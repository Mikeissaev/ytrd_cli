import pytest
import sys
from unittest.mock import MagicMock
from ytrd import main
from ytrd import config


class TestRunPipeline:
    """Test suite for main pipeline orchestration."""
    
    def test_run_pipeline_happy_path(self, monkeypatch):
        """Test successful full pipeline execution (video + translation)."""
        # Mock CLI parsing
        mock_args = MagicMock()
        mock_args.url = "http://url"
        mock_args.output = "/downloads"
        mock_args.mix = False
        mock_args.dual = False
        mock_args.audio = False
        mock_args.quality = 1080
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        
        # Mock startup checks
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        monkeypatch.setattr(main.utils, 'cleanup', MagicMock())
        
        # Mock user input
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("http://url", 1080, "Title", "Uploader", 100.0, "en", False)
        )
        
        # Mock VOT (translation)
        mock_get_translation = MagicMock(return_value=True)
        monkeypatch.setattr(main.vot, 'get_translation_audio', mock_get_translation)
        
        # Mock downloader (video)
        mock_download_video = MagicMock(return_value=(100, 1080, "temp_video.mp4"))
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        # Mock subtitle download
        monkeypatch.setattr(main.downloader, 'download_subtitles', lambda url, path, cookies_path=None: ("sub.srt", "rus"))
        
        # Mock FFmpeg (merge)
        mock_process_merge = MagicMock()
        monkeypatch.setattr(main.ffmpeg, 'process_video_merge', mock_process_merge)
        
        main.run_pipeline()
        
        # Verify execution order
        mock_get_translation.assert_called_once()
        mock_download_video.assert_called_once()
        mock_process_merge.assert_called_once()
        
        # Check merge was called with translation_success=True
        merge_args = mock_process_merge.call_args[0]
        assert merge_args[2] is True  # translation_success
    
    def test_run_pipeline_russian_video_skip_translation(self, monkeypatch):
        """Test skipping translation for Russian video when user confirms."""
        mock_args = MagicMock()
        mock_args.audio = False
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        monkeypatch.setattr(main.utils, 'cleanup', MagicMock())
        
        # Language detected as Russian
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 1080, "Title", "Up", 100.0, "Russian", False)
        )
        
        # User says YES (skip translation)
        monkeypatch.setattr(main.cli, 'ask_yes_no', lambda text: True)
        # Mock subtitle error action to skip
        monkeypatch.setattr(main.cli, 'ask_subtitle_error_action', lambda: 'skip')
        
        mock_get_translation = MagicMock()
        monkeypatch.setattr(main.vot, 'get_translation_audio', mock_get_translation)
        
        mock_download_video = MagicMock(return_value=(100, 1080, "temp_video.mp4"))
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        mock_process_merge = MagicMock()
        monkeypatch.setattr(main.ffmpeg, 'process_video_merge', mock_process_merge)
        
        main.run_pipeline()
        
        # Should NOT call translation
        mock_get_translation.assert_not_called()
        
        # Should still download video
        mock_download_video.assert_called_once()
        
        # Merge should be called with translation_success=False
        assert mock_process_merge.call_args[0][2] is False
    
    def test_run_pipeline_russian_video_user_cancels(self, monkeypatch):
        """Test cancellation when user declines to download Russian video."""
        mock_args = MagicMock()
        mock_args.audio = False
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(main.utils, 'cleanup', mock_cleanup)
        
        # Language = Russian
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 1080, "Title", "Up", 100.0, "Russian", False)
        )
        
        # User says NO (don't skip)
        monkeypatch.setattr(main.cli, 'ask_yes_no', lambda text: False)
        
        mock_download_video = MagicMock()
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        main.run_pipeline()
        
        # Should cleanup and exit early
        mock_cleanup.assert_called()
        mock_download_video.assert_not_called()
    
    def test_run_pipeline_audio_only_mode(self, monkeypatch):
        """Test audio-only workflow."""
        mock_args = MagicMock()
        mock_args.audio = False  # Will be set by get_user_input_and_info
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        monkeypatch.setattr(main.utils, 'cleanup', MagicMock())
        
        # Return 'audio' as quality
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 'audio', "Title", "Up", 100.0, "en", False)
        )
        
        mock_get_translation = MagicMock(return_value=True)
        monkeypatch.setattr(main.vot, 'get_translation_audio', mock_get_translation)
        
        mock_process_audio = MagicMock()
        monkeypatch.setattr(main.downloader, 'process_audio_only', mock_process_audio)
        
        mock_download_video = MagicMock()
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        main.run_pipeline()
        
        # Should process audio only
        mock_process_audio.assert_called_once()
        
        # Should NOT download video
        mock_download_video.assert_not_called()
    
    def test_run_pipeline_translation_not_found(self, monkeypatch):
        """Test workflow when translation is not available."""
        mock_args = MagicMock()
        mock_args.audio = False
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        monkeypatch.setattr(main.utils, 'cleanup', MagicMock())
        
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 1080, "Title", "Up", 100.0, "en", False)
        )
        
        # Translation fails
        monkeypatch.setattr(main.vot, 'get_translation_audio', lambda *args, **kwargs: False)
        
        # User agrees to download original
        monkeypatch.setattr(main.cli, 'ask_yes_no', lambda text: True)
        # Mock subtitle error action to skip
        monkeypatch.setattr(main.cli, 'ask_subtitle_error_action', lambda: 'skip')
        
        mock_download_video = MagicMock(return_value=(100, 1080, "temp_video.mp4"))
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        mock_process_merge = MagicMock()
        monkeypatch.setattr(main.ffmpeg, 'process_video_merge', mock_process_merge)
        
        main.run_pipeline()
        
        # Should download video anyway
        mock_download_video.assert_called_once()
        
        # Merge with translation_success=False
        assert mock_process_merge.call_args[0][2] is False
    
    def test_run_pipeline_translation_not_found_user_cancels(self, monkeypatch):
        """Test cancellation when translation not found and user declines original."""
        mock_args = MagicMock()
        mock_args.audio = False
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(main.utils, 'cleanup', mock_cleanup)
        
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 1080, "Title", "Up", 100.0, "en", False)
        )
        
        # Translation fails
        monkeypatch.setattr(main.vot, 'get_translation_audio', lambda *args, **kwargs: False)
        
        # User declines to download original
        monkeypatch.setattr(main.cli, 'ask_yes_no', lambda text: False)
        
        mock_download_video = MagicMock()
        monkeypatch.setattr(main.downloader, 'download_video', mock_download_video)
        
        main.run_pipeline()
        
        # Should cleanup and exit
        mock_cleanup.assert_called()
        mock_download_video.assert_not_called()
    
    @pytest.mark.parametrize("mix,dual,expected_step_label", [
        (True, False, "[3/3]"),   # Mix mode explicitly set
        (False, True, "[3/3]"),   # Dual mode explicitly set
        (False, False, "[3/3]"),  # Interactive (will ask)
    ])
    def test_run_pipeline_different_merge_modes(self, monkeypatch, mix, dual, expected_step_label):
        """Test that different merge modes are passed correctly."""
        mock_args = MagicMock()
        mock_args.mix = mix
        mock_args.dual = dual
        mock_args.audio = False
        
        monkeypatch.setattr(main.cli, 'parse_arguments', lambda: mock_args)
        monkeypatch.setattr(main.utils, 'install_check', MagicMock())
        monkeypatch.setattr(main.utils, 'check_write_permissions', MagicMock())
        monkeypatch.setattr(main.utils, 'cleanup', MagicMock())
        
        monkeypatch.setattr(
            main.cli, 'get_user_input_and_info',
            lambda args: ("url", 1080, "Title", "Up", 100.0, "en", False)
        )
        
        monkeypatch.setattr(main.vot, 'get_translation_audio', lambda *args, **kwargs: True)
        monkeypatch.setattr(main.downloader, 'download_video', lambda *args, **kwargs: (100, 1080, "temp_video.mp4"))
        
        mock_process_merge = MagicMock()
        monkeypatch.setattr(main.ffmpeg, 'process_video_merge', mock_process_merge)
        
        # If interactive, mock ask_merge_mode
        monkeypatch.setattr(main.cli, 'ask_merge_mode', lambda: 2)
        
        # Mock subtitle error action to skip
        monkeypatch.setattr(main.cli, 'ask_subtitle_error_action', lambda: 'skip')
        
        main.run_pipeline()
        
        # Should call merge
        mock_process_merge.assert_called_once()
        
        # Check args.mix and args.dual were passed
        call_kwargs = mock_process_merge.call_args
        args_passed = call_kwargs[0][6]  # args object
        assert hasattr(args_passed, 'mix')
        assert hasattr(args_passed, 'dual')


class TestEntryPoint:
    """Test suite for CLI entry point."""
    
    def test_entry_point_success(self, monkeypatch):
        """Test successful entry point execution."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        mock_run = MagicMock()
        monkeypatch.setattr(main, 'run_pipeline', mock_run)
        
        main.entry_point()
        
        mock_run.assert_called_once()
    
    def test_entry_point_keyboard_interrupt(self, monkeypatch):
        """Test graceful handling of Ctrl+C."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        def mock_run():
            raise KeyboardInterrupt()
        
        monkeypatch.setattr(main, 'run_pipeline', mock_run)
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(main.utils, 'cleanup', mock_cleanup)
        
        with pytest.raises(SystemExit) as exc_info:
            main.entry_point()
        
        assert exc_info.value.code == 0
        mock_cleanup.assert_called()
    
    def test_entry_point_exception(self, monkeypatch, capsys):
        """Test exception handling and error output."""
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        def mock_run():
            raise Exception("Test error")
        
        monkeypatch.setattr(main, 'run_pipeline', mock_run)
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(main.utils, 'cleanup', mock_cleanup)
        
        with pytest.raises(SystemExit) as exc_info:
            main.entry_point()
        
        assert exc_info.value.code == 1
        mock_cleanup.assert_called_with(True)  # cleanup(error=True)
        
        # Check error message was printed
        captured = capsys.readouterr()
        assert "Test error" in captured.out
    
    def test_entry_point_sets_windows_encoding(self, monkeypatch):
        """Test that Windows encoding is configured."""
        monkeypatch.setattr(sys, 'platform', 'win32')
        
        mock_stdout = MagicMock()
        monkeypatch.setattr(sys, 'stdout', mock_stdout)
        
        monkeypatch.setattr(main, 'run_pipeline', MagicMock())
        
        main.entry_point()
        
        # Should call reconfigure on Windows
        mock_stdout.reconfigure.assert_called_once_with(encoding='utf-8')
    
    def test_entry_point_sets_termux_path(self, monkeypatch):
        """Test that Termux paths are added to environment."""
        import os
        
        monkeypatch.setattr(sys, 'platform', 'linux')
        
        original_path = os.environ.get('PATH', '')
        
        monkeypatch.setattr(main, 'run_pipeline', MagicMock())
        
        main.entry_point()
        
        # Should add Termux bin path
        assert config.TERMUX_BIN_PATH in os.environ['PATH']
