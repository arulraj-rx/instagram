import os
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TelegramPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.token = os.getenv("TELEGRAM_POST_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_POST_CHAT_ID")
        self.poll_interval = settings.get("poll_interval", 20)
        self.poll_attempts = settings.get("poll_attempts", 3)

        if not self.token or not self.chat_id:
            raise ValueError("Missing Telegram Credentials")

        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _poll_message(self, response_json):
        result = response_json.get("result", {})
        message_id = result.get("message_id")

        for attempt in range(1, self.poll_attempts + 1):
            if message_id:
                self.logger.info(f"   Telegram publish confirmed on poll attempt {attempt}")
                return True

            self.logger.warning(f"   Telegram poll attempt {attempt}/{self.poll_attempts} pending")
            if attempt < self.poll_attempts:
                time.sleep(self.poll_interval)

        return False

    def _send_with_poll(self, endpoint, data, files=None):
        url = f"{self.base_url}/{endpoint}"
        res = self.session.post(url, data=data, files=files, timeout=60)
        if res.status_code != 200:
            raise requests.HTTPError(f"Telegram API Error: {res.text}", response=res)
        return self._poll_message(res.json())

    def post_video(self, file_path, caption):
        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return False

        with open(file_path, "rb") as file_obj:
            return self._send_with_poll(
                "sendVideo",
                {"chat_id": str(self.chat_id), "caption": caption},
                {"video": file_obj},
            )

    def post_image(self, file_path, caption):
        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return False

        with open(file_path, "rb") as file_obj:
            return self._send_with_poll(
                "sendPhoto",
                {"chat_id": str(self.chat_id), "caption": caption},
                {"photo": file_obj},
            )

    def send_message(self, text):
        return self._send_with_poll(
            "sendMessage",
            {"chat_id": str(self.chat_id), "text": str(text)[:4000]},
        )

    def post_text(self, text):
        return self.send_message(text)
