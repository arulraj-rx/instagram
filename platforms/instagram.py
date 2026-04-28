import logging
import os
import time

import requests
from core.meta_api import (
    MetaPublishRetryExhausted,
    build_meta_error_message,
    parse_meta_error,
)


class InstagramPoster:
    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.ig_id = os.getenv("IG_ID")
        self.token = os.getenv("META_TOKEN")
        self.api_version = str(settings.get("instagram_api_version", "v24.0"))
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.ig_id}"
        self.poll_interval = int(settings.get("instagram_poll_interval", 10))
        self.poll_timeout_seconds = int(
            settings.get("instagram_poll_timeout_seconds", 50)
        )
        self.poll_attempts = max(1, self.poll_timeout_seconds // max(1, self.poll_interval))
        self.publish_retry_attempts = int(settings.get("meta_publish_retry_attempts", 2))
        self.publish_retry_delay = int(settings.get("meta_publish_retry_delay", 60))

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
            self._log_usage_headers(response, "IG create")

            if response.status_code != 200:
                raise requests.HTTPError(
                    build_meta_error_message("IG create failed", response),
                    response=response,
                )

            creation_id = response.json()["id"]
            self.logger.info(f"IG container created: {creation_id}")

            if media_type == "VIDEO":
                self._wait_for_video_processing(creation_id)

            return self._publish_creation_id(creation_id)
        except requests.exceptions.Timeout:
            self.logger.error("IG connection timed out")
            raise Exception("Timeout")
        except Exception as error:
            self.logger.error(f"IG error: {error}")
            raise

    def _publish_creation_id(self, creation_id):
        publish_url = f"{self.base_url}/media_publish"
        last_response = None

        for attempt in range(1, self.publish_retry_attempts + 1):
            publish_response = requests.post(
                publish_url,
                data={"creation_id": creation_id, "access_token": self.token},
                timeout=60,
            )
            self._log_usage_headers(publish_response, f"IG publish attempt {attempt}")

            if publish_response.status_code == 200:
                media_id = publish_response.json()["id"]
                self.logger.info(f"IG published successfully: {media_id}")
                return self._confirm_media_exists(media_id)

            last_response = publish_response
            meta_error = parse_meta_error(publish_response)
            message = build_meta_error_message("IG publish failed", publish_response)
            retryable = self._is_retryable_publish_error(meta_error)

            if retryable and attempt < self.publish_retry_attempts:
                wait_seconds = self.publish_retry_delay * attempt
                self.logger.warning(
                    f"{message}. Reusing same IG container and retrying publish in {wait_seconds}s"
                )
                time.sleep(wait_seconds)
                continue

            if retryable:
                raise MetaPublishRetryExhausted(message, response=publish_response)

            raise requests.HTTPError(message, response=publish_response)

        raise MetaPublishRetryExhausted(
            "IG publish failed after internal retries",
            response=last_response,
        )

    def _is_retryable_publish_error(self, meta_error):
        return (
            meta_error.get("is_transient") is True
            or meta_error.get("code") in {4, 17, 32, 341, 613}
            or meta_error.get("subcode") in {2207051}
        )

    def _log_usage_headers(self, response, label):
        app_usage = response.headers.get("x-app-usage")
        page_usage = response.headers.get("x-page-usage")
        business_usage = response.headers.get("x-business-use-case-usage")

        if app_usage:
            self.logger.info(f"{label} x-app-usage: {app_usage}")
        if page_usage:
            self.logger.info(f"{label} x-page-usage: {page_usage}")
        if business_usage:
            self.logger.info(f"{label} x-business-use-case-usage: {business_usage}")

    def _wait_for_video_processing(self, creation_id):
        self.logger.info("IG: waiting for reel processing")
        last_status = None

        for attempt in range(1, self.poll_attempts + 1):
            time.sleep(self.poll_interval)

            status_response = requests.get(
                f"https://graph.facebook.com/{self.api_version}/{creation_id}",
                params={
                    "fields": "status_code",
                    "access_token": self.token,
                },
                timeout=30,
            )
            self._log_usage_headers(status_response, f"IG status attempt {attempt}")

            if status_response.status_code != 200:
                self.logger.warning(f"IG poll error: {status_response.text}")
                continue

            data = status_response.json()
            status = data.get("status_code") or "UNKNOWN"
            last_status = status
            self.logger.info(f"IG poll attempt {attempt}: {status}")

            if status in {"FINISHED", "PUBLISHED"}:
                return

            if status in {"ERROR", "EXPIRED", "FAILED"}:
                raise Exception(f"IG video processing failed: status={status}")

        raise Exception(f"IG video processing timeout: last_status={last_status or 'UNKNOWN'}")

    def _confirm_media_exists(self, media_id):
        url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
        params = {"fields": "id", "access_token": self.token}

        for attempt in range(1, self.poll_attempts + 1):
            response = requests.get(url, params=params, timeout=30)
            self._log_usage_headers(response, f"IG confirm attempt {attempt}")

            if response.status_code == 200 and response.json().get("id"):
                self.logger.info(f"IG publish confirmed on attempt {attempt}")
                return True

            self.logger.warning(
                f"IG publish not visible yet on attempt {attempt}/{self.poll_attempts}"
            )
            if attempt < self.poll_attempts:
                time.sleep(self.poll_interval)

        raise Exception("IG publish confirmation timeout")
