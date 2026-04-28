import logging
import os
import time

import requests
from core.meta_api import (
    build_meta_error_message,
)


class ThreadsPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.token = os.getenv("THREADS_ACCESS_TOKEN")
        self.api_host = "https://graph.threads.net/v1.0"
        self.base_url = f"{self.api_host}/me"
        self.poll_interval = int(settings.get("threads_poll_interval", 10))
        self.processing_timeout_seconds = int(
            settings.get("threads_processing_timeout_seconds", 50)
        )
        self.publish_timeout_seconds = int(
            settings.get("threads_publish_timeout_seconds", 50)
        )
        self.processing_poll_attempts = max(
            1,
            self.processing_timeout_seconds // max(1, self.poll_interval),
        )
        self.publish_poll_attempts = max(
            1,
            self.publish_timeout_seconds // max(1, self.poll_interval),
        )

    def post_image(self, image_url, caption):
        return self._create_media_post(image_url, caption, "IMAGE")

    def post_video(self, video_url, caption):
        return self._create_media_post(video_url, caption, "VIDEO")

    def post_text(self, text):
        url = f"{self.base_url}/threads"
        payload = {
            "access_token": self.token,
            "media_type": "TEXT",
            "text": text,
            "auto_publish_text": "true",
        }
        response = self._post(url, payload, "Threads text creation failed")
        thread_id = response.json().get("id")
        if not thread_id:
            raise Exception("Threads text creation failed: missing thread id")
        return self._poll_thread(thread_id)

    def _post(self, url, payload, label):
        response = requests.post(url, data=payload, timeout=60)
        if response.status_code != 200:
            raise requests.HTTPError(build_meta_error_message(label, response), response=response)
        return response

    def _get(self, url, params, label):
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            raise requests.HTTPError(build_meta_error_message(label, response), response=response)
        return response

    def _create_media_container(self, media_url, caption, media_type):
        url = f"{self.base_url}/threads"
        payload = {
            "access_token": self.token,
            "media_type": media_type,
            "text": caption,
        }
        if media_type == "IMAGE":
            payload["image_url"] = media_url
        else:
            payload["video_url"] = media_url

        response = self._post(url, payload, f"Threads {media_type.lower()} creation failed")
        creation_id = response.json().get("id")
        if not creation_id:
            raise Exception("Threads media creation failed: missing creation id")
        return creation_id

    def _create_media_post(self, media_url, caption, media_type):
        creation_id = self._create_media_container(media_url, caption, media_type)
        self._wait_for_container(creation_id)
        return self._publish_container(creation_id)

    def _wait_for_container(self, creation_id):
        url = f"{self.api_host}/{creation_id}"
        params = {
            "fields": "id,status,error,error_message",
            "access_token": self.token,
        }
        last_status = None

        for attempt in range(1, self.processing_poll_attempts + 1):
            time.sleep(self.poll_interval)
            response = self._get(url, params, "Threads status check failed")
            data = response.json()
            status = data.get("status") or "UNKNOWN"
            last_status = status
            self.logger.info(f"THREADS processing attempt {attempt}: {status}")

            if status in {"FINISHED", "PUBLISHED"}:
                return True

            if status in {"ERROR", "EXPIRED", "FAILED"}:
                details = (
                    data.get("error_message")
                    or data.get("error")
                    or f"status={status}"
                )
                raise Exception(f"Threads Processing Error: {details}")

        raise Exception(f"Threads processing timeout: last_status={last_status or 'UNKNOWN'}")

    def _publish_container(self, creation_id):
        url = f"{self.base_url}/threads_publish"
        payload = {"creation_id": creation_id, "access_token": self.token}
        response = requests.post(url, data=payload, timeout=60)
        if response.status_code != 200:
            raise requests.HTTPError(
                build_meta_error_message("Threads publish failed", response),
                response=response,
            )

        thread_id = response.json().get("id")
        if not thread_id:
            raise Exception("Threads publish failed: missing thread id")
        return self._poll_thread(thread_id)

    def _poll_thread(self, thread_id):
        url = f"{self.api_host}/{thread_id}"
        params = {"fields": "id", "access_token": self.token}

        for attempt in range(1, self.publish_poll_attempts + 1):
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200 and response.json().get("id"):
                self.logger.info(f"THREADS publish confirmed on attempt {attempt}")
                return True

            self.logger.warning(
                f"THREADS publish not visible yet on attempt {attempt}/{self.publish_poll_attempts}"
            )
            if attempt < self.publish_poll_attempts:
                time.sleep(self.poll_interval)

        raise Exception("Threads publish confirmation timeout")
