import os
import time
import logging
import requests


class FacebookPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.page_id = os.getenv("FB_PAGE_ID")
        self.token = os.getenv("META_TOKEN")
        self.base_url = f"https://graph.facebook.com/v18.0/{self.page_id}"
        self.poll_interval = settings.get("poll_interval", 20)
        self.poll_attempts = settings.get("poll_attempts", 3)

    def _poll_object(self, object_id):
        if not object_id:
            return False

        url = f"https://graph.facebook.com/v18.0/{object_id}"
        params = {
            "access_token": self.token,
            "fields": "id",
        }

        for attempt in range(1, self.poll_attempts + 1):
            res = requests.get(url, params=params, timeout=30)
            if res.status_code == 200 and res.json().get("id"):
                self.logger.info(f"   Facebook publish confirmed on poll attempt {attempt}")
                return True

            self.logger.warning(f"   Facebook poll attempt {attempt}/{self.poll_attempts} pending")
            if attempt < self.poll_attempts:
                time.sleep(self.poll_interval)

        return False

    def post_video(self, file_path, caption):
        url = f"{self.base_url}/videos"
        data = {
            "access_token": self.token,
            "description": caption,
        }

        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return False

        with open(file_path, "rb") as file_obj:
            files = {"source": file_obj}
            res = requests.post(url, data=data, files=files, timeout=120)

        if res.status_code != 200:
            raise requests.HTTPError(f"FB Upload Failed: {res.text}", response=res)

        publish_id = res.json().get("id")
        return self._poll_object(publish_id)

    def post_image(self, file_path, caption):
        url = f"{self.base_url}/photos"
        data = {
            "access_token": self.token,
            "message": caption,
        }

        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            return False

        with open(file_path, "rb") as file_obj:
            files = {"source": file_obj}
            res = requests.post(url, data=data, files=files, timeout=60)

        if res.status_code != 200:
            raise requests.HTTPError(f"FB Photo Failed: {res.text}", response=res)

        publish_id = res.json().get("post_id") or res.json().get("id")
        return self._poll_object(publish_id)

    def post_text(self, text):
        url = f"{self.base_url}/feed"
        data = {
            "access_token": self.token,
            "message": text,
        }

        res = requests.post(url, data=data, timeout=60)
        if res.status_code != 200:
            raise requests.HTTPError(f"FB Text Post Failed: {res.text}", response=res)

        publish_id = res.json().get("id")
        return self._poll_object(publish_id)
