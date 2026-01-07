import requests
import struct
import uuid
import hmac
import hashlib
import time
import json
import re
from typing import Optional, Tuple
from . import config
from . import utils
from . import errors
from . import logger

# Инициализация логгера для модуля vot
log = logger.get_logger(__name__)

def get_translation_audio(
    url: str,
    duration: float,
    use_live_voice: bool = False
) -> Tuple[bool, Optional[str]]:
    """Запрашивает перевод и ждёт готовности.

    Args:
        url: URL видео
        duration: Длительность видео
        use_live_voice: Использовать ли "Живой голос"

    Returns:
        Кортеж (success: bool, audio_url: str | None)
    """
    log.info(f"Starting translation polling: url={url}, duration={duration}, live_voice={use_live_voice}")
    print(f"\n{config.COLOR_YELLOW}[1/3] Запрос перевода{' (Живой голос)' if use_live_voice else ''}...{config.COLOR_RESET}")

    # Polling (maximum defined in config)
    max_attempts = config.RETRY_ATTEMPTS
    for attempt in range(max_attempts):
        result = translate_video(url, duration, use_live_voice)

        if not result.get("success"):
            log.error(f"Translation API error: {result.get('message')}")
            print(f"{config.COLOR_RED}❌ Ошибка API перевода: {result.get('message')}{config.COLOR_RESET}")
            return False, None

        status = result.get("status")
        if status == "Ready":
            audio_url = result.get("url")
            if audio_url:
                log.info("Translation is ready")
                print(f"{config.COLOR_GREEN}✅ Перевод готов!{config.COLOR_RESET}")
                return True, audio_url
            else:
                log.error("Translation status Ready but no URL returned")
                print(f"{config.COLOR_RED}❌ Ошибка: Статус Ready, но нет URL.{config.COLOR_RESET}")
                return False, None

        elif status == "Waiting":
            log.debug(f"Translation in progress (attempt {attempt+1}/{max_attempts})")
            print(f"{config.COLOR_YELLOW}⏳ Перевод в процессе... (Попытка {attempt+1}/{max_attempts}){config.COLOR_RESET}")
            time.sleep(config.RETRY_SLEEP_SECONDS)

        else:
            log.error(f"Unknown translation status or error: {result.get('message')}")
            print(f"{config.COLOR_RED}❌ Неизвестный статус или ошибка: {result.get('message')}{config.COLOR_RESET}")
            return False, None

    log.error("Translation polling timeout")
    print(f"{config.COLOR_RED}❌ Время ожидания перевода истекло.{config.COLOR_RESET}")
    return False, None

# --- Protobuf Helpers ---
# Minimal implementation to avoid needing 'protoc' installed

def encode_varint(value: int) -> bytes:
    """Кодирует целое число в varint формат."""
    target = []
    if value < 0:
        value += (1 << 64)
    bits = value & 0x7f
    value >>= 7
    while value:
        target.append(bits | 0x80)
        bits = value & 0x7f
        value >>= 7
    target.append(bits)
    return bytes(target)

def read_varint(buffer: bytes, pos: int) -> tuple[int, int]:
    """Декодирует varint из буфера.

    Returns:
        Кортеж (value, new_position)
    """
    result = 0
    shift = 0
    while True:
        b = buffer[pos]
        result |= (b & 0x7f) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7

def encode_tag(field_number: int, wire_type: int) -> bytes:
    return encode_varint((field_number << 3) | wire_type)

def encode_string(field_number: int, value: Optional[str]) -> bytes:
    if value is None:
        return b""
    encoded = value.encode('utf-8')
    return encode_tag(field_number, 2) + encode_varint(len(encoded)) + encoded

def encode_bool(field_number: int, value: bool) -> bytes:
    return encode_tag(field_number, 0) + encode_varint(1 if value else 0)

def encode_double(field_number: int, value: float) -> bytes:
    return encode_tag(field_number, 1) + struct.pack('<d', float(value))

def encode_int32(field_number: int, value: int) -> bytes:
    return encode_tag(field_number, 0) + encode_varint(value)

class SimpleProtobufReader:
    """Простой парсер protobuf сообщений."""

    def __init__(self, data: bytes) -> None:
        self.data: bytes = data
        self.pos: int = 0
        self.fields: dict[int, bytes | int] = {}
        self._parse()

    def _parse(self) -> None:
        while self.pos < len(self.data):
            try:
                tag, self.pos = read_varint(self.data, self.pos)
                field_number = tag >> 3
                wire_type = tag & 0x07

                if wire_type == 0:  # Varint
                    val, self.pos = read_varint(self.data, self.pos)
                    self.fields[field_number] = val
                elif wire_type == 2:  # Length-delimited (string, bytes, embedded messages)
                    length, self.pos = read_varint(self.data, self.pos)
                    val = self.data[self.pos:self.pos+length]
                    self.pos += length
                    self.fields[field_number] = val
                elif wire_type == 1:  # 64-bit
                    val = self.data[self.pos:self.pos+8]
                    self.pos += 8
                    self.fields[field_number] = val
                elif wire_type == 5:  # 32-bit
                    val = self.data[self.pos:self.pos+4]
                    self.pos += 4
                    self.fields[field_number] = val
                else:
                    # Skip unknown
                    pass
            except IndexError:
                break

    def get_string(self, field_number: int) -> Optional[str]:
        if field_number in self.fields:
            return self.fields[field_number].decode('utf-8')
        return None

    def get_int(self, field_number: int) -> Optional[int]:
        return self.fields.get(field_number)


# --- Core Logic ---

def get_uuid() -> str:
    """Генерирует UUID для запроса."""
    return str(uuid.uuid4()).replace("-", "")

def get_signature(body: bytes) -> str:
    """Вычисляет HMAC SHA256 подпись для тела запроса."""
    signature = hmac.new(config.VOT_HMAC_KEY, body, hashlib.sha256).hexdigest()
    return signature


def translate_video(url: str, duration: float = 341.0, use_live_voice: bool = False) -> dict:
    video_id = utils.extract_video_id(url)
    if not video_id:
        log.warning(f"Invalid YouTube URL: {url}")
        return {"success": False, "message": "Invalid YouTube URL"}

    log.debug(f"Requesting translation: url={url}, video_id={video_id}, duration={duration}, live_voice={use_live_voice}")

    # Video ID is used for validation only, but the request itself requires URL
    
    body = b""
    body += encode_string(3, url)
    body += encode_bool(5, True)
    body += encode_double(6, float(duration))
    body += encode_int32(7, 1)
    body += encode_string(8, "en") # Request Lang (usually detected automatically or 'en')
    body += encode_int32(9, 0)
    body += encode_int32(10, 0)
    body += encode_string(14, "ru") # Response Lang
    body += encode_int32(15, 0)
    body += encode_int32(16, 2)
    body += encode_int32(17, 0)
    body += encode_bool(18, use_live_voice)
    body += encode_string(19, "") # Video Title

    headers = {
        "Accept": "application/x-protobuf",
        "Accept-Language": "en",
        "Content-Type": "application/x-protobuf",
        "User-Agent": config.HTTP_USER_AGENT,
        "Vtrans-Signature": get_signature(body),
        "Sec-Vtrans-Token": get_uuid()
    }

    try:
        response = requests.post(
            "https://api.browser.yandex.ru/video-translation/translate",
            data=body,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        log.debug(f"VOT API response status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log.error(f"VOT API request failed: {e}", exc_info=True)
        return {"success": False, "message": f"Network error: {str(e)}"}

    reader = SimpleProtobufReader(response.content)
    
    status = reader.get_int(4)
    message = reader.get_string(9)
    audio_url = reader.get_string(1)

    log.debug(f"VOT response: status={status}, message={message}, has_audio_url={bool(audio_url)}")

    if status == 1:
        return {
            "success": True,
            "status": "Ready",
            "url": audio_url,
            "message": "Translation ready"
        }
    elif status == 2:
        return {
            "success": True,
            "status": "Waiting",
            "url": None,
            "message": "Translation will take a few minutes"
        }
    elif status == 7:
        # Статус 7 - перевод в процессе/инициализации (новый статус VOT API)
        log.info(f"VOT status 7: Translation initializing, will retry")
        return {
            "success": True,
            "status": "Waiting",
            "url": None,
            "message": "Translation is being prepared"
        }
    elif status == 0:
        log.warning(f"VOT returned error status: {message}")
        return {
            "success": False,
            "status": "Error",
            "url": None,
            "message": message if message else "Unknown error"
        }
    else:
        # Другие неизвестные статусы считаем ошибкой
        log.warning(f"VOT returned unknown status: {status}, message: {message}")
        error_msg = message if message else f"Перевод недоступен (код: {status})"
        return {
            "success": False,
            "status": "Error",
            "url": None,
            "message": error_msg
        }
