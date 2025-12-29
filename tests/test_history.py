import os
import json
import pytest
from unittest.mock import MagicMock
from ytrd import history
from ytrd import config

class TestHistory:
    """Test suite for history management module."""

    @pytest.fixture
    def mock_history_file(self, tmp_path, monkeypatch):
        """Creates a temporary history file and mocks the config path."""
        p = tmp_path / "test_history.json"
        monkeypatch.setattr(config, 'HISTORY_FILE_PATH', str(p))
        return p

    def test_load_history_empty(self, mock_history_file):
        """Test loading when file does not exist."""
        assert history.load_history() == []

    def test_load_history_exists(self, mock_history_file):
        """Test loading existing history."""
        data = ["http://url1", "http://url2"]
        with open(mock_history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        
        loaded = history.load_history()
        assert loaded == data

    def test_load_history_corrupted(self, mock_history_file):
        """Test loading corrupted JSON file."""
        with open(mock_history_file, 'w', encoding='utf-8') as f:
            f.write("{invalid_json")
        
        assert history.load_history() == []

    def test_save_history(self, mock_history_file):
        """Test saving history to file."""
        data = ["http://url1"]
        history.save_history(data)
        
        assert os.path.exists(mock_history_file)
        with open(mock_history_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        assert loaded == data

    def test_add_to_history(self, mock_history_file):
        """Test adding a new URL to history."""
        url = "http://new_url"
        history.add_to_history(url)
        
        assert history.is_in_history(url)
        
        # Add duplicate, should remain single entry
        history.add_to_history(url)
        loaded = history.load_history()
        assert len(loaded) == 1
        assert loaded[0] == url

    def test_is_in_history(self, mock_history_file):
        """Test checking if URL is in history."""
        url = "http://exists"
        history.add_to_history(url)
        
        assert history.is_in_history(url)
        assert not history.is_in_history("http://not_exists")

    def test_clear_history(self, mock_history_file, capsys):
        """Test clearing history."""
        history.add_to_history("http://url")
        assert os.path.exists(mock_history_file)
        
        history.clear_history()
        
        assert not os.path.exists(mock_history_file)
        captured = capsys.readouterr()
        assert "История скачиваний очищена" in captured.out

    def test_clear_history_empty(self, mock_history_file, capsys):
        """Test clearing empty history."""
        if os.path.exists(mock_history_file):
            os.remove(mock_history_file)
            
        history.clear_history()
        
        captured = capsys.readouterr()
        assert "История уже пуста" in captured.out
