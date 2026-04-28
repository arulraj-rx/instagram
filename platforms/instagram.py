import logging
import os
import time

import requests


class InstagramPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.ig_id = os.getenv("IG_ID")
        self.token = os.getenv("META_TOKEN")
        self.base_url = f"https://graph.facebook.com/v18.0/{self.ig_id}"
        self.poll_interval = int(settings.get("instagram_poll_interval", 10))
        self.poll_attempts = int(settings.get("instagram_poll_attempts", 30))

    def post_video(self, video_url, caption):
        return self._create_publish_container(video_url, caption, "VIDEO")

    def post_image(self, image_url, caption):
        return self._create_publish_container(image_url, caption, "IMAGE")

    def _create_publish_container(self, media_url, caption, media_type):
        url = f"{self.base_url}/media"
        payload = {
            "access_token": self.token,
            "caption": caption,
            "media_type": "REELS" if media_type == "VIDEO" else "IMAGE",
        }

        if media_type == "VIDEO":
            payload["video_url"] = media_url
            payload["share_to_feed"] = "true"
        else:
            payload["image_url"] = media_url

        self.logger.info(f"IG: sending {media_type.lower()} URL to Meta")

        try:
            response = requests.post(url, data=payload, timeout=60)
            self.logger.info(f"IG create response code: {response.status_code}")

            if response.status_code != 200:
                raise Exception(f"IG create failed: {response.text}")

            creation_id = response.json()["id"]
            self.logger.info(f"IG container created: {creation_id}")

            if media_type == "VIDEO":
                self._wait_for_video_processing(creation_id)

            publish_url = f"{self.base_url}/media_publish"
            publish_response = requests.post(
                publish_url,
                data={"creation_id": creation_id, "access_token": self.token},
                timeout=60,
            )

            if publish_response.status_code != 200:
                raise Exception(f"IG publish failed: {publish_response.text}")

            self.logger.info(f"IG published successfully: {publish_response.json()['id']}")
            return True
        except requests.exceptions.Timeout:
            self.logger.error("IG connection timed out")
            raise Exception("Timeout")
        except Exception as error:
            self.logger.error(f"IG error: {error}")
            raise

    def _wait_for_video_processing(self, creation_id):
        self.logger.info("IG: waiting for reel processing")
        last_status = None

        for attempt in range(1, self.poll_attempts + 1):
            time.sleep(self.poll_interval)

            status_response = requests.get(
                f"https://graph.facebook.com/v18.0/{creation_id}",
                params={
                    "fields": "status_code,status,error_message",
                    "access_token": self.token,
                },
                timeout=30,
            )

            if status_response.status_code != 200:
                self.logger.warning(f"IG poll error: {status_response.text}")
                continue

            data = status_response.json()
            status = data.get("status_code") or data.get("status") or "UNKNOWN"
            last_status = status
            self.logger.info(f"IG poll attempt {attempt}: {status}")

            if status in {"FINISHED", "PUBLISHED"}:
                return

            if status in {"ERROR", "EXPIRED", "FAILED"}:
                detail = data.get("error_message") or f"status={status}"
                raise Exception(f"IG video processing failed: {detail}")

        raise Exception(f"IG video processing timeout: last_status={last_status or 'UNKNOWN'}")
