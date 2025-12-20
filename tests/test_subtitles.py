import pytest
from unittest.mock import MagicMock, call
import sys
import os
from ytrd import cli, downloader, ffmpeg, config

def test_cli_subtitles_arg():
    """Test that -s/--subtitles argument is parsed correctly."""
    # Test short flag
    with pytest.MonkeyPatch.context() as m:
        m.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/123', '-s'])
        args = cli.parse_arguments()
        assert args.subtitles is True
    
    # Test long flag
    with pytest.MonkeyPatch.context() as m:
        m.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/123', '--subtitles'])
        args = cli.parse_arguments()
        assert args.subtitles is True

    # Test default
    with pytest.MonkeyPatch.context() as m:
        m.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/123'])
        args = cli.parse_arguments()
        assert args.subtitles is False

def test_download_subtitles_options(monkeypatch):
    """Test that download_subtitles passes correct options to yt-dlp."""
    import yt_dlp
    
    spy_opts = {}
    
    class MockYDL:
        def __init__(self, opts):
            nonlocal spy_opts
            spy_opts = opts
            
        def __enter__(self):
            return self
            
        def __exit__(self, *args):
            pass
            
        def extract_info(self, url, download=True):
            return {}
            
        def download(self, urls):
            pass

    monkeypatch.setattr(yt_dlp, 'YoutubeDL', MockYDL)
    
    # Mock os.path.exists to simulate successful download of Russian subs
    # and fail check for cookies file
    def mock_exists(path):
        if path == config.COOKIES_FILE_PATH:
            return False
        if "ru.vtt" in path:
            return True
        return False
        
    monkeypatch.setattr(os.path, 'exists', mock_exists)
    
    downloader.download_subtitles("http://test", "base_path")
    
    # Check key options for subtitle download
    assert spy_opts.get('skip_download') is True
    assert spy_opts.get('writesubtitles') is True
    assert spy_opts.get('writeautomaticsub') is True
    # Should try 'ru' first and succeed (so last opts are ru)
    assert spy_opts.get('subtitleslangs') == ['ru']

def test_ffmpeg_command_subtitles(monkeypatch):
    """Test building ffmpeg command with subtitles."""
    # Mock get_binary_path
    monkeypatch.setattr(downloader.utils, 'get_binary_path', lambda x: 'ffmpeg')
    
    # 1. Test MP4 (needs mov_text)
    cmd = ffmpeg.build_ffmpeg_command(
        mode=2, 
        final_path="output.mp4", 
        is_mkv=False, 
        sub_path="sub.vtt"
    )
    
    # Check input
    assert "sub.vtt" in cmd
    idx = cmd.index("sub.vtt")
    assert cmd[idx-1] == "-i"
    
    # Check mappings
    assert "-map" in cmd
    assert "2:s" in cmd
    
    # Check codec for MP4
    assert "-c:s" in cmd
    idx_cs = cmd.index("-c:s")
    assert cmd[idx_cs+1] == "mov_text"
    
    # Check metadata
    assert "language=rus" in cmd
    
    # 2. Test MKV (supports srt)
    cmd_mkv = ffmpeg.build_ffmpeg_command(
        mode=2, 
        final_path="output.mkv", 
        is_mkv=True, 
        sub_path="sub.srt"
    )
    
    assert "-c:s" in cmd_mkv
    idx_cs = cmd_mkv.index("-c:s")
    assert cmd_mkv[idx_cs+1] == "srt"
