import pytest
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock
from contextlib import contextmanager

# Add src to pythonpath so we can import ytrd modules
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# ============================================================================
# Directory and Input Fixtures
# ============================================================================

@pytest.fixture
def temp_dir(tmp_path):
    """Fixture providing a temporary directory for tests."""
    return tmp_path

@pytest.fixture
def mock_yes_input(monkeypatch):
    """Simulates user entering 'y'."""
    monkeypatch.setattr('builtins.input', lambda _: 'y')

@pytest.fixture
def mock_no_input(monkeypatch):
    """Simulates user entering 'n'."""
    monkeypatch.setattr('builtins.input', lambda _: 'n')

# ============================================================================
# yt-dlp Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_ydl_video_info():
    """Standard video info dictionary for mocking yt-dlp responses."""
    return {
        'duration': 341.0,
        'height': 1080,
        'title': 'Test Video Title',
        'uploader': 'Test Channel',
        'language': 'en',
        'formats': [
            {'height': 1080, 'vcodec': 'avc1', 'ext': 'mp4'},
            {'height': 720, 'vcodec': 'avc1', 'ext': 'mp4'},
            {'height': 480, 'vcodec': 'avc1', 'ext': 'mp4'},
        ]
    }

@pytest.fixture
def mock_youtube_dl_success(monkeypatch, mock_ydl_video_info):
    """Mock successful yt-dlp download with proper context manager."""
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = mock_ydl_video_info
    
    @contextmanager
    def mock_ydl_context(*args, **kwargs):
        yield mock_ydl_instance
    
    import yt_dlp
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
    return mock_ydl_instance

@pytest.fixture
def mock_youtube_dl_error(monkeypatch):
    """Mock yt-dlp download error."""
    import yt_dlp
    
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Network error")
    
    @contextmanager
    def mock_ydl_context(*args, **kwargs):
        yield mock_ydl_instance
    
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
    return mock_ydl_instance

# ============================================================================
# VOT API Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_vot_ready_response():
    """Mock VOT API response for ready translation."""
    # Protobuf: {status: 1 (Ready), url: "http://test.mp3"}
    # Field 4 (status), wire type 0: tag = (4 << 3) | 0 = 0x20, value = 1
    # Field 1 (url), wire type 2: tag = (1 << 3) | 2 = 0x0A, length = 15 (0x0F)
    return b"\x20\x01\x0A\x0Fhttp://test.mp3"

@pytest.fixture
def mock_vot_waiting_response():
    """Mock VOT API response for waiting status."""
    # Protobuf: {status: 2 (Waiting)}
    return b"\x20\x02"

@pytest.fixture
def mock_vot_error_response():
    """Mock VOT API response for error status."""
    # Protobuf: {status: 0 (Error), message: "Translation failed"}
    return b"\x20\x00\x4A\x12Translation failed"

# ============================================================================
# File System Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_file_operations(monkeypatch):
    """Mock common file operations."""
    created_files = []
    removed_files = []
    
    original_exists = os.path.exists
    original_makedirs = os.makedirs
    
    def mock_exists(path):
        if path in created_files:
            return True
        return original_exists(path)
    
    def mock_remove(path):
        removed_files.append(path)
    
    def mock_makedirs(path, *args, **kwargs):
        created_files.append(path)
    
    monkeypatch.setattr(os.path, 'exists', mock_exists)
    monkeypatch.setattr(os, 'remove', mock_remove)
    monkeypatch.setattr(os, 'makedirs', mock_makedirs)
    
    return {
        'created': created_files,
        'removed': removed_files
    }
