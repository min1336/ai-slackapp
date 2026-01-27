from __future__ import annotations

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import settings

# Initializes your app with your bot token and socket mode handler
app = App(token=settings.SLACK_BOT_TOKEN)


def main():
    SocketModeHandler(app, settings.SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
