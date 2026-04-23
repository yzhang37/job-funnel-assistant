from __future__ import annotations

import time
import uuid

from job_search_assistant.integrations import TelegramBotClient
from job_search_assistant.manual_flow import looks_like_job_input, normalize_manual_intake_request, parse_manual_intake_text
from job_search_assistant.runtime import format_kv, get_logger
from job_search_assistant.runtime.config import RuntimeSettings
from job_search_assistant.runtime.kafka_bus import KafkaEventBus
from job_search_assistant.runtime.mysql_runtime import MySQLRuntimeStore


logger = get_logger("service.manual_intake")


class ManualIntakeService:
    def __init__(self, *, settings: RuntimeSettings, bus: KafkaEventBus, runtime_store: MySQLRuntimeStore) -> None:
        self.settings = settings
        self.bus = bus
        self.runtime_store = runtime_store
        self.telegram = TelegramBotClient()

    def run_once(self) -> int:
        last_update_id = self.runtime_store.get_offset("telegram:last_update_id", default=0)
        updates = self.telegram.get_updates(offset=last_update_id + 1)
        if not updates:
            logger.debug(format_kv("service.manual_intake.empty", last_update_id=last_update_id))
            return 0

        processed = 0
        for message in updates:
            self.runtime_store.set_offset("telegram:last_update_id", message.update_id)
            if not self.telegram.is_owner_message(message):
                logger.warning(
                    format_kv(
                        "service.manual_intake.ignored_non_owner",
                        update_id=message.update_id,
                        chat_id=message.chat_id,
                        from_user_id=message.from_user_id,
                    )
                )
                continue
            try:
                request = parse_manual_intake_text(message.text, source_channel="telegram")
                if not looks_like_job_input(request):
                    logger.warning(
                        format_kv(
                            "service.manual_intake.invalid_input",
                            update_id=message.update_id,
                            chat_id=message.chat_id,
                            message_id=message.message_id,
                        )
                    )
                    continue

                request = normalize_manual_intake_request(
                    repo_root=self.settings.repo_root,
                    request=request,
                    model=str(self.settings.manual_intake.extras.get("model", "gpt-5.4")),
                )
                request_id = str(uuid.uuid4())
                payload = {
                    "request_id": request_id,
                    "source_component": "manual_intake",
                    "source_channel": request.source_channel,
                    "raw_text": request.raw_text,
                    "job_url": request.job_url,
                    "jd_text": request.jd_text,
                    "company_name": request.company_name,
                    "position_name": request.position_name,
                    "capture_company_name": request.capture_company_name,
                    "hiring_company": request.hiring_company,
                    "vendor_company": request.vendor_company,
                    "location": request.location,
                    "employment_type": request.employment_type,
                    "recruiter_name": request.recruiter_name,
                    "recruiter_email": request.recruiter_email,
                    "recruiter_phone": request.recruiter_phone,
                    "input_kind": request.input_kind,
                    "end_client_disclosed": request.end_client_disclosed,
                    "should_enrich_company_profile": request.should_enrich_company_profile,
                    "field_confidence": request.field_confidence,
                    "field_evidence": request.field_evidence,
                    "normalization_payload": request.normalization_payload,
                    "notes": request.notes,
                    "telegram": {
                        "update_id": message.update_id,
                        "chat_id": message.chat_id,
                        "message_id": message.message_id,
                    },
                    "reply_chat_id": message.chat_id,
                    "send_telegram_reply": True,
                }
                self.runtime_store.record_manual_intake_event(
                    request_id=request_id,
                    source_channel=request.source_channel,
                    update_id=message.update_id,
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    job_url=request.job_url,
                    has_jd_text=bool(request.jd_text),
                    status="enqueued",
                    payload=payload,
                )
                self.bus.publish(
                    topic=self.settings.topics.capture_requested,
                    event_type="capture.requested",
                    payload=payload,
                    producer_name="manual_intake",
                    key=request_id,
                    correlation_id=request_id,
                )
                if bool(self.settings.manual_intake.extras.get("send_ack", True)):
                    self.telegram.send_message("已接收，开始处理。", chat_id=message.chat_id)
                processed += 1
                logger.info(
                    format_kv(
                        "service.manual_intake.enqueued",
                        request_id=request_id,
                        update_id=message.update_id,
                        job_url=request.job_url,
                        input_kind=request.input_kind,
                        has_jd_text=bool(request.jd_text),
                        company_name=request.company_name,
                        position_name=request.position_name,
                    )
                )
            except Exception as exc:
                logger.error(
                    format_kv(
                        "service.manual_intake.failed",
                        update_id=message.update_id,
                        chat_id=message.chat_id,
                        error=str(exc),
                    )
                )
                if bool(self.settings.manual_intake.extras.get("send_ack", True)):
                    self.telegram.send_message("已收到输入，但结构化解析失败，请稍后重试。", chat_id=message.chat_id)
        return processed

    def run_forever(self) -> None:
        interval = self.settings.manual_intake.poll_interval_seconds
        while True:
            try:
                processed = self.run_once()
                sleep_seconds = 1 if processed else interval
            except Exception as exc:  # pragma: no cover - service guard
                logger.error(format_kv("service.manual_intake.crashed", error=str(exc)))
                sleep_seconds = interval
            time.sleep(sleep_seconds)
