import logging
import os
import time

import requests


class InstagramPoster:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.ig_id = os.getenv("IG_ID")
        self.token = os.getenv("META_TOKEN")
        self.base_url = f"https://graph.facebook.com/v18.0/{self.ig_id}"
        self.processing_wait_seconds = int(os.getenv("IG_REEL_STATUS_WAIT_TIME", "10"))
        self.processing_max_attempts = int(os.getenv("IG_REEL_STATUS_RETRIES", "30"))
        self.publish_delay_seconds = int(os.getenv("IG_PUBLISH_DELAY_AFTER_FINISHED", "15"))

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
        self.logger.info(f"IG create URL: {url}")

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
            self.logger.info("IG: publishing media")
            publish_response = requests.post(
                publish_url,
                data={"creation_id": creation_id, "access_token": self.token},
                timeout=60,
            )

            self.logger.info(f"IG publish response code: {publish_response.status_code}")

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
        self.logger.info(
            "IG poll config: %ss interval, %s max attempts",
            self.processing_wait_seconds,
            self.processing_max_attempts,
        )
        status = "IN_PROGRESS"

        for attempt in range(1, self.processing_max_attempts + 1):
            self.logger.info(
                "IG poll attempt %s/%s",
                attempt,
                self.processing_max_attempts,
            )

            status_response = requests.get(
                f"https://graph.facebook.com/v18.0/{creation_id}",
                params={"fields": "status_code", "access_token": self.token},
                timeout=30,
            )

            if status_response.status_code != 200:
                self.logger.warning(f"IG poll error: {status_response.text}")
                if attempt < self.processing_max_attempts:
                    self.logger.info(
                        "IG: waiting %ss before next status check",
                        self.processing_wait_seconds,
                    )
                    time.sleep(self.processing_wait_seconds)
                continue

            status = status_response.json().get("status_code", "ERROR")
            self.logger.info(f"IG poll status: {status}")

            if status == "ERROR":
                raise Exception("IG video processing failed")

            if status == "FINISHED":
                self.logger.info("IG: reel processing finished")
                if self.publish_delay_seconds > 0:
                    self.logger.info(
                        "IG: waiting %ss before publish",
                        self.publish_delay_seconds,
                    )
                    time.sleep(self.publish_delay_seconds)
                return

            if attempt < self.processing_max_attempts:
                self.logger.info(
                    "IG: waiting %ss before next status check",
                    self.processing_wait_seconds,
                )
                time.sleep(self.processing_wait_seconds)

        raise Exception("IG video processing timeout")
