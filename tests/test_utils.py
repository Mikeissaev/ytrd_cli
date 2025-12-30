import pytest
import os
import shutil
import ytrd.utils as utils
from ytrd import config


class TestCleanName:
    """Test suite for filename cleaning function."""
    
    def test_clean_name_removes_invalid_characters(self):
        """Test that invalid characters are removed from filenames."""
        assert utils.clean_name("Video: Test/Name") == "Video TestName"
        assert utils.clean_name("File|Name<>?") == "FileName"
    
    def test_clean_name_preserves_valid_characters(self):
        """Test that valid characters are preserved."""
        assert utils.clean_name("Normal Name") == "Normal Name"
        assert utils.clean_name("Video-Test_2024.mp4") == "Video-Test_2024.mp4"
    
    def test_clean_name_empty_string_fallback(self):
        """Test that empty string returns default name."""
        assert utils.clean_name("") == "Video_Dubbed"
        assert utils.clean_name(None) == "Video_Dubbed"
    
    def test_clean_name_length_limit(self):
        """Test that long names are truncated to 60 chars."""
        long_name = "a" * 100
        result = utils.clean_name(long_name)
        assert len(result) == 60
        assert result == "a" * 60


class TestGetBinaryPath:
    """Test suite for binary path resolution."""
    
    def test_get_binary_path_found(self, monkeypatch):
        """Test get_binary_path when tool exists in PATH."""
        monkeypatch.setattr(shutil, 'which', lambda x: f"/usr/bin/{x}")
        assert utils.get_binary_path("ffmpeg") == "/usr/bin/ffmpeg"
    
    def test_get_binary_path_not_found(self, monkeypatch):
        """Test get_binary_path when tool is missing."""
        monkeypatch.setattr(shutil, 'which', lambda x: None)
        # Mock os.path.exists to return False for Termux fallback
        monkeypatch.setattr(os.path, 'exists', lambda x: False)
        assert utils.get_binary_path("unknown_tool") is None
    
    def test_get_binary_path_termux_fallback(self, monkeypatch):
        """Test fallback to Termux paths when not in system PATH."""
        monkeypatch.setattr(shutil, 'which', lambda x: None)
        
        def mock_exists(path):
            return "/data/data/com.termux" in path and "ffmpeg" in path
        
        monkeypatch.setattr(os.path, 'exists', mock_exists)
        result = utils.get_binary_path("ffmpeg")
        assert result is not None
        assert "com.termux" in result


class TestCleanup:
    """Test suite for cleanup function."""
    
    def test_cleanup_removes_temp_files(self, monkeypatch):
        """Test that cleanup removes all temporary video and audio files."""
        removed_files = []
        
        def mock_glob(pattern):
            if "video" in pattern:
                return ["temp_video.mp4", "temp_video.part", "temp_video.mkv"]
            if "audio" in pattern:
                return ["temp_audio.mp3", "temp_audio.part"]
            return []
        
        monkeypatch.setattr("glob.glob", mock_glob)
        monkeypatch.setattr(os, "remove", lambda x: removed_files.append(x))
        
        utils.cleanup()
        
        # Should remove all temp files
        assert len(removed_files) == 5
        assert "temp_video.mp4" in removed_files
        assert "temp_audio.mp3" in removed_files
    
    def test_cleanup_preserves_files_on_error(self, monkeypatch):
        """Test that cleanup does NOT remove files when error=True."""
        removed_files = []
        
        # Mock glob to return files (but they should not be deleted)
        monkeypatch.setattr("glob.glob", lambda pattern: ["temp_video.mp4"])
        monkeypatch.setattr(os, "remove", lambda x: removed_files.append(x))
        
        utils.cleanup(error=True)
        
        # Should NOT remove any files
        assert len(removed_files) == 0
    
    def test_cleanup_handles_oserror_gracefully(self, monkeypatch):
        """Test that cleanup continues even if file deletion fails."""
        def mock_glob(pattern):
            # Return appropriate files based on pattern
            if "video" in pattern:
                return ["temp_video.mp4"]
            elif "audio" in pattern:
                return ["temp_audio.mp3"]
            return []
        
        call_count = 0
        def mock_remove(path):
            nonlocal call_count
            call_count += 1
            if "video" in path:
                raise OSError("File in use")
            # Should not raise, just log
        
        monkeypatch.setattr("glob.glob", mock_glob)
        monkeypatch.setattr(os, "remove", mock_remove)
        
        # Should not raise exception
        utils.cleanup()
        assert call_count == 2  # Both files attempted


class TestCleanVideoPartials:
    """Test suite for cleaning video partial files."""
    
    def test_clean_video_partials_removes_only_video(self, monkeypatch):
        """Test that only video files are removed, audio is preserved."""
        removed_files = []
        
        def mock_glob(pattern):
            if "video" in pattern:
                return ["temp_video.mp4", "temp_video.part"]
            return []
        
        monkeypatch.setattr("glob.glob", mock_glob)
        monkeypatch.setattr(os, "remove", lambda x: removed_files.append(x))
        
        utils.clean_video_partials()
        
        assert len(removed_files) == 2
        assert all("video" in f for f in removed_files)
        # Audio should be preserved (not in removed list since glob doesn't return it)


class TestExtractVideoId:
    """Test suite for YouTube video ID extraction."""
    
    @pytest.mark.parametrize("url,expected_id", [
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ])
    def test_extract_video_id_valid_urls(self, url, expected_id):
        """Test extraction from various valid YouTube URL formats."""
        assert utils.extract_video_id(url) == expected_id
    
    @pytest.mark.parametrize("invalid_url", [
        "invalid_url",
        "https://vimeo.com/123456",
        "https://www.example.com",
        "",
    ])
    def test_extract_video_id_invalid_urls(self, invalid_url):
        """Test that invalid URLs return None."""
        assert utils.extract_video_id(invalid_url) is None


class TestCheckWritePermissions:
    """Test suite for write permission checks."""
    
    def test_check_write_permissions_creates_missing_directory(self, tmp_path):
        """Test that function creates directory if it doesn't exist."""
        test_dir = tmp_path / "new_folder"
        assert not test_dir.exists()
        
        utils.check_write_permissions(str(test_dir))
        
        assert test_dir.exists()
    
    def test_check_write_permissions_exits_on_creation_error(self, monkeypatch):
        """Test that function exits if directory creation fails."""
        from ytrd import errors

        def mock_makedirs(path, *args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(os, 'makedirs', mock_makedirs)
        monkeypatch.setattr(os.path, 'exists', lambda x: False)

        # Теперь выбрасывается YtrdFileError
        with pytest.raises(errors.YtrdFileError):
            utils.check_write_permissions("/invalid/path")

    def test_check_write_permissions_exits_on_no_write_access(self, monkeypatch, tmp_path):
        """Test that function exits if directory is not writable."""
        from ytrd import errors

        test_dir = tmp_path / "readonly"
        test_dir.mkdir()

        # Mock to simulate no write permission
        monkeypatch.setattr(os, 'access', lambda path, mode: False)

        # Теперь выбрасывается YtrdFileError
        with pytest.raises(errors.YtrdFileError):
            utils.check_write_permissions(str(test_dir))


class TestValidateUrl:
    """Test suite for URL validation."""
    
    def test_validate_url_accepts_youtube_urls(self):
        """Test that valid YouTube URLs pass validation."""
        # Should not raise
        utils.validate_url("https://youtube.com/watch?v=test")
        utils.validate_url("https://youtu.be/test")
    
    def test_validate_url_rejects_non_youtube(self, monkeypatch):
        """Test that non-YouTube URLs are rejected."""
        from ytrd import errors

        # Теперь выбрасывается YtrdValidationError
        with pytest.raises(errors.YtrdValidationError):
            utils.validate_url("https://vimeo.com/123456")
