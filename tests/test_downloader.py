import pytest
import yt_dlp
import requests
from ytrd import downloader
from ytrd import config
from unittest.mock import MagicMock, Mock, patch
import os


class TestDownloadVideo:
    """Test suite for video downloading functionality."""
    
    def test_download_video_success(self, mock_youtube_dl_success, monkeypatch):
        """Test successful video download with proper mocks."""
        # Mock file existence check
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr(os.path, 'getsize', lambda x: 10485760)  # 10MB
        
        duration, height, path = downloader.download_video(
            "https://youtu.be/test", 
            "temp_video.mp4", 
            1080
        )
        
        assert duration == 341.0
        assert height == 1080
        assert path == "temp_video.mp4"
        
        # Verify extract_info was called
        mock_youtube_dl_success.extract_info.assert_called_once_with(
            "https://youtu.be/test",
            download=True
        )
    
    def test_download_video_format_selection_1080p(self, monkeypatch, mock_ydl_video_info):
        """Test that 1080p uses correct format string (H.264 preferred)."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_ydl_video_info
        
        from contextlib import contextmanager
        
        captured_opts = {}
        
        @contextmanager
        def mock_ydl_context(opts):
            captured_opts.update(opts)
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr(os.path, 'getsize', lambda x: 1024)
        
        downloader.download_video("url", "path.mp4", 1080)
        
        # Should prioritize H.264 (avc) codec
        assert 'format' in captured_opts
        assert 'avc' in captured_opts['format']
        assert captured_opts['merge_output_format'] == 'mp4'
    
    def test_download_video_high_res_uses_mkv(self, monkeypatch, mock_ydl_video_info):
        """Test that 4K/2K videos use MKV container."""
        mock_ydl_instance = MagicMock()
        mock_ydl_video_info_4k = mock_ydl_video_info.copy()
        mock_ydl_video_info_4k['height'] = 2160
        mock_ydl_instance.extract_info.return_value = mock_ydl_video_info_4k
        
        from contextlib import contextmanager
        
        captured_opts = {}
        
        @contextmanager
        def mock_ydl_context(opts):
            captured_opts.update(opts)
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr(os.path, 'getsize', lambda x: 1024)
        
        duration, height, path = downloader.download_video("url", "temp_video.mp4", 2160)
        
        assert path.endswith('.mkv')
        assert captured_opts['merge_output_format'] == 'mkv'
    
    def test_download_video_network_error_retry(self, mock_youtube_dl_error, monkeypatch):
        """Test retry logic on download error."""
        # Mock callback to reject retry
        mock_callback = MagicMock(return_value=False)
        
        with pytest.raises(SystemExit) as exc_info:
            downloader.download_video(
                "url",
                "path.mp4",
                quality_height=1080,
                retry_callback=mock_callback
            )
        
        assert exc_info.value.code == 1
        mock_callback.assert_called_once()
    
    def test_download_video_critical_error_416(self, monkeypatch):
        """Test handling of critical 416 error with cleanup."""
        from ytrd import utils
        
        mock_ydl_instance = MagicMock()
        # First call: 416 error
        # Second call: success after cleanup
        mock_ydl_instance.extract_info.side_effect = [
            yt_dlp.utils.DownloadError("HTTP Error 416: Range Not Satisfiable"),
            {'duration': 100, 'height': 1080}
        ]
        
        from contextlib import contextmanager
        
        @contextmanager
        def mock_ydl_context(*args, **kwargs):
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        # Mock callback to accept cleanup retry
        mock_callback = MagicMock(return_value=True)
        
        mock_clean = MagicMock()
        monkeypatch.setattr(utils, 'clean_video_partials', mock_clean)
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr(os.path, 'getsize', lambda x: 1024)
        
        duration, height, path = downloader.download_video(
            "url",
            "path.mp4",
            retry_callback=mock_callback
        )
        
        # Should have cleaned partials
        mock_clean.assert_called_once()
        assert duration == 100
    
    def test_download_video_file_exists_after_error(self, monkeypatch):
        """Test that valid file is returned even if yt-dlp crashes during post-processing."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Post-processing error")
        
        from contextlib import contextmanager
        
        @contextmanager
        def mock_ydl_context(*args, **kwargs):
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        # Mock file exists and has reasonable size
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr(os.path, 'getsize', lambda x: 5242880)  # 5MB
        
        duration, height, path = downloader.download_video("url", "path.mp4")
        
        # Should return success because file exists
        assert path == "path.mp4"


class TestDownloadAudio:
    """Test suite for audio downloading functionality."""
    
    def test_download_audio_success(self, monkeypatch):
        """Test successful translation audio download."""
        mock_response = MagicMock()
        mock_response.headers = {'content-length': '1024000'}
        mock_response.iter_content = lambda size: [b'chunk'] * 10
        
        monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: mock_response)
        
        # Mock file operations
        written_data = []
        
        class MockFile:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def write(self, data):
                written_data.append(data)
        
        monkeypatch.setattr('builtins.open', lambda *args, **kwargs: MockFile())
        
        # Should not raise
        downloader.download_audio("http://test.mp3", "output.mp3")
        
        assert len(written_data) == 10
    
    def test_download_audio_network_error_retry(self, monkeypatch):
        """Test retry on network error."""
        mock_callback = MagicMock(return_value=False)
        
        def mock_get(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Network error")
        
        monkeypatch.setattr(requests, 'get', mock_get)
        
        with pytest.raises(SystemExit):
            downloader.download_audio("url", "path.mp3", retry_callback=mock_callback)
        
        mock_callback.assert_called_once()


class TestGetAvailableQualities:
    """Test suite for quality detection."""
    
    def test_get_available_qualities(self, mock_youtube_dl_success, mock_ydl_video_info):
        """Test collecting available video qualities."""
        qualities, title, uploader, duration, language = downloader.get_available_qualities(
            "https://youtu.be/test"
        )
        
        assert title == "Test Video Title"
        assert uploader == "Test Channel"
        assert duration == 341.0
        assert language == "en"
        
        # Should extract heights from formats
        assert 1080 in qualities
        assert 720 in qualities
        assert 480 in qualities
    
    def test_get_available_qualities_filters_low_res(self, monkeypatch, mock_ydl_video_info):
        """Test that resolutions below 144p are filtered out."""
        mock_ydl_instance = MagicMock()
        
        # Add low-res format
        info_with_low_res = mock_ydl_video_info.copy()
        info_with_low_res['formats'] = [
            {'height': 1080, 'vcodec': 'avc1'},
            {'height': 144, 'vcodec': 'avc1'},  # Should be filtered
            {'height': 720, 'vcodec': 'avc1'},
        ]
        
        mock_ydl_instance.extract_info.return_value = info_with_low_res
        
        from contextlib import contextmanager
        
        @contextmanager
        def mock_ydl_context(*args, **kwargs):
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        qualities, *rest = downloader.get_available_qualities("url")
        
        assert 144 not in qualities
        assert 1080 in qualities
        assert 720 in qualities
    
    def test_get_available_qualities_filters_audio_only(self, monkeypatch, mock_ydl_video_info):
        """Test that audio-only formats (vcodec=none) are filtered."""
        mock_ydl_instance = MagicMock()
        
        info_with_audio = mock_ydl_video_info.copy()
        info_with_audio['formats'] = [
            {'height': 1080, 'vcodec': 'avc1'},
            {'height': None, 'vcodec': 'none'},  # Audio only
            {'height': 720, 'vcodec': 'avc1'},
        ]
        
        mock_ydl_instance.extract_info.return_value = info_with_audio
        
        from contextlib import contextmanager
        
        @contextmanager
        def mock_ydl_context(*args, **kwargs):
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        qualities, *rest = downloader.get_available_qualities("url")
        
        # Should only have video formats
        assert len(qualities) == 2


class TestProcessAudioOnly:
    """Test suite for audio-only workflow."""
    
    def test_process_audio_only_skip_translation(self, monkeypatch):
        """Test downloading original audio when translation is skipped."""
        from ytrd import utils
        
        class MockArgs:
            output = "/downloads"
        
        mock_download = MagicMock(return_value=True)
        monkeypatch.setattr(downloader, 'download_youtube_audio', mock_download)
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(utils, 'cleanup', mock_cleanup)
        
        mock_file_callback = MagicMock(side_effect=lambda x: x)
        
        downloader.process_audio_only(
            "url",
            MockArgs(),
            skip_translation=True,
            translation_success=False,
            uploader="Channel",
            title="Video",
            file_exists_callback=mock_file_callback
        )
        
        # Should download YouTube audio
        mock_download.assert_called_once()
        call_args = mock_download.call_args[0]
        assert call_args[0] == "url"
        assert "[Original]" in call_args[1]
        
        mock_cleanup.assert_called_once()
    
    def test_process_audio_only_with_translation(self, monkeypatch):
        """Test saving translation audio."""
        from ytrd import utils
        import shutil
        
        class MockArgs:
            output = "/downloads"
        
        mock_copy = MagicMock()
        monkeypatch.setattr(shutil, 'copy', mock_copy)
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(utils, 'cleanup', mock_cleanup)
        
        mock_file_callback = MagicMock(side_effect=lambda x: x)
        
        downloader.process_audio_only(
            "url",
            MockArgs(),
            skip_translation=False,
            translation_success=True,
            uploader="Channel",
            title="Video",
            file_exists_callback=mock_file_callback
        )
        
        # Should copy temp audio file
        mock_copy.assert_called_once()
        call_args = mock_copy.call_args[0]
        assert call_args[0] == config.TEMP_AUDIO_FILENAME
        assert "[AudioTranslation]" in call_args[1]


class TestDownloadYoutubeAudio:
    """Test suite for YouTube audio extraction."""
    
    def test_download_youtube_audio_success(self, monkeypatch):
        """Test successful audio extraction with FFmpeg postprocessor."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.download.return_value = None  # Success
        
        from contextlib import contextmanager
        
        captured_opts = {}
        
        @contextmanager
        def mock_ydl_context(opts):
            captured_opts.update(opts)
            yield mock_ydl_instance
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        result = downloader.download_youtube_audio("url", "output.mp3")
        
        assert result is True
        
        # Check postprocessor is configured
        assert 'postprocessors' in captured_opts
        postproc = captured_opts['postprocessors'][0]
        assert postproc['key'] == 'FFmpegExtractAudio'
        assert postproc['preferredcodec'] == 'mp3'
    
    def test_download_youtube_audio_error(self, monkeypatch):
        """Test handling of download errors."""
        def mock_ydl_context(*args, **kwargs):
            raise Exception("Download failed")
        
        monkeypatch.setattr(yt_dlp, 'YoutubeDL', mock_ydl_context)
        
        result = downloader.download_youtube_audio("url", "output.mp3")
        
        assert result is False
