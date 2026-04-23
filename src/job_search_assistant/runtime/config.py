from __future__ import annotations

import os
import socket
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MySQLSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    pool_size: int
    connect_timeout_seconds: int

    def connector_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "connection_timeout": self.connect_timeout_seconds,
            "autocommit": False,
        }


@dataclass(frozen=True)
class KafkaSettings:
    bootstrap_servers: tuple[str, ...]
    client_id: str
    request_timeout_ms: int


@dataclass(frozen=True)
class ArtifactStoreSettings:
    driver: str
    root: Path


@dataclass(frozen=True)
class BrowserBrokerSettings:
    node_id: str
    lane_name: str
    lock_dir: Path
    acquire_timeout_seconds: int
    poll_interval_seconds: int


@dataclass(frozen=True)
class TopicSettings:
    tracker_discovery_requested: str
    tracker_links_discovered: str
    capture_requested: str
    capture_bundle_ready: str
    analysis_requested: str
    analysis_ready: str
    output_requested: str

    def all_topics(self) -> tuple[str, ...]:
        return (
            self.tracker_discovery_requested,
            self.tracker_links_discovered,
            self.capture_requested,
            self.capture_bundle_ready,
            self.analysis_requested,
            self.analysis_ready,
            self.output_requested,
        )


@dataclass(frozen=True)
class ServiceSettings:
    poll_interval_seconds: int
    consumer_group: str
    extras: dict[str, Any]


@dataclass(frozen=True)
class RuntimeSettings:
    repo_root: Path
    mysql: MySQLSettings
    kafka: KafkaSettings
    artifact_store: ArtifactStoreSettings
    browser_broker: BrowserBrokerSettings
    topics: TopicSettings
    tracker: ServiceSettings
    manual_intake: ServiceSettings
    capture: ServiceSettings
    analyzer: ServiceSettings
    output: ServiceSettings


def load_runtime_settings(repo_root: Path, path: str | Path = "config/runtime.toml") -> RuntimeSettings:
    config_path = repo_root / path
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    mysql_payload = dict(payload["mysql"])
    mysql = MySQLSettings(
        host=_env("JOB_SEARCH_MYSQL_HOST", mysql_payload["host"]),
        port=int(_env("JOB_SEARCH_MYSQL_PORT", mysql_payload["port"])),
        database=_env("JOB_SEARCH_MYSQL_DATABASE", mysql_payload["database"]),
        user=_env("JOB_SEARCH_MYSQL_USER", mysql_payload["user"]),
        password=_env("JOB_SEARCH_MYSQL_PASSWORD", mysql_payload["password"]),
        pool_size=int(_env("JOB_SEARCH_MYSQL_POOL_SIZE", mysql_payload["pool_size"])),
        connect_timeout_seconds=int(
            _env("JOB_SEARCH_MYSQL_CONNECT_TIMEOUT_SECONDS", mysql_payload["connect_timeout_seconds"])
        ),
    )

    kafka_payload = dict(payload["kafka"])
    bootstrap_override = os.getenv("JOB_SEARCH_KAFKA_BOOTSTRAP_SERVERS")
    bootstrap_servers = (
        tuple(part.strip() for part in bootstrap_override.split(",") if part.strip())
        if bootstrap_override
        else tuple(str(item) for item in kafka_payload["bootstrap_servers"])
    )
    kafka = KafkaSettings(
        bootstrap_servers=bootstrap_servers,
        client_id=_env("JOB_SEARCH_KAFKA_CLIENT_ID", kafka_payload["client_id"]),
        request_timeout_ms=int(_env("JOB_SEARCH_KAFKA_REQUEST_TIMEOUT_MS", kafka_payload["request_timeout_ms"])),
    )

    artifact_payload = dict(payload["artifact_store"])
    artifact_store = ArtifactStoreSettings(
        driver=_env("JOB_SEARCH_ARTIFACT_STORE_DRIVER", artifact_payload["driver"]),
        root=_resolve_path(repo_root, _env("JOB_SEARCH_ARTIFACT_ROOT", artifact_payload["root"])),
    )

    broker_payload = dict(payload["browser_broker"])
    browser_broker = BrowserBrokerSettings(
        node_id=_env("JOB_SEARCH_NODE_ID", broker_payload["node_id"] or socket.gethostname()),
        lane_name=_env("JOB_SEARCH_BROWSER_LANE_NAME", broker_payload["lane_name"]),
        lock_dir=_resolve_path(repo_root, _env("JOB_SEARCH_BROWSER_LOCK_DIR", broker_payload["lock_dir"])),
        acquire_timeout_seconds=int(
            _env("JOB_SEARCH_BROWSER_ACQUIRE_TIMEOUT_SECONDS", broker_payload["acquire_timeout_seconds"])
        ),
        poll_interval_seconds=int(
            _env("JOB_SEARCH_BROWSER_POLL_INTERVAL_SECONDS", broker_payload["poll_interval_seconds"])
        ),
    )

    topics_payload = dict(payload["topics"])
    topics = TopicSettings(
        tracker_discovery_requested=_env(
            "JOB_SEARCH_TOPIC_TRACKER_DISCOVERY_REQUESTED", topics_payload["tracker_discovery_requested"]
        ),
        tracker_links_discovered=_env(
            "JOB_SEARCH_TOPIC_TRACKER_LINKS_DISCOVERED", topics_payload["tracker_links_discovered"]
        ),
        capture_requested=_env("JOB_SEARCH_TOPIC_CAPTURE_REQUESTED", topics_payload["capture_requested"]),
        capture_bundle_ready=_env("JOB_SEARCH_TOPIC_CAPTURE_BUNDLE_READY", topics_payload["capture_bundle_ready"]),
        analysis_requested=_env("JOB_SEARCH_TOPIC_ANALYSIS_REQUESTED", topics_payload["analysis_requested"]),
        analysis_ready=_env("JOB_SEARCH_TOPIC_ANALYSIS_READY", topics_payload["analysis_ready"]),
        output_requested=_env("JOB_SEARCH_TOPIC_OUTPUT_REQUESTED", topics_payload["output_requested"]),
    )

    services_payload = payload["services"]
    return RuntimeSettings(
        repo_root=repo_root,
        mysql=mysql,
        kafka=kafka,
        artifact_store=artifact_store,
        browser_broker=browser_broker,
        topics=topics,
        tracker=_service_settings(services_payload["tracker"]),
        manual_intake=_service_settings(services_payload["manual_intake"]),
        capture=_service_settings(services_payload["capture"]),
        analyzer=_service_settings(services_payload["analyzer"]),
        output=_service_settings(services_payload["output"]),
    )


def _service_settings(payload: dict[str, Any]) -> ServiceSettings:
    payload = dict(payload)
    poll_interval_seconds = int(payload.pop("poll_interval_seconds"))
    consumer_group = str(payload.pop("consumer_group"))
    return ServiceSettings(
        poll_interval_seconds=poll_interval_seconds,
        consumer_group=consumer_group,
        extras=payload,
    )


def _env(name: str, default: Any) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return str(default)
    return value


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path
