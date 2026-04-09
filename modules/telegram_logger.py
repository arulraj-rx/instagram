import logging
import os

import requests


class TelegramLogHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.token = os.getenv("TELEGRAM_LOG_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_LOG_CHAT_ID", "").strip()
        self.session = requests.Session()

    def emit(self, record):
        if not self.token or not self.chat_id:
            return

        try:
            message = self.format(record)
            if not message:
                return

            for chunk in self._chunk_message(message):
                self._send_message(chunk)
        except Exception:
            # Logging transport failures must never break the main workflow.
            return

    def _chunk_message(self, message, limit=4000):
        text = str(message).strip()
        if not text:
            return []

        chunks = []
        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = limit
            chunks.append(text[:split_at].strip())
            text = text[split_at:].strip()

        if text:
            chunks.append(text)
        return chunks

    def _send_message(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.session.post(
            url,
            data={"chat_id": self.chat_id, "text": text},
            timeout=15,
        )
