#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.integrations import TelegramBotClient
from job_search_assistant.runtime import configure_logging, format_kv, get_logger, load_local_env


logger = get_logger("telegram.send")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one Telegram bot message using credentials from .env.local.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Text to send.")
    group.add_argument("--stdin", action="store_true", help="Read text to send from stdin.")
    parser.add_argument("--chat-id", help="Optional chat id override.")
    return parser.parse_args()


def main(args: argparse.Namespace) -> None:
    configure_logging(force=True)
    load_local_env(ROOT)
    client = TelegramBotClient()
    text = args.text
    if args.stdin:
        text = sys.stdin.read()
    if not text:
        raise SystemExit("No message text provided.")
    result = client.send_message(text, chat_id=args.chat_id)
    logger.info(
        format_kv(
            "telegram.send.done",
            chat_id=args.chat_id or client.default_chat_id,
            message_id=result["result"]["message_id"],
            text_chars=len(text),
        )
    )


if __name__ == "__main__":
    main(parse_args())
