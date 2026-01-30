from __future__ import annotations

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import slack
from app.listener.actions import register_action_handlers
from app.listener.messages import register_message_handlers
from app.listener.views import register_view_handlers

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("slack_bolt").setLevel(logging.WARNING)
logging.getLogger("slack_sdk").setLevel(logging.WARNING)

# Initializes your app with your bot token and socket mode handler
app = App(token=slack.bot_token)

# 리스너 등록
register_message_handlers(app)
register_action_handlers(app)
register_view_handlers(app)


def main():
    SocketModeHandler(app, slack.app_token).start()


if __name__ == "__main__":
    main()
