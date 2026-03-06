from __future__ import annotations

import os
import signal
from datetime import datetime
from threading import Event, Thread

from croniter import croniter
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import (
    get_app_config,
    get_database_settings,
    get_jotform_settings,
    get_slack_settings,
    resolve_config_path,
)
from app.container import ServiceContainer
from app.core import get_logger, setup_logging
from app.error_handler import register_error_handler
from app.listener.actions import register_action_handlers
from app.listener.messages import register_message_handlers
from app.listener.views import register_view_handlers
from app.listener.webhook import start_webhook_server
from app.services.sync_service import SyncService

# 로깅 설정 (환경별 로그 레벨: dev=DEBUG, prod=INFO)
setup_logging()
logger = get_logger(__name__)

# Graceful shutdown을 위한 이벤트
_stop_event = Event()


def _start_sync_worker(sync_service: SyncService, cron_expr: str) -> None:
    def run() -> None:
        cron = croniter(cron_expr, datetime.now())
        logger.info("sync_worker_started", schedule=cron_expr)
        while not _stop_event.is_set():
            next_run = cron.get_next(datetime)
            wait_seconds = (next_run - datetime.now()).total_seconds()
            logger.debug(
                "sync_worker_waiting",
                next_run=next_run.isoformat(),
                wait_seconds=int(wait_seconds),
            )

            if _stop_event.wait(timeout=max(wait_seconds, 0)):
                break

            try:
                synced_settlements, synced_logs = sync_service.sync_pending_records()
                if synced_settlements or synced_logs:
                    logger.info(
                        "background_sync_completed",
                        settlements=synced_settlements,
                        logs=synced_logs,
                    )

                newly_completed = sync_service.reverse_sync_settlement_completed()
                if newly_completed:
                    logger.info(
                        "background_reverse_sync_completed",
                        newly_completed=newly_completed,
                    )
            except Exception:
                logger.exception("background_sync_failed")

        logger.info("sync_worker_stopped")

    Thread(target=run, daemon=True).start()


def _handle_shutdown(signum: int, frame) -> None:
    """SIGTERM/SIGINT 핸들러 - graceful shutdown 시작."""
    sig_name = signal.Signals(signum).name
    logger.info("graceful_shutdown", signal=sig_name)
    _stop_event.set()


def main():
    # 시그널 핸들러 등록
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    config_path = resolve_config_path()
    logger.info(
        "config_resolved",
        config_file=str(config_path),
        environment=os.getenv("ENVIRONMENT", "dev"),
    )
    logger.info("app_started")
    slack_settings = get_slack_settings()
    bolt_app = App(token=slack_settings.bot_token)
    container = ServiceContainer(bolt_app.client)

    app_config = get_app_config()
    database = get_database_settings()
    if database.is_configured:
        container.sync_service.recover_stale_sync_records()
        container.discovery.backfill_reservation_threads(days=7)
        _start_sync_worker(container.sync_service, app_config.settlement.sync_schedule)
    else:
        logger.warning(
            "database_not_configured",
            consequence="sync_worker_disabled",
        )

    error_channel = app_config.settlement.error_channel_id
    register_error_handler(bolt_app, error_channel_id=error_channel)
    register_message_handlers(bolt_app, container)
    register_action_handlers(bolt_app, container)
    register_view_handlers(bolt_app, container)

    jotform = get_jotform_settings()
    if container.cancellation_image and jotform.is_configured:
        start_webhook_server(
            container.cancellation_image,
            api_key=jotform.api_key,
            port=container.cancellation_webhook_port,
        )
    else:
        logger.info("cancellation_webhook_disabled")

    SocketModeHandler(bolt_app, slack_settings.app_token).start()


if __name__ == "__main__":
    main()
