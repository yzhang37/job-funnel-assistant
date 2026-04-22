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
from job_search_assistant.runtime import load_local_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one Telegram bot message using credentials from .env.local.")
    parser.add_argument("--text", required=True, help="Text to send.")
    parser.add_argument("--chat-id", help="Optional chat id override.")
    return parser.parse_args()


def main(args: argparse.Namespace) -> None:
    load_local_env(ROOT)
    client = TelegramBotClient()
    result = client.send_message(args.text, chat_id=args.chat_id)
    print(result["result"]["message_id"])


if __name__ == "__main__":
    main(parse_args())
