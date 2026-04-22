from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass
class TelegramMessage:
    update_id: int
    chat_id: int
    text: str
    message_id: int


class TelegramBotClient:
    def __init__(self, token: str | None = None, default_chat_id: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = default_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    def get_updates(self, *, offset: int | None = None, timeout: int = 0) -> list[TelegramMessage]:
        payload: dict[str, Any] = {}
        if offset is not None:
            payload["offset"] = offset
        if timeout:
            payload["timeout"] = timeout
        response = requests.get(
            self._endpoint("getUpdates"),
            params=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        messages: list[TelegramMessage] = []
        for item in body.get("result", []):
            message = item.get("message") or {}
            text = message.get("text")
            chat = message.get("chat") or {}
            if not isinstance(text, str):
                continue
            messages.append(
                TelegramMessage(
                    update_id=int(item["update_id"]),
                    chat_id=int(chat["id"]),
                    text=text,
                    message_id=int(message["message_id"]),
                )
            )
        return messages

    def send_message(
        self,
        text: str,
        *,
        chat_id: int | str | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        resolved_chat_id = str(chat_id or self.default_chat_id or "")
        if not resolved_chat_id:
            raise RuntimeError("TELEGRAM_CHAT_ID is not set and no chat_id was provided.")
        response = requests.post(
            self._endpoint("sendMessage"),
            data={
                "chat_id": resolved_chat_id,
                "text": text,
                "disable_web_page_preview": "true" if disable_web_page_preview else "false",
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def _endpoint(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.token}/{method}"
