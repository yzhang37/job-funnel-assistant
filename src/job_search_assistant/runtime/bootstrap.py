from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .browser_broker import CodexComputerUseBroker
from .config import RuntimeSettings, load_runtime_settings
from .env import load_local_env
from .kafka_bus import KafkaEventBus
from .logging import configure_logging
from .mysql_runtime import MySQLRuntimeStore


@dataclass(frozen=True)
class RuntimeComponents:
    settings: RuntimeSettings
    bus: KafkaEventBus
    runtime_store: MySQLRuntimeStore
    browser_broker: CodexComputerUseBroker

    def close(self) -> None:
        self.bus.close()


def bootstrap_runtime(repo_root: Path, *, force_logging: bool = False) -> RuntimeComponents:
    load_local_env(repo_root)
    configure_logging(force=force_logging)
    settings = load_runtime_settings(repo_root)
    runtime_store = MySQLRuntimeStore(settings.mysql)
    bus = KafkaEventBus(settings.kafka)
    browser_broker = CodexComputerUseBroker(
        settings=settings.browser_broker,
        runtime_store=runtime_store,
    )
    settings.artifact_store.root.mkdir(parents=True, exist_ok=True)
    settings.browser_broker.lock_dir.mkdir(parents=True, exist_ok=True)
    return RuntimeComponents(
        settings=settings,
        bus=bus,
        runtime_store=runtime_store,
        browser_broker=browser_broker,
    )


def ensure_runtime_ready(components: RuntimeComponents) -> None:
    components.runtime_store.ensure_schema()
    components.bus.ensure_topics(components.settings.topics.all_topics())
    components.settings.artifact_store.root.mkdir(parents=True, exist_ok=True)
    components.settings.browser_broker.lock_dir.mkdir(parents=True, exist_ok=True)
