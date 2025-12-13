import pytest
from ytrd import config
import os


class TestConfigConstants:
    """Test suite for configuration constants."""
    
    def test_retry_parameters_exist_and_valid(self):
        """Test that retry parameters exist and have reasonable values."""
        assert hasattr(config, 'RETRY_ATTEMPTS')
        assert hasattr(config, 'RETRY_FRAGMENTS')
        assert hasattr(config, 'RETRY_SLEEP_SECONDS')
        
        # Check values are within reasonable bounds
        assert 1 <= config.RETRY_ATTEMPTS <= 100, "RETRY_ATTEMPTS should be between 1 and 100"
        assert 1 <= config.RETRY_FRAGMENTS <= 100, "RETRY_FRAGMENTS should be between 1 and 100"
        assert 1 <= config.RETRY_SLEEP_SECONDS <= 60, "RETRY_SLEEP_SECONDS should be between 1 and 60"
    
    def test_temp_filenames_are_strings(self):
        """Test that temporary filenames are non-empty strings."""
        assert isinstance(config.TEMP_VIDEO_FILENAME, str)
        assert isinstance(config.TEMP_AUDIO_FILENAME, str)
        assert len(config.TEMP_VIDEO_FILENAME) > 0
        assert len(config.TEMP_AUDIO_FILENAME) > 0
        
        # Check extensions
        assert config.TEMP_VIDEO_FILENAME.endswith('.mp4')
        assert config.TEMP_AUDIO_FILENAME.endswith('.mp3')
    
    def test_color_codes_are_ansi_sequences(self):
        """Test that color codes are valid ANSI escape sequences."""
        colors = [
            config.COLOR_RED,
            config.COLOR_GREEN,
            config.COLOR_YELLOW,
            config.COLOR_CYAN,
            config.COLOR_RESET
        ]
        
        for color in colors:
            assert isinstance(color, str)
            assert color.startswith("\033["), f"Color code {color!r} should start with ANSI escape"
            assert len(color) > 3


class TestTermuxConfiguration:
    """Test suite for Termux-specific configuration."""
    
    def test_termux_paths_structure(self):
        """Test that Termux paths follow expected structure."""
        assert "com.termux" in config.TERMUX_PREFIX_PATH
        assert config.TERMUX_BIN_PATH.endswith("bin")
        assert config.TERMUX_PREFIX_PATH in config.TERMUX_BIN_PATH
    
    def test_termux_prefix_is_absolute(self):
        """Test that Termux prefix is an absolute Unix path."""
        # Termux uses Unix paths which start with /
        # os.path.isabs() doesn't work on Windows for Unix paths
        assert config.TERMUX_PREFIX_PATH.startswith("/"), \
            "Termux prefix should be an absolute Unix path starting with /"


class TestProgressBarFormats:
    """Test suite for progress bar format strings."""
    
    def test_progress_bar_format_contains_required_placeholders(self):
        """Test that progress bar formats contain required placeholders."""
        # Standard format should have bar, labels, and stats
        assert "{l_bar}" in config.PROGRESS_BAR_FORMAT
        assert "{bar}" in config.PROGRESS_BAR_FORMAT
        assert "{n_fmt}" in config.PROGRESS_BAR_FORMAT
        assert "{total_fmt}" in config.PROGRESS_BAR_FORMAT
    
    def test_time_format_has_time_unit(self):
        """Test that time-based format has seconds indicator."""
        assert "{l_bar}" in config.PROGRESS_BAR_TIME_FORMAT
        assert "{bar}" in config.PROGRESS_BAR_TIME_FORMAT
        # Should show time in seconds
        assert "s" in config.PROGRESS_BAR_TIME_FORMAT or "{n_fmt}" in config.PROGRESS_BAR_TIME_FORMAT


class TestVOTConfiguration:
    """Test suite for Voice Over Translation (VOT) API configuration."""
    
    def test_hmac_key_is_bytes(self):
        """Test that HMAC key is bytes and has reasonable length."""
        assert isinstance(config.VOT_HMAC_KEY, bytes)
        assert len(config.VOT_HMAC_KEY) >= 16, "HMAC key should be at least 16 bytes for security"
    
    def test_user_agent_is_valid(self):
        """Test that HTTP User-Agent is non-empty and looks valid."""
        assert isinstance(config.HTTP_USER_AGENT, str)
        assert len(config.HTTP_USER_AGENT) > 0
        # Should contain browser identifier
        assert any(browser in config.HTTP_USER_AGENT for browser in ['Mozilla', 'Chrome', 'Safari'])

