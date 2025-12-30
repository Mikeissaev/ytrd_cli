"""Модуль для управления историей скачиваний."""

import json
import os
from typing import List
from . import config


def load_history() -> List[str]:
    """Загружает историю скачиваний из JSON файла.

    Returns:
        Список URL видео, которые были скачаны ранее.
    """
    if not os.path.exists(config.HISTORY_FILE_PATH):
        return []
    try:
        with open(config.HISTORY_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure it's a list
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history: List[str]) -> None:
    """Сохраняет историю скачиваний в JSON файл.

    Args:
        history: Список URL для сохранения.
    """
    try:
        with open(config.HISTORY_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"{config.COLOR_RED}Ошибка сохранения истории: {e}{config.COLOR_RESET}")


def add_to_history(url: str) -> None:
    """Добавляет URL в историю, если его там ещё нет.

    Args:
        url: URL видео для добавления.
    """
    history = load_history()
    if url not in history:
        history.append(url)
        save_history(history)


def is_in_history(url: str) -> bool:
    """Проверяет, есть ли URL в истории.

    Args:
        url: URL для проверки.

    Returns:
        True если URL уже в истории, иначе False.
    """
    history = load_history()
    return url in history


def clear_history() -> None:
    """Очищает историю скачиваний."""
    if os.path.exists(config.HISTORY_FILE_PATH):
        try:
            os.remove(config.HISTORY_FILE_PATH)
            print(f"{config.COLOR_GREEN}✅ История скачиваний очищена.{config.COLOR_RESET}")
        except OSError as e:
            print(f"{config.COLOR_RED}❌ Не удалось очистить историю: {e}{config.COLOR_RESET}")
    else:
        print(f"{config.COLOR_YELLOW}История уже пуста.{config.COLOR_RESET}")
