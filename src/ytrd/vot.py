import hashlib
import hmac
import requests
import struct
import time
import uuid
from typing import Optional, Tuple
from . import config
from . import errors
from . import logger
from . import utils

log = logger.get_logger(__name__)


def get_translation_audio(
    url: str,
    duration: float,
    use_live_voice: bool = False,
    source_lang: str = "en"
) -> Tuple[bool, Optional[str]]:
    log.info(f"Starting translation polling: url={url}, duration={duration}, live_voice={use_live_voice}, source_lang={source_lang}")
    print(f"\n{config.COLOR_YELLOW}[1/3] Запрос перевода{' (Живой голос)' if use_live_voice else ''}...{config.COLOR_RESET}")

    max_attempts = config.RETRY_ATTEMPTS
    for attempt in range(max_attempts):
        result = translate_video(url, duration, use_live_voice, source_lang=source_lang)

        if not result.get("success"):
            error_type = result.get("error_type")
            if error_type == "protocol":
                raise errors.YtrdTranslationProtocolError(result.get("message") or "Некорректный ответ API")
            if error_type == "network":
                raise errors.YtrdTranslationUnavailable(result.get("message") or "Сетевая ошибка API перевода")
            log.error(f"Translation API error: {result.get('message')}")
            return False, None

        status = result.get("status")
        if status == "Ready":
            audio_url = result.get("url")
            if audio_url:
                log.info("Translation is ready")
                print(f"{config.COLOR_GREEN}✅ Перевод готов!{config.COLOR_RESET}")
                return True, audio_url
            raise errors.YtrdTranslationProtocolError("Статус Ready, но URL перевода отсутствует")

        if status == "Waiting":
            log.debug(f"Translation in progress (attempt {attempt+1}/{max_attempts})")
            print(f"{config.COLOR_YELLOW}⏳ Перевод в процессе... (Попытка {attempt+1}/{max_attempts}){config.COLOR_RESET}")
            time.sleep(config.RETRY_SLEEP_SECONDS)
            continue

        raise errors.YtrdTranslationProtocolError(result.get("message") or "Неизвестный статус ответа API")

    log.error("Translation polling timeout")
    return False, None


def check_translation_availability(url: str, duration: float, source_lang: str = "en") -> dict:
    """Checks translation availability for both voice types without downloading.

    Performs a single API request per mode (standard and live voice).

    Returns:
        dict: {'standard': result, 'live': result} — результат translate_video()
              для каждого режима.
    """
    log.info(f"Checking translation availability: url={url}, duration={duration}, source_lang={source_lang}")
    results = {}
    for mode, use_live in (('standard', False), ('live', True)):
        results[mode] = translate_video(url, duration, use_live, source_lang=source_lang)
        log.debug(f"Check result ({mode}): {results[mode]}")
    return results


def encode_varint(value: int) -> bytes:
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
    result = 0
    shift = 0
    while True:
        if pos >= len(buffer):
            raise errors.YtrdTranslationProtocolError("Неожиданный конец protobuf varint")
        byte = buffer[pos]
        result |= (byte & 0x7f) << shift
        pos += 1
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise errors.YtrdTranslationProtocolError("Слишком длинный protobuf varint")


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
    def __init__(self, data: bytes) -> None:
        self.data: bytes = data or b""
        self.pos: int = 0
        self.fields: dict[int, object] = {}
        self._parse()

    def _read_bytes(self, length: int) -> bytes:
        if length < 0 or self.pos + length > len(self.data):
            raise errors.YtrdTranslationProtocolError("Некорректная длина protobuf поля")
        value = self.data[self.pos:self.pos+length]
        self.pos += length
        return value

    def _parse(self) -> None:
        if not self.data:
            raise errors.YtrdTranslationProtocolError("Пустой ответ API перевода")

        while self.pos < len(self.data):
            tag, self.pos = read_varint(self.data, self.pos)
            field_number = tag >> 3
            wire_type = tag & 0x07

            if wire_type == 0:
                val, self.pos = read_varint(self.data, self.pos)
                self.fields[field_number] = val
            elif wire_type == 2:
                length, self.pos = read_varint(self.data, self.pos)
                self.fields[field_number] = self._read_bytes(length)
            elif wire_type == 1:
                self.fields[field_number] = self._read_bytes(8)
            elif wire_type == 5:
                self.fields[field_number] = self._read_bytes(4)
            else:
                raise errors.YtrdTranslationProtocolError(f"Неподдерживаемый protobuf wire_type: {wire_type}")

    def get_string(self, field_number: int) -> Optional[str]:
        value = self.fields.get(field_number)
        if value is None:
            return None
        if not isinstance(value, (bytes, bytearray)):
            raise errors.YtrdTranslationProtocolError(f"Поле {field_number} не является строкой")
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise errors.YtrdTranslationProtocolError(f"Некорректная UTF-8 строка в поле {field_number}") from exc

    def get_int(self, field_number: int) -> Optional[int]:
        value = self.fields.get(field_number)
        if value is None:
            return None
        if not isinstance(value, int):
            raise errors.YtrdTranslationProtocolError(f"Поле {field_number} не является целым числом")
        return value


def get_uuid() -> str:
    return str(uuid.uuid4()).replace("-", "")


def get_signature(body: bytes) -> str:
    return hmac.new(config.VOT_HMAC_KEY, body, hashlib.sha256).hexdigest()


def translate_video(url: str, duration: float = 341.0, use_live_voice: bool = False, source_lang: str = "en") -> dict:
    video_id = utils.extract_video_id(url)
    if not video_id:
        log.warning(f"Invalid YouTube URL: {url}")
        return {"success": False, "message": "Invalid YouTube URL"}

    body = b""
    body += encode_string(3, url)
    body += encode_bool(5, True)
    body += encode_double(6, float(duration))
    body += encode_int32(7, 1)
    body += encode_string(8, source_lang)
    body += encode_int32(9, 0)
    body += encode_int32(10, 0)
    body += encode_string(14, "ru")
    body += encode_int32(15, 0)
    body += encode_int32(16, 2)
    body += encode_int32(17, 0)
    body += encode_bool(18, use_live_voice)
    body += encode_string(19, "")

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
        return {"success": False, "error_type": "network", "message": f"Network error: {str(e)}"}

    try:
        reader = SimpleProtobufReader(response.content)
        status = reader.get_int(4)
        message = reader.get_string(9)
        audio_url = reader.get_string(1)
    except errors.YtrdTranslationProtocolError as exc:
        log.error(f"Invalid VOT API response: {exc}")
        return {"success": False, "error_type": "protocol", "message": str(exc)}

    log.debug(f"VOT response: status={status}, message={message}, has_audio_url={bool(audio_url)}")

    if status == 1:
        return {
            "success": True,
            "status": "Ready",
            "url": audio_url,
            "message": "Translation ready"
        }
    if status == 2:
        return {
            "success": True,
            "status": "Waiting",
            "url": None,
            "message": "Translation will take a few minutes"
        }
    if status == 7:
        return {
            "success": True,
            "status": "Waiting",
            "url": None,
            "message": "Translation is being prepared"
        }
    if status == 0:
        log.warning(f"VOT returned error status: {message}")
        return {
            "success": False,
            "status": "Error",
            "url": None,
            "message": message if message else "Unknown error"
        }

    log.warning(f"VOT returned unknown status: {status}, message: {message}")
    error_msg = message if message else f"Перевод недоступен (код: {status})"
    return {
        "success": False,
        "status": "Error",
        "url": None,
        "message": error_msg
    }
