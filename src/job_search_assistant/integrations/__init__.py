"""Thin integration clients used by manual and output flows."""

from .notion import NotionAnalysisReportClient
from .telegram import TelegramBotClient

__all__ = ["NotionAnalysisReportClient", "TelegramBotClient"]
