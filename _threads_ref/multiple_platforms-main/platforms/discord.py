import os
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DiscordPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.token = os.getenv("DISCORD_BOT_TOKEN")
        self.channel_id = os.getenv("DISCORD_CHANNEL_ID")
        self.poll_interval = settings.get("poll_interval", 20)
        self.poll_attempts = settings.get("poll_attempts", 3)

        if not self.token or not self.channel_id:
            raise ValueError("Missing Discord Credentials")

        self.base_url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "Authorization": f"Bot {self.token}",
            "User-Agent": "DiscordBot (SocialAuto, 1.0)",
        })

    def _poll_message(self, message_id):
        if not message_id:
            return False

        url = f"{self.base_url}/{message_id}"
        for attempt in range(1, self.poll_attempts + 1):
            response = self.session.get(url, timeout=30)
            if response.status_code == 200 and response.json().get("id"):
                self.logger.info(f"   Discord publish confirmed on poll attempt {attempt}")
                return True

            self.logger.warning(f"   Discord poll attempt {attempt}/{self.poll_attempts} pending")
            if attempt < self.poll_attempts:
                time.sleep(self.poll_interval)

        return False

    def _send(self, payload, files=None):
        response = self.session.post(self.base_url, data=payload if files else None, json=None if files else payload, files=files, timeout=60)
        if response.status_code not in [200, 201]:
            raise requests.HTTPError(f"Discord API Error: {response.status_code} - {response.text}", response=response)
        return self._poll_message(response.json().get("id"))

    def post_image(self, file_path, caption):
        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return False

        with open(file_path, "rb") as file_obj:
            files = {
                "file": (os.path.basename(file_path), file_obj, "application/octet-stream")
            }
            return self._send({"content": caption[:2000]}, files=files)

    def post_video(self, file_path, caption):
        return self.post_image(file_path, caption)

    def post_text(self, text):
        return self._send({"content": str(text)[:2000]})
