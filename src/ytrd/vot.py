import requests
import struct
import uuid
import hmac
import hashlib
import time
import json
import re
from . import config
from . import utils
from . import downloader

def get_translation_audio(url, duration, step_label="[1/3]", retry_callback=None, use_live_voice=False):
    """Uses vot.py to get translation, waits for readiness and downloads."""
    print(f"\n{config.COLOR_YELLOW}{step_label} Запрос перевода{' (Живой голос)' if use_live_voice else ''}...{config.COLOR_RESET}")
    
    # Polling (maximum defined in config)
    max_attempts = config.RETRY_ATTEMPTS 
    for attempt in range(max_attempts):
        result = translate_video(url, duration, use_live_voice)
        
        if not result.get("success"):
            print(f"{config.COLOR_RED}❌ Ошибка API перевода: {result.get('message')}{config.COLOR_RESET}")
            return False
            
        status = result.get("status")
        if status == "Ready":
            audio_url = result.get("url")
            if audio_url:
                print(f"{config.COLOR_GREEN}✅ Перевод готов!{config.COLOR_RESET}")
                downloader.download_audio(audio_url, config.TEMP_AUDIO_FILENAME, retry_callback=retry_callback)
                return True
            else:
                 print(f"{config.COLOR_RED}❌ Ошибка: Статус Ready, но нет URL.{config.COLOR_RESET}")
                 return False
                 
        elif status == "Waiting":
            print(f"{config.COLOR_YELLOW}⏳ Перевод в процессе... (Попытка {attempt+1}/{max_attempts}){config.COLOR_RESET}")
            time.sleep(config.RETRY_SLEEP_SECONDS)
            
        else:
             print(f"{config.COLOR_RED}❌ Неизвестный статус или ошибка: {result.get('message')}{config.COLOR_RESET}")
             return False

    print(f"{config.COLOR_RED}❌ Время ожидания перевода истекло.{config.COLOR_RESET}")
    return False

# --- Protobuf Helpers ---
# Minimal implementation to avoid needing 'protoc' installed

def encode_varint(value):
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

def read_varint(buffer, pos):
    result = 0
    shift = 0
    while True:
        b = buffer[pos]
        result |= (b & 0x7f) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7

def encode_tag(field_number, wire_type):
    return encode_varint((field_number << 3) | wire_type)

def encode_string(field_number, value):
    if value is None:
        return b""
    encoded = value.encode('utf-8')
    return encode_tag(field_number, 2) + encode_varint(len(encoded)) + encoded

def encode_bool(field_number, value):
    return encode_tag(field_number, 0) + encode_varint(1 if value else 0)

def encode_double(field_number, value):
    return encode_tag(field_number, 1) + struct.pack('<d', float(value))

def encode_int32(field_number, value):
    return encode_tag(field_number, 0) + encode_varint(value)

class SimpleProtobufReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.fields = {}
        self._parse()

    def _parse(self):
        while self.pos < len(self.data):
            try:
                tag, self.pos = read_varint(self.data, self.pos)
                field_number = tag >> 3
                wire_type = tag & 0x07
                
                if wire_type == 0: # Varint
                    val, self.pos = read_varint(self.data, self.pos)
                    self.fields[field_number] = val
                elif wire_type == 2: # Length-delimited (string, bytes, embedded messages)
                    length, self.pos = read_varint(self.data, self.pos)
                    val = self.data[self.pos:self.pos+length]
                    self.pos += length
                    self.fields[field_number] = val
                elif wire_type == 1: # 64-bit
                    val = self.data[self.pos:self.pos+8]
                    self.pos += 8
                    self.fields[field_number] = val
                elif wire_type == 5: # 32-bit
                    val = self.data[self.pos:self.pos+4]
                    self.pos += 4
                    self.fields[field_number] = val
                else:
                    # Skip unknown
                    pass 
            except IndexError:
                break

    def get_string(self, field_number):
        if field_number in self.fields:
            return self.fields[field_number].decode('utf-8')
        return None

    def get_int(self, field_number):
        return self.fields.get(field_number)

# --- Core Logic ---

def get_uuid():
    return str(uuid.uuid4()).replace("-", "")

def get_signature(body):
    """
    Calculates HMAC SHA256 signature for the request body.
    """
    signature = hmac.new(config.VOT_HMAC_KEY, body, hashlib.sha256).hexdigest()
    return signature


def translate_video(url, duration=341.0, use_live_voice=False):
    video_id = utils.extract_video_id(url)
    if not video_id:
        return {"success": False, "message": "Invalid YouTube URL"}

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
    except requests.exceptions.RequestException as e:
         return {"success": False, "message": f"Network error: {str(e)}"}

    reader = SimpleProtobufReader(response.content)
    
    status = reader.get_int(4)
    message = reader.get_string(9)
    audio_url = reader.get_string(1)
    
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
    elif status == 0:
        return {
            "success": False,
            "status": "Error", 
            "url": None,
            "message": message if message else "Unknown error"
        }
    else:
         return {
            "success": False,
            "status": "Unknown", 
            "url": None,
            "message": f"Unknown status: {status}"
        }
