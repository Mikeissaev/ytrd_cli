import requests
import struct
import uuid
import hmac
import hashlib
import time
import json
import re
from urllib.parse import urlparse, parse_qs

# Configuration
YANDEX_HMAC_KEY = b"bt8xH3VOlb4mqf0nqAibnDOoiPlXsisf"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 YaBrowser/24.4.0.0 Safari/537.36"

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

def get_video_id(url):
    """
    Extracts YouTube video ID from URL.
    """
    try:
        parsed_url = urlparse(url)
    except Exception:
        return None

    if parsed_url.netloc in ["youtu.be"]:
        return parsed_url.path.lstrip("/")
    
    if parsed_url.netloc in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
        if parsed_url.path == "/watch":
            params = parse_qs(parsed_url.query)
            return params.get("v", [None])[0]
        if parsed_url.path.startswith("/embed/"):
            return parsed_url.path.split("/")[2]
        if parsed_url.path.startswith("/v/"):
            return parsed_url.path.split("/")[2]
        if parsed_url.path.startswith("/shorts/"):
            return parsed_url.path.split("/")[2]
            
    return None

def get_uuid():
    return str(uuid.uuid4()).replace("-", "")

def get_signature(body):
    """
    Calculates HMAC SHA256 signature for the request body.
    """
    signature = hmac.new(YANDEX_HMAC_KEY, body, hashlib.sha256).hexdigest()
    return signature


def translate_video(url, duration=341.0):
    video_id = get_video_id(url)
    if not video_id:
        return {"success": False, "message": "Invalid YouTube URL"}

    # Видео ID используется только для валидации, но сам запрос требует URL
    
    body = b""
    body += encode_string(3, url)
    body += encode_bool(5, True)
    body += encode_double(6, float(duration))
    body += encode_int32(7, 1)
    body += encode_string(8, "en") # Request Lang (обычно определяется автоматически или 'en')
    body += encode_int32(9, 0)
    body += encode_int32(10, 0)
    body += encode_string(14, "ru") # Response Lang
    body += encode_int32(15, 0)
    body += encode_int32(16, 1)
    body += encode_int32(17, 0)

    headers = {
        "Accept": "application/x-protobuf",
        "Accept-Language": "en",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT,
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
