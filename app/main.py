from __future__ import annotations

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import slack
from app.core import get_logger, setup_logging
from app.listener.actions import register_action_handlers
from app.listener.messages import register_message_handlers
from app.listener.views import register_view_handlers

# 로깅 설정 (환경별 로그 레벨: dev=DEBUG, prod=INFO)
setup_logging()
logger = get_logger(__name__)

# Initializes your app with your bot token and socket mode handler
app = App(token=slack.bot_token)

# 리스너 등록
register_message_handlers(app)
register_action_handlers(app)
register_view_handlers(app)


def main():
    logger.info("애플리케이션 시작")
    SocketModeHandler(app, slack.app_token).start()


if __name__ == "__main__":
    main()
