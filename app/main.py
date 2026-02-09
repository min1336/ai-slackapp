from __future__ import annotations

import signal
from threading import Event, Thread

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import get_app_config, get_database_settings, get_slack_settings
from app.core import get_logger, setup_logging
from app.error_handler import register_error_handler
from app.listener.actions import register_action_handlers
from app.listener.messages import register_message_handlers
from app.listener.views import register_view_handlers
from app.services.sync_service import recover_stale_sync_records, sync_pending_records

# 로깅 설정 (환경별 로그 레벨: dev=DEBUG, prod=INFO)
setup_logging()
logger = get_logger(__name__)

# Graceful shutdown을 위한 이벤트
_stop_event = Event()


def _create_app() -> App:
    """Slack Bolt App 초기화 (lazy — main() 호출 시에만 실행)."""
    slack_settings = get_slack_settings()
    bolt_app = App(token=slack_settings.bot_token)
    register_error_handler(bolt_app)
    register_message_handlers(bolt_app)
    register_action_handlers(bolt_app)
    register_view_handlers(bolt_app)
    return bolt_app


def _start_sync_worker(interval_seconds: int) -> None:
    def run() -> None:
        logger.info("sync_worker_started", interval_seconds=interval_seconds)
        while not _stop_event.is_set():
            try:
                synced_settlements, synced_logs = sync_pending_records()
                if synced_settlements or synced_logs:
                    logger.info(
                        "background_sync_completed",
                        settlements=synced_settlements,
                        logs=synced_logs,
                    )
            except Exception as e:
                logger.warning("background_sync_failed", error=str(e))

            # sleep 대신 Event.wait() 사용 - 종료 신호 시 즉시 응답
            _stop_event.wait(timeout=interval_seconds)

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

    logger.info("app_started")
    database = get_database_settings()
    if database.is_configured:
        recover_stale_sync_records()
        app_config = get_app_config()
        _start_sync_worker(app_config.sync_interval_seconds)
    else:
        logger.warning(
            "database_not_configured",
            consequence="sync_worker_disabled",
        )
    app = _create_app()
    slack_settings = get_slack_settings()
    SocketModeHandler(app, slack_settings.app_token).start()


if __name__ == "__main__":
    main()
