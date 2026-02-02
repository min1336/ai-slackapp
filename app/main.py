from __future__ import annotations

import signal
from threading import Event, Thread

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import config, database, slack
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

# Initializes your app with your bot token and socket mode handler
app = App(token=slack.bot_token)

# 에러 핸들러 등록 (다른 핸들러보다 먼저)
register_error_handler(app)

# 리스너 등록
register_message_handlers(app)
register_action_handlers(app)
register_view_handlers(app)


def _start_sync_worker(interval_seconds: int) -> None:
    def run() -> None:
        logger.info(f"Sync worker started (interval={interval_seconds}s)")
        while not _stop_event.is_set():
            try:
                synced_settlements, synced_logs = sync_pending_records()
                if synced_settlements or synced_logs:
                    logger.info(
                        "Background sync completed: "
                        f"settlements={synced_settlements}, logs={synced_logs}"
                    )
            except Exception as e:
                logger.warning(f"Background sync failed: {e}")

            # sleep 대신 Event.wait() 사용 - 종료 신호 시 즉시 응답
            _stop_event.wait(timeout=interval_seconds)

        logger.info("Sync worker stopped")

    Thread(target=run, daemon=True).start()


def _handle_shutdown(signum: int, frame) -> None:
    """SIGTERM/SIGINT 핸들러 - graceful shutdown 시작."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    _stop_event.set()


def main():
    # 시그널 핸들러 등록
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    logger.info("애플리케이션 시작")
    if database.is_configured:
        recover_stale_sync_records()
        _start_sync_worker(config.sync_interval_seconds)
    else:
        logger.warning("DATABASE_URL is not configured; sync worker disabled")
    SocketModeHandler(app, slack.app_token).start()


if __name__ == "__main__":
    main()
