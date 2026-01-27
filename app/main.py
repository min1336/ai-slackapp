from __future__ import annotations

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import settings
from app.listener.actions import register_action_handlers
from app.listener.messages import register_message_handlers
from app.listener.views import register_view_handlers

# Initializes your app with your bot token and socket mode handler
app = App(token=settings.SLACK_BOT_TOKEN)

# 리스너 등록
register_message_handlers(app)
register_action_handlers(app)
register_view_handlers(app)

def main():
    SocketModeHandler(app, settings.SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
