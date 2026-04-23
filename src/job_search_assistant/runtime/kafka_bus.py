from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.admin import NewTopic

from .config import KafkaSettings


@dataclass(frozen=True)
class EventEnvelope:
    message_id: str
    event_type: str
    producer: str
    emitted_at: str
    correlation_id: str | None
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "event_type": self.event_type,
            "producer": self.producer,
            "emitted_at": self.emitted_at,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EventEnvelope:
        return cls(
            message_id=str(payload["message_id"]),
            event_type=str(payload["event_type"]),
            producer=str(payload["producer"]),
            emitted_at=str(payload["emitted_at"]),
            correlation_id=payload.get("correlation_id"),
            payload=dict(payload.get("payload") or {}),
        )


@dataclass(frozen=True)
class ConsumedEvent:
    topic: str
    partition: int
    offset: int
    key: str | None
    envelope: EventEnvelope


class KafkaEventBus:
    def __init__(self, settings: KafkaSettings) -> None:
        self.settings = settings
        self._producer: KafkaProducer | None = None

    def ensure_topics(self, topics: list[str] | tuple[str, ...]) -> None:
        admin = KafkaAdminClient(
            bootstrap_servers=list(self.settings.bootstrap_servers),
            client_id=f"{self.settings.client_id}-admin",
        )
        try:
            existing = set(admin.list_topics())
            missing = [topic for topic in topics if topic not in existing]
            if not missing:
                return
            admin.create_topics(
                new_topics=[NewTopic(name=topic, num_partitions=1, replication_factor=1) for topic in missing],
                validate_only=False,
            )
        finally:
            admin.close()

    def publish(
        self,
        *,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        producer_name: str,
        key: str | None = None,
        correlation_id: str | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope(
            message_id=str(uuid.uuid4()),
            event_type=event_type,
            producer=producer_name,
            emitted_at=_utcnow_text(),
            correlation_id=correlation_id,
            payload=payload,
        )
        producer = self._ensure_producer()
        future = producer.send(topic, key=key.encode("utf-8") if key else None, value=envelope.to_dict())
        future.get(timeout=self.settings.request_timeout_ms / 1000)
        return envelope

    def build_consumer(self, *, topics: list[str] | tuple[str, ...], group_id: str) -> KafkaConsumer:
        return KafkaConsumer(
            *topics,
            bootstrap_servers=list(self.settings.bootstrap_servers),
            group_id=group_id,
            client_id=f"{self.settings.client_id}-{group_id}",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_interval_ms=3600000,
            session_timeout_ms=30000,
            heartbeat_interval_ms=3000,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            key_deserializer=lambda raw: raw.decode("utf-8") if raw else None,
            consumer_timeout_ms=1000,
        )

    def poll(
        self,
        consumer: KafkaConsumer,
        *,
        timeout_ms: int,
        max_records: int = 10,
        max_attempts: int = 3,
    ) -> list[ConsumedEvent]:
        started = time.monotonic()
        polled = {}
        for _ in range(max_attempts):
            elapsed_ms = int((time.monotonic() - started) * 1000)
            remaining_ms = max(timeout_ms - elapsed_ms, 0)
            current_timeout_ms = remaining_ms if remaining_ms > 0 else 0
            polled = consumer.poll(timeout_ms=current_timeout_ms, max_records=max_records)
            if polled or remaining_ms <= 0:
                break
        events: list[ConsumedEvent] = []
        for topic_partition, messages in polled.items():
            for message in messages:
                envelope = EventEnvelope.from_dict(message.value)
                events.append(
                    ConsumedEvent(
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        key=message.key,
                        envelope=envelope,
                    )
                )
        return events

    def commit(self, consumer: KafkaConsumer) -> None:
        consumer.commit()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.flush()
            self._producer.close()
            self._producer = None

    def _ensure_producer(self) -> KafkaProducer:
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=list(self.settings.bootstrap_servers),
                client_id=self.settings.client_id,
                value_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                linger_ms=50,
                retries=3,
            )
        return self._producer


def _utcnow_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
