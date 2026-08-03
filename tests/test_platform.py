"""Тесты для модуля platform.py."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from ytrd import platform


class TestDetectPlatform:
    """Тесты определения платформы."""

    @patch('sys.platform', 'win32')
    def test_detect_platform_windows(self):
        assert platform.detect_platform() == platform.Platform.WINDOWS

    @patch('sys.platform', 'darwin')
    def test_detect_platform_macos(self):
        assert platform.detect_platform() == platform.Platform.MACOS

    @patch('sys.platform', 'linux')
    @patch('os.path.exists')
    def test_detect_platform_termux(self, mock_exists):
        mock_exists.return_value = True
        assert platform.detect_platform() == platform.Platform.ANDROID_TERMUX

    @patch('sys.platform', 'linux')
    @patch('os.path.exists')
    def test_detect_platform_linux(self, mock_exists):
        mock_exists.return_value = False
        assert platform.detect_platform() == platform.Platform.LINUX

    @patch('sys.platform', 'unknown')
    def test_detect_platform_unknown(self):
        assert platform.detect_platform() == platform.Platform.UNKNOWN


class TestGetDefaultOutputDir:
    """Тесты получения пути к папке загрузок."""

    @patch('ytrd.platform.detect_platform')
    @patch('os.access')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_get_default_output_dir_termux_youtube(self, mock_makedirs, mock_exists, mock_access, mock_detect):
        mock_detect.return_value = platform.Platform.ANDROID_TERMUX
        # Мокаем os.path.exists чтобы возвращал True для /sdcard/Download/Youtube
        mock_exists.side_effect = lambda p: p == '/sdcard/Download/Youtube'
        mock_access.return_value = True

        result = platform.get_default_output_dir()
        assert result == Path('/sdcard/Download/Youtube')

    @patch('ytrd.platform.detect_platform')
    @patch('os.access')
    @patch('os.path.exists')
    def test_get_default_output_dir_termux_sdcard(self, mock_exists, mock_access, mock_detect):
        mock_detect.return_value = platform.Platform.ANDROID_TERMUX
        # Мокаем os.path.exists так, чтобы Youtube не существовал, а Download существовал
        def exists_side_effect(p):
            if p == '/sdcard/Download/Youtube': return False
            if p == '/sdcard/Download': return True
            return False
            
        mock_exists.side_effect = exists_side_effect
        mock_access.return_value = True

        result = platform.get_default_output_dir()
        assert result == Path('/sdcard/Download')

    @patch('ytrd.platform.detect_platform')
    @patch('os.access')
    @patch('os.path.exists')
    def test_get_default_output_dir_termux_emulated(self, mock_exists, mock_access, mock_detect):
        mock_detect.return_value = platform.Platform.ANDROID_TERMUX
        # sdcard не существует, но существует emulated
        mock_exists.side_effect = lambda p: p == '/storage/emulated/0/Download'
        mock_access.return_value = True

        result = platform.get_default_output_dir()
        assert result == Path('/storage/emulated/0/Download')

    @patch('ytrd.platform.detect_platform')
    @patch('os.access')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_get_default_output_dir_termux_fallback(self, mock_makedirs, mock_exists, mock_access, mock_detect):
        mock_detect.return_value = platform.Platform.ANDROID_TERMUX
        # Ничего не существует
        mock_exists.return_value = False
        mock_access.return_value = True

        result = platform.get_default_output_dir()
        # Должен попробовать создать Youtube папку и затем fallback
        assert mock_makedirs.call_count >= 2
        assert result == Path.home() / 'downloads'

    @patch('ytrd.platform.detect_platform')
    @patch('os.path.exists')
    def test_get_default_output_dir_windows(self, mock_exists, mock_detect):
        mock_detect.return_value = platform.Platform.WINDOWS
        mock_exists.return_value = True

        result = platform.get_default_output_dir()
        assert result == Path.home() / 'Downloads'

    @patch('ytrd.platform.detect_platform')
    @patch('os.path.exists')
    def test_get_default_output_dir_linux(self, mock_exists, mock_detect):
        mock_detect.return_value = platform.Platform.LINUX
        mock_exists.return_value = True

        result = platform.get_default_output_dir()
        assert result == Path.home() / 'Downloads'

    @patch('ytrd.platform.detect_platform')
    @patch('os.path.exists')
    def test_get_default_output_dir_linux_russian(self, mock_exists, mock_detect):
        mock_detect.return_value = platform.Platform.LINUX
        # Downloads не существует, но существует Загрузки
        def exists_side_effect(p):
            if 'Downloads' in p:
                return False
            if 'Загрузки' in p:
                return True
            return True

        mock_exists.side_effect = exists_side_effect

        result = platform.get_default_output_dir()
        assert result == Path.home() / 'Загрузки'


class TestGetBinaryPath:
    """Тесты поиска исполняемых файлов."""

    @patch('shutil.which')
    def test_get_binary_path_found_in_path(self, mock_which):
        mock_which.return_value = '/usr/bin/ffmpeg'

        result = platform.get_binary_path('ffmpeg')
        assert result == Path('/usr/bin/ffmpeg')

    @patch('shutil.which')
    def test_get_binary_path_not_found(self, mock_which):
        mock_which.return_value = None

        result = platform.get_binary_path('nonexistent')
        assert result is None

    @patch('ytrd.platform.detect_platform')
    @patch('shutil.which')
    @patch('os.path.exists')
    def test_get_binary_path_termux_fallback(self, mock_exists, mock_which, mock_detect):
        mock_detect.return_value = platform.Platform.ANDROID_TERMUX
        mock_which.return_value = None
        # Существует в Termux bin
        mock_exists.side_effect = lambda p: 'termux' in p

        result = platform.get_binary_path('ffmpeg')
        assert result is not None
        assert 'termux' in str(result)


class TestEnsureWritePermission:
    """Тесты проверки прав записи."""

    @patch('os.access')
    @patch('os.path.exists')
    def test_ensure_write_permission_existing_dir(self, mock_exists, mock_access):
        mock_exists.return_value = True
        mock_access.return_value = True

        result = platform.ensure_write_permission(Path('/tmp/test'))
        assert result is True

    @patch('os.access')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_ensure_write_permission_creates_dir(self, mock_makedirs, mock_exists, mock_access):
        mock_exists.return_value = False
        mock_access.return_value = True

        result = platform.ensure_write_permission(Path('/tmp/test'))
        assert result is True
        mock_makedirs.assert_called_once_with('/tmp/test', exist_ok=True)

    @patch('os.access')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_ensure_write_permission_mkdir_fails(self, mock_makedirs, mock_exists, mock_access):
        mock_exists.return_value = False
        mock_makedirs.side_effect = OSError("Permission denied")

        with pytest.raises(OSError, match="Не удалось создать папку"):
            platform.ensure_write_permission(Path('/tmp/test'))

    @patch('os.access')
    @patch('os.path.exists')
    def test_ensure_write_permission_no_write_access(self, mock_exists, mock_access):
        mock_exists.return_value = True
        mock_access.return_value = False

        result = platform.ensure_write_permission(Path('/tmp/test'))
        assert result is False


class TestGlobalVariables:
    """Тесты глобальных переменных модуля."""

    def test_is_termux_global(self):
        # Глобальные флаги вычисляются при импорте модуля, поэтому
        # необходимо замокать условия, которые использует detect_platform().
        import importlib

        with patch('sys.platform', 'linux'), patch('os.path.exists', return_value=True):
            importlib.reload(platform)
            assert platform.IS_TERMUX is True
            assert platform.CURRENT_PLATFORM == platform.Platform.ANDROID_TERMUX

        # Восстанавливаем глобальные значения для следующих тестов.
        importlib.reload(platform)

    @patch('ytrd.platform.detect_platform')
    def test_termux_constants(self, mock_detect):
        assert platform.TERMUX_PREFIX_PATH == "/data/data/com.termux/files/usr"
        assert "bin" in platform.TERMUX_BIN_PATH


class TestPlatformEnum:
    """Тесты перечисления Platform."""

    def test_platform_enum_values(self):
        assert platform.Platform.ANDROID_TERMUX.value == "android_termux"
        assert platform.Platform.WINDOWS.value == "windows"
        assert platform.Platform.LINUX.value == "linux"
        assert platform.Platform.MACOS.value == "macos"
        assert platform.Platform.UNKNOWN.value == "unknown"

    def test_platform_enum_members(self):
        assert len(platform.Platform) == 5
        assert platform.Platform.ANDROID_TERMUX in platform.Platform
        assert platform.Platform.WINDOWS in platform.Platform
        assert platform.Platform.LINUX in platform.Platform
        assert platform.Platform.MACOS in platform.Platform
        assert platform.Platform.UNKNOWN in platform.Platform
