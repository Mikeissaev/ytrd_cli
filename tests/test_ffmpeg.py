import pytest
from ytrd import ffmpeg
from ytrd import config
from unittest.mock import patch, MagicMock


class TestBuildFFmpegCommand:
    """Test suite for FFmpeg command building."""
    
    def test_build_ffmpeg_command_mix_mode(self):
        """Test building command for Mix mode (mode 2)."""
        cmd = ffmpeg.build_ffmpeg_command(mode=2, final_path="out.mp4")
        
        # Check structure
        assert isinstance(cmd, list)
        assert 'out.mp4' in cmd
        
        # Check filter_complex is present
        assert '-filter_complex' in cmd
        idx = cmd.index('-filter_complex')
        filter_str = cmd[idx + 1]
        
        # Verify filter reduces original volume and boosts dub
        assert '[0:a]volume=0.2[orig]' in filter_str
        assert '[1:a]volume=1.2[dub]' in filter_str
        assert 'amix=inputs=2' in filter_str
        
        # Check mapping
        assert '-map' in cmd
        map_out_idx = cmd.index('[out]')
        assert cmd[map_out_idx - 1] == '-map'
        
        # Check video codec is copy
        assert '-c:v' in cmd
        assert 'copy' in cmd[cmd.index('-c:v') + 1]
    
    def test_build_ffmpeg_command_dual_mode(self):
        """Test building command for Dual mode (mode 3)."""
        cmd = ffmpeg.build_ffmpeg_command(mode=3, final_path="out.mp4")
        
        # Check dual audio mapping
        assert cmd.count('-map') >= 3  # Video + 2 audio tracks
        
        # Check metadata for both tracks
        assert any('title=Original' in str(arg) for arg in cmd)
        assert any('title=Русский' in str(arg) for arg in cmd)
        assert any('language=rus' in str(arg) for arg in cmd)
        
        # Check codec is copy (no re-encoding)
        assert '-c' in cmd
        c_idx = cmd.index('-c')
        assert cmd[c_idx + 1] == 'copy'
    
    def test_build_ffmpeg_command_dub_only_mode(self):
        """Test building command for Dub only mode (mode 1)."""
        cmd = ffmpeg.build_ffmpeg_command(mode=1, final_path="out.mp4")
        
        # Check that translation audio is mapped
        assert '-map' in cmd
        
        # Should map video and translation audio
        # -map 0:v (video) and -map 1:a (translation)
        assert '0:v' in cmd
        assert '1:a' in cmd
    
    def test_build_ffmpeg_command_mkv_no_aac_fix(self):
        """Test that MKV files don't get AAC bitstream filter."""
        cmd = ffmpeg.build_ffmpeg_command(mode=3, final_path="out.mkv", is_mkv=True)
        
        # Should NOT have aac_adtstoasc filter for MKV
        assert '-bsf:a:0' not in cmd
        assert 'aac_adtstoasc' not in ' '.join(cmd)
    
    def test_build_ffmpeg_command_mp4_has_aac_fix(self):
        """Test that MP4 files get AAC bitstream filter in Dual mode."""
        cmd = ffmpeg.build_ffmpeg_command(mode=3, final_path="out.mp4", is_mkv=False)
        
        # Should have aac_adtstoasc filter for MP4
        assert '-bsf:a:0' in cmd
        assert 'aac_adtstoasc' in cmd
    
    def test_build_ffmpeg_command_has_faststart(self):
        """Test that all commands include faststart for web playback."""
        for mode in [1, 2, 3]:
            cmd = ffmpeg.build_ffmpeg_command(mode=mode, final_path="out.mp4")
            
            assert '-movflags' in cmd
            movflags_idx = cmd.index('-movflags')
            assert '+faststart' in cmd[movflags_idx + 1]
    
    def test_build_ffmpeg_command_uses_temp_files(self):
        """Test that command uses configured temp filenames."""
        cmd = ffmpeg.build_ffmpeg_command(mode=2, final_path="out.mp4")
        
        # Should reference temp video and audio files
        assert config.TEMP_VIDEO_FILENAME in cmd
        assert config.TEMP_AUDIO_FILENAME in cmd
    
    @pytest.mark.parametrize("mode,expected_codec", [
        (2, 'aac'),  # Mix mode re-encodes to AAC
        (3, 'copy'),  # Dual mode copies streams
    ])
    def test_build_ffmpeg_command_audio_codec(self, mode, expected_codec):
        """Test audio codec selection based on mode."""
        cmd = ffmpeg.build_ffmpeg_command(mode=mode, final_path="out.mp4")
        
        if mode == 2:
            # Mix mode should specify AAC codec
            assert '-c:a' in cmd
            assert 'aac' in cmd[cmd.index('-c:a') + 1]
        else:
            # Dual should copy
            assert 'copy' in cmd


class TestProcessVideoMerge:
    """Test suite for video merging workflow."""
    
    def test_process_video_merge_with_translation(self, monkeypatch):
        """Test merge workflow when translation is available."""
        from ytrd import cli, utils
        
        class MockArgs:
            mix = True
            dual = False
            output = "/downloads"
        
        mock_run_ffmpeg = MagicMock()
        monkeypatch.setattr(ffmpeg, 'run_ffmpeg', mock_run_ffmpeg)
        
        mock_handle_file = MagicMock(side_effect=lambda x: x)
        monkeypatch.setattr(cli, 'handle_existing_file', mock_handle_file)
        
        mock_cleanup = MagicMock()
        monkeypatch.setattr(utils, 'cleanup', mock_cleanup)
        
        # Mock os.path.exists to simulate created file
        monkeypatch.setattr('os.path.exists', lambda x: True)
        
        ffmpeg.process_video_merge(
            current_path="temp_video.mp4",
            ext="mp4",
            translation_success=True,
            uploader="Channel",
            title="Video",
            actual_height=1080,
            args=MockArgs(),
            duration=341.0
        )
        
        # Should call ffmpeg
        mock_run_ffmpeg.assert_called_once()
        
        # Check filename includes [Mix] tag
        call_args = mock_run_ffmpeg.call_args[0]
        cmd_list = call_args[0]
        final_path = cmd_list[-1]
        assert "[Mix]" in final_path
        assert "[1080p]" in final_path
    
    def test_process_video_merge_dual_mode(self, monkeypatch):
        """Test merge workflow in Dual mode."""
        from ytrd import cli, utils
        
        class MockArgs:
            mix = False
            dual = True
            output = "/downloads"
        
        mock_run_ffmpeg = MagicMock()
        monkeypatch.setattr(ffmpeg, 'run_ffmpeg', mock_run_ffmpeg)
        
        monkeypatch.setattr(cli, 'handle_existing_file', lambda x: x)
        monkeypatch.setattr(utils, 'cleanup', MagicMock())
        monkeypatch.setattr('os.path.exists', lambda x: True)
        
        ffmpeg.process_video_merge(
            "temp_video.mp4", "mp4", True,
            "Channel", "Video", 1080,
            MockArgs(), 341.0
        )
        
        call_args = mock_run_ffmpeg.call_args[0]
        cmd_list = call_args[0]
        final_path = cmd_list[-1]
        
        assert "[Dual]" in final_path
    
    def test_process_video_merge_without_translation(self, monkeypatch):
        """Test workflow when translation failed (just copy original)."""
        from ytrd import cli, utils
        import shutil
        
        class MockArgs:
            output = "/downloads"
        
        mock_copy = MagicMock()
        monkeypatch.setattr(shutil, 'copy', mock_copy)
        
        monkeypatch.setattr(cli, 'handle_existing_file', lambda x: x)
        monkeypatch.setattr(utils, 'cleanup', MagicMock())
        monkeypatch.setattr('os.path.exists', lambda x: True)
        
        ffmpeg.process_video_merge(
            "temp_video.mp4", "mp4", False,
            "Channel", "Video", 1080,
            MockArgs(), 341.0
        )
        
        # Should copy file instead of ffmpeg merge
        mock_copy.assert_called_once()
        call_args = mock_copy.call_args[0]
        assert call_args[0] == "temp_video.mp4"


class TestRunFFmpeg:
    """Test suite for FFmpeg execution."""
    
    def test_run_ffmpeg_success(self, monkeypatch):
        """Test successful FFmpeg execution."""
        import subprocess
        
        # Mock stdout with proper readline method
        class MockStdout:
            def __init__(self):
                self.lines = [
                    "out_time_us=1000000\n",  # 1 second
                    "out_time_us=2000000\n",  # 2 seconds
                ]
                self.index = 0
            
            def readline(self):
                if self.index < len(self.lines):
                    line = self.lines[self.index]
                    self.index += 1
                    return line
                return ""  # EOF
        
        mock_proc = MagicMock()
        mock_proc.stdout = MockStdout()
        mock_proc.poll.return_value = 0
        
        monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: mock_proc)
        
        # Should not raise
        ffmpeg.run_ffmpeg(['ffmpeg', '-i', 'input.mp4', 'output.mp4'], duration=100)
    
    def test_run_ffmpeg_error_exits(self, monkeypatch):
        """Test that FFmpeg errors cause system exit."""
        import subprocess
        
        class MockStdout:
            def __init__(self):
                self.lines = ["Error message\n"]
                self.index = 0
            
            def readline(self):
                if self.index < len(self.lines):
                    line = self.lines[self.index]
                    self.index += 1
                    return line
                return ""
        
        mock_proc = MagicMock()
        mock_proc.stdout = MockStdout()
        mock_proc.poll.return_value = 1  # Error code
        
        monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: mock_proc)
        
        from ytrd import utils
        mock_cleanup = MagicMock()
        monkeypatch.setattr(utils, 'cleanup', mock_cleanup)
        
        with pytest.raises(SystemExit) as exc_info:
            ffmpeg.run_ffmpeg(['ffmpeg'], duration=100)
        
        assert exc_info.value.code == 1
        mock_cleanup.assert_called_with(error=True)
