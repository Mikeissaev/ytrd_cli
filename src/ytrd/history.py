"""Модуль для управления историей скачиваний."""

import json
import os
from typing import List
from . import config
from . import logger

# Инициализация логгера для модуля history
log = logger.get_logger(__name__)


def load_history() -> List[str]:
    """Загружает историю скачиваний из JSON файла.

    Returns:
        Список URL видео, которые были скачаны ранее.
    """
    if not os.path.exists(config.HISTORY_FILE_PATH):
        log.debug("History file does not exist, returning empty list")
        return []
    try:
        with open(config.HISTORY_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure it's a list
            if isinstance(data, list):
                log.debug(f"History loaded: {len(data)} entries")
                return data
            log.warning("History file is not a list, returning empty")
            return []
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Failed to load history: {e}")
        return []


def save_history(history: List[str]) -> None:
    """Сохраняет историю скачиваний в JSON файл.

    Args:
        history: Список URL для сохранения.
    """
    try:
        with open(config.HISTORY_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        log.debug(f"History saved: {len(history)} entries")
    except OSError as e:
        log.error(f"Failed to save history: {e}")
        print(f"{config.COLOR_RED}Ошибка сохранения истории: {e}{config.COLOR_RESET}")


def add_to_history(url: str) -> None:
    """Добавляет URL в историю, если его там ещё нет.

    Args:
        url: URL видео для добавления.
    """
    log.debug(f"Adding URL to history: {url}")
    history = load_history()
    if url not in history:
        history.append(url)
        save_history(history)
        log.info(f"URL added to history: {url}")
    else:
        log.debug(f"URL already in history: {url}")


def is_in_history(url: str) -> bool:
    """Проверяет, есть ли URL в истории.

    Args:
        url: URL для проверки.

    Returns:
        True если URL уже в истории, иначе False.
    """
    result = url in load_history()
    log.debug(f"History check for {url}: {result}")
    return result


def clear_history() -> None:
    """Очищает историю скачиваний."""
    log.info("Clearing history")
    if os.path.exists(config.HISTORY_FILE_PATH):
        try:
            os.remove(config.HISTORY_FILE_PATH)
            print(f"{config.COLOR_GREEN}✅ История скачиваний очищена.{config.COLOR_RESET}")
            log.info("History cleared successfully")
        except OSError as e:
            log.error(f"Failed to clear history: {e}")
            print(f"{config.COLOR_RED}❌ Не удалось очистить историю: {e}{config.COLOR_RESET}")
    else:
        log.debug("History file does not exist, already empty")
        print(f"{config.COLOR_YELLOW}История уже пуста.{config.COLOR_RESET}")
