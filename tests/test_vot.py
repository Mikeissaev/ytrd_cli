import pytest
import requests
import time
from ytrd import vot
from ytrd import config
from unittest.mock import MagicMock


class TestGetTranslationAudio:
    """Test suite for translation audio retrieval with polling."""

    def test_get_translation_audio_ready_immediately(self, monkeypatch, mock_vot_ready_response):
        """Test successful translation that is ready immediately."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_ready_response
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "test_id")

        # Теперь vot.get_translation_audio возвращает кортеж (success, url)
        result = vot.get_translation_audio("url", 341.0)

        assert result == (True, "http://test.mp3")

    def test_get_translation_audio_waiting_then_ready(self, monkeypatch, mock_vot_waiting_response, mock_vot_ready_response):
        """Test polling mechanism (Waiting → Ready)."""
        mock_responses = [
            MagicMock(content=mock_vot_waiting_response),
            MagicMock(content=mock_vot_ready_response),
        ]

        for resp in mock_responses:
            resp.raise_for_status = MagicMock()

        call_count = [0]
        def mock_post(*args, **kwargs):
            response = mock_responses[call_count[0]]
            call_count[0] += 1
            return response

        monkeypatch.setattr(requests, 'post', mock_post)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "test_id")
        monkeypatch.setattr(time, 'sleep', MagicMock())  # Don't actually sleep

        result = vot.get_translation_audio("url", 341.0)

        assert result == (True, "http://test.mp3")
        assert call_count[0] == 2  # Should have polled twice

    def test_get_translation_audio_error_status(self, monkeypatch, mock_vot_error_response):
        """Test handling of error status from VOT API."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_error_response
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "test_id")

        result = vot.get_translation_audio("url", 341.0)

        assert result == (False, None)

    def test_get_translation_audio_timeout(self, monkeypatch, mock_vot_waiting_response):
        """Test timeout when translation takes too long."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_waiting_response
        mock_response.raise_for_status = MagicMock()

        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "test_id")
        monkeypatch.setattr(time, 'sleep', MagicMock())

        result = vot.get_translation_audio("url", 341.0)

        # Should timeout after RETRY_ATTEMPTS
        assert result == (False, None)


class TestTranslateVideo:
    """Test suite for low-level VOT API calls."""
    
    def test_translate_video_ready_status(self, monkeypatch, mock_vot_ready_response):
        """Test successful translation with Ready status."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_ready_response
        mock_response.raise_for_status = MagicMock()
        
        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "video_id")
        
        result = vot.translate_video("http://youtube.com/watch?v=video_id")
        
        assert result['success'] is True
        assert result['status'] == 'Ready'
        assert result['url'] == 'http://test.mp3'
    
    def test_translate_video_waiting_status(self, monkeypatch, mock_vot_waiting_response):
        """Test Waiting status response."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_waiting_response
        mock_response.raise_for_status = MagicMock()
        
        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "video_id")
        
        result = vot.translate_video("url")
        
        assert result['success'] is True
        assert result['status'] == 'Waiting'
        assert result['url'] is None
    
    def test_translate_video_error_status(self, monkeypatch, mock_vot_error_response):
        """Test Error status response with message."""
        mock_response = MagicMock()
        mock_response.content = mock_vot_error_response
        mock_response.raise_for_status = MagicMock()
        
        monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: mock_response)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "video_id")
        
        result = vot.translate_video("url")
        
        assert result['success'] is False
        assert result['status'] == 'Error'
        assert 'Translation failed' in result['message']
    
    def test_translate_video_network_error(self, monkeypatch):
        """Test handling of network errors."""
        def mock_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Network error")
        
        monkeypatch.setattr(requests, 'post', mock_post)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "video_id")
        
        result = vot.translate_video("url")
        
        assert result['success'] is False
        assert 'Network error' in result['message']
    
    def test_translate_video_invalid_url(self, monkeypatch):
        """Test handling of invalid YouTube URL."""
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: None)
        
        result = vot.translate_video("invalid_url")
        
        assert result['success'] is False
        assert 'Invalid YouTube URL' in result['message']
    
    def test_translate_video_builds_correct_protobuf(self, monkeypatch):
        """Test that correct protobuf request is built."""
        captured_data = {}
        
        def mock_post(url, data, headers, timeout):
            captured_data['data'] = data
            captured_data['headers'] = headers
            
            mock_response = MagicMock()
            mock_response.content = b"\x20\x01\x0A\x04test"
            mock_response.raise_for_status = MagicMock()
            return mock_response
        
        monkeypatch.setattr(requests, 'post', mock_post)
        monkeypatch.setattr(vot.utils, 'extract_video_id', lambda x: "test_id")
        
        vot.translate_video("http://youtube.com/watch?v=test", duration=120.0)
        
        # Check headers
        assert 'Vtrans-Signature' in captured_data['headers']
        assert 'Sec-Vtrans-Token' in captured_data['headers']
        assert captured_data['headers']['Content-Type'] == 'application/x-protobuf'
        
        # Check data is bytes
        assert isinstance(captured_data['data'], bytes)


class TestProtobufHelpers:
    """Test suite for protobuf encoding/decoding helpers."""
    
    def test_encode_varint_small_numbers(self):
        """Test varint encoding for small numbers."""
        assert vot.encode_varint(0) == b'\x00'
        assert vot.encode_varint(1) == b'\x01'
        assert vot.encode_varint(127) == b'\x7f'
    
    def test_encode_varint_large_numbers(self):
        """Test varint encoding for larger numbers."""
        # 300 = 0b100101100 → 1010 1100, 0000 0010
        result = vot.encode_varint(300)
        assert len(result) == 2
        assert result[0] & 0x80  # High bit set on first byte
        assert not (result[1] & 0x80)  # High bit clear on last byte
    
    def test_read_varint(self):
        """Test varint decoding."""
        # Single byte
        val, pos = vot.read_varint(b'\x05\xFF', 0)
        assert val == 5
        assert pos == 1
        
        # Multi-byte (300 = 0xAC, 0x02)
        val, pos = vot.read_varint(b'\xAC\x02\xFF', 0)
        assert val == 300
        assert pos == 2
    
    def test_encode_string(self):
        """Test string field encoding."""
        result = vot.encode_string(1, "test")
        # Should be: tag (field 1, wire type 2) + length (4) + "test"
        assert isinstance(result, bytes)
        assert b'test' in result
    
    def test_simple_protobuf_reader_parses_fields(self):
        """Test protobuf reader can extract fields."""
        # Construct: {field 1 (string): "hello", field 4 (varint): 42}
        data = vot.encode_string(1, "hello") + vot.encode_tag(4, 0) + vot.encode_varint(42)
        
        reader = vot.SimpleProtobufReader(data)
        
        assert reader.get_string(1) == "hello"
        assert reader.get_int(4) == 42
    
    def test_simple_protobuf_reader_handles_unknown_fields(self):
        """Test that unknown wire types don't crash parser."""
        # Include unknown wire type that should be skipped
        data = b'\x08\x05'  # Field 1, wire type 0, value 5
        
        reader = vot.SimpleProtobufReader(data)
        assert reader.get_int(1) == 5


class TestSignatureGeneration:
    """Test suite for HMAC signature generation."""
    
    def test_get_signature_returns_hex_string(self):
        """Test that signature is a valid hex string."""
        body = b"test_body"
        signature = vot.get_signature(body)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex = 64 chars
        # Should be valid hex
        int(signature, 16)
    
    def test_get_signature_deterministic(self):
        """Test that same input produces same signature."""
        body = b"test_body"
        sig1 = vot.get_signature(body)
        sig2 = vot.get_signature(body)
        
        assert sig1 == sig2
    
    def test_get_signature_different_for_different_input(self):
        """Test that different inputs produce different signatures."""
        sig1 = vot.get_signature(b"body1")
        sig2 = vot.get_signature(b"body2")
        
        assert sig1 != sig2
