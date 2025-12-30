import pytest
import sys
import os
from ytrd import cli
from ytrd import config
from ytrd import utils


class TestAskYesNo:
    """Test suite for yes/no prompts."""
    
    def test_ask_yes_no_accepts_yes(self, mock_yes_input):
        """Test that 'y' returns True."""
        # input() doesn't write to stdout, so no capsys check
        assert cli.ask_yes_no("Question") is True
    
    def test_ask_yes_no_accepts_no(self, mock_no_input):
        """Test that 'n' returns False."""
        assert cli.ask_yes_no("Question") is False
    
    @pytest.mark.parametrize("user_input,expected", [
        ('y', True),
        ('yes', True),
        ('д', True),   # Russian 'yes'
        ('да', True),  # Russian 'yes'
        ('n', False),
        ('no', False),
        ('н', False),  # Russian 'no'
        ('нет', False), # Russian 'no'
    ])
    def test_ask_yes_no_multilingual(self, monkeypatch, user_input, expected):
        """Test that function accepts both English and Russian responses."""
        monkeypatch.setattr('builtins.input', lambda _: user_input)
        assert cli.ask_yes_no("Test") is expected
    
    def test_ask_yes_no_keyboard_interrupt(self, monkeypatch):
        """Test that KeyboardInterrupt returns False."""
        def mock_input_interrupt(_):
            raise KeyboardInterrupt()
        
        monkeypatch.setattr('builtins.input', mock_input_interrupt)
        # Should handle gracefully and return False
        result = cli.ask_yes_no("Test")
        assert result is False


class TestAskMergeMode:
    """Test suite for merge mode selection."""
    
    def test_ask_merge_mode_mix(self, monkeypatch):
        """Test selecting Mix mode (option 1)."""
        monkeypatch.setattr('builtins.input', lambda _: '1')
        assert cli.ask_merge_mode() == 2  # Mix mode
    
    def test_ask_merge_mode_dual(self, monkeypatch):
        """Test selecting Dual mode (option 2)."""
        monkeypatch.setattr('builtins.input', lambda _: '2')
        assert cli.ask_merge_mode() == 3  # Dual mode
    
    def test_ask_merge_mode_default(self, monkeypatch):
        """Test default selection (empty input)."""
        monkeypatch.setattr('builtins.input', lambda _: '')
        assert cli.ask_merge_mode() == 2  # Default is Mix


class TestParseArguments:
    """Test suite for command-line argument parsing."""
    
    def test_parse_arguments_defaults(self, monkeypatch):
        """Test parsing with only URL provided."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID'])
        args = cli.parse_arguments()
        
        assert args.url == 'https://youtu.be/ID'
        assert args.mix is False
        assert args.dual is False
        assert args.audio is False
        assert args.quality is None
        assert args.output == utils.get_default_output_dir()
    
    def test_parse_arguments_mix_mode(self, monkeypatch):
        """Test --mix flag."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID', '--mix'])
        args = cli.parse_arguments()
        
        assert args.mix is True
        assert args.dual is False
    
    def test_parse_arguments_dual_mode(self, monkeypatch):
        """Test --dual flag."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID', '--dual'])
        args = cli.parse_arguments()
        
        assert args.dual is True
        assert args.mix is False
    
    def test_parse_arguments_audio_mode(self, monkeypatch):
        """Test --audio flag."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID', '-a'])
        args = cli.parse_arguments()
        
        assert args.audio is True
        assert args.mix is False
    
    def test_parse_arguments_quality(self, monkeypatch):
        """Test --quality argument."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID', '-q', '1080'])
        args = cli.parse_arguments()
        
        assert args.quality == 1080
    
    def test_parse_arguments_custom_output(self, monkeypatch):
        """Test --output argument."""
        monkeypatch.setattr(sys, 'argv', ['ytrd', 'https://youtu.be/ID', '-o', '/custom/path'])
        args = cli.parse_arguments()
        
        assert args.output == '/custom/path'
    
    def test_parse_arguments_no_url(self, monkeypatch):
        """Test parsing without URL (interactive mode)."""
        monkeypatch.setattr(sys, 'argv', ['ytrd'])
        args = cli.parse_arguments()
        
        assert args.url is None


class TestValidateArgsCompatibility:
    """Test suite for argument compatibility validation."""
    
    def test_validate_args_mix_and_dual_conflict(self, capsys):
        """Test that conflicting --mix and --dual are reset."""
        class MockArgs:
            mix = True
            dual = True
            audio = False
            quality = None
        
        args = MockArgs()
        cli.validate_args_compatibility(args)
        
        assert args.mix is False
        assert args.dual is False
        
        captured = capsys.readouterr()
        assert "конфликт" in captured.out.lower()
    
    def test_validate_args_audio_with_video_options(self, capsys):
        """Test that --audio with video options are reset."""
        class MockArgs:
            mix = False
            dual = True
            audio = True
            quality = 1080
        
        args = MockArgs()
        cli.validate_args_compatibility(args)
        
        assert args.audio is False
        assert args.dual is False
        assert args.quality is None
        
        captured = capsys.readouterr()
        assert "конфликт" in captured.out.lower()
    
    def test_validate_args_no_conflicts(self):
        """Test that valid arguments pass without changes."""
        class MockArgs:
            mix = True
            dual = False
            audio = False
            quality = 1080
        
        args = MockArgs()
        original_mix = args.mix
        original_quality = args.quality
        
        cli.validate_args_compatibility(args)
        
        assert args.mix == original_mix
        assert args.quality == original_quality


class TestHandleExistingFile:
    """Test suite for file conflict resolution."""
    
    def test_handle_existing_file_not_exists(self, monkeypatch):
        """Test that non-existing file path is returned as-is."""
        monkeypatch.setattr(os.path, 'exists', lambda x: False)
        
        result = cli.handle_existing_file("/path/to/file.mp4")
        assert result == "/path/to/file.mp4"
    
    def test_handle_existing_file_replace(self, monkeypatch):
        """Test choosing to replace existing file (option 1)."""
        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr('builtins.input', lambda _: '1')
        
        result = cli.handle_existing_file("/path/to/file.mp4")
        assert result == "/path/to/file.mp4"
    
    def test_handle_existing_file_rename(self, monkeypatch):
        """Test choosing to rename existing file (option 2)."""
        monkeypatch.setattr(os.path, 'exists', lambda x: x == "/path/to/file.mp4")
        monkeypatch.setattr('builtins.input', lambda _: '2')
        
        result = cli.handle_existing_file("/path/to/file.mp4")
        assert result == "/path/to/file (1).mp4"
    
    def test_handle_existing_file_rename_multiple(self, monkeypatch):
        """Test renaming when multiple files already exist."""
        existing_files = {
            "/path/to/file.mp4": True,
            "/path/to/file (1).mp4": True,
            "/path/to/file (2).mp4": True,
        }
        
        monkeypatch.setattr(os.path, 'exists', lambda x: existing_files.get(x, False))
        monkeypatch.setattr('builtins.input', lambda _: '2')
        
        result = cli.handle_existing_file("/path/to/file.mp4")
        assert result == "/path/to/file (3).mp4"
    
    def test_handle_existing_file_cancel(self, monkeypatch, mock_file_operations):
        """Test choosing to cancel (option 3)."""
        from ytrd import errors

        monkeypatch.setattr(os.path, 'exists', lambda x: True)
        monkeypatch.setattr('builtins.input', lambda _: '3')

        # Теперь выбрасывается YtrdUserCancelled вместо SystemExit
        with pytest.raises(errors.YtrdUserCancelled):
            cli.handle_existing_file("/path/to/file.mp4")


class TestGetUserInputAndInfo:


    """Test suite for user input gathering."""


    


    def test_get_user_input_with_url_in_args(self, monkeypatch, mock_youtube_dl_success):


        """Test when URL is provided in arguments."""


        from ytrd import downloader


    


        class MockArgs:


            url = "https://youtu.be/test"


            quality = None


            audio = False


            live = False


            mix = False


            dual = False


    


        # Mock downloader.get_available_qualities


        monkeypatch.setattr(


            downloader,


            'get_available_qualities',


            lambda url: ([1080, 720], "Test Video", "Test Channel", 341.0, "en")


        )


    


        # Mock user selecting quality 1


        monkeypatch.setattr('builtins.input', lambda _: '1')


    


        url, quality, title, uploader, duration, language, use_live, mix, dual = cli.get_user_input_and_info(MockArgs())


        


        assert url == "https://youtu.be/test"


        assert quality == 1080


        assert title == "Test Video"


    


    def test_get_user_input_audio_mode(self, monkeypatch, mock_youtube_dl_success):


        """Test audio-only mode sets quality to 'audio'."""


        from ytrd import downloader


    


        class MockArgs:


            url = "https://youtu.be/test"


            quality = None


            audio = True


            live = False


            mix = False


            dual = False


    


        monkeypatch.setattr(


            downloader,


            'get_available_qualities',


            lambda url: ([1080, 720], "Test", "Ch", 100.0, "en")


        )


    


        url, quality, *rest = cli.get_user_input_and_info(MockArgs())


        


        assert quality == 'audio'
