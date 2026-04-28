import os
import time
import logging
import requests


class ThreadsPoster:
    VALID_REPLY_CONTROLS = {"everyone", "accounts_you_follow", "mentioned_only"}

    def __init__(self, settings=None):
        settings = settings or {}
        self.logger = logging.getLogger(__name__)
        self.user_id = os.getenv("THREADS_USER_ID")
        self.token = os.getenv("THREADS_ACCESS_TOKEN")
        self.api_host = "https://graph.threads.net/v1.0"
        self.base_url = f"{self.api_host}/me"
        self.poll_interval = settings.get("poll_interval", 20)
        self.poll_attempts = settings.get("poll_attempts", 3)
        self.publish_poll_attempts = settings.get(
            "threads_publish_poll_attempts",
            self.poll_attempts,
        )
        self.processing_poll_attempts = settings.get(
            "threads_processing_poll_attempts",
            max(self.poll_attempts, 6),
        )
        self.reply_control = self._normalize_reply_control(
            settings.get("threads_reply_control")
        )
        self.enable_reply_approvals = bool(
            settings.get("threads_enable_reply_approvals", False)
        )
        self.auto_publish_text = bool(
            settings.get("threads_auto_publish_text", True)
        )
        self.topic_tag = str(settings.get("threads_topic_tag", "")).strip()
        self.location_id = str(settings.get("threads_location_id", "")).strip()

    @classmethod
    def _normalize_reply_control(cls, value):
        if value is None:
            return None

        normalized = str(value).strip().lower()
        if normalized in cls.VALID_REPLY_CONTROLS:
            return normalized
        return None

    def _build_base_params(self, text=None):
        params = {"access_token": self.token}

        if text is not None:
            params["text"] = text
        if self.reply_control:
            params["reply_control"] = self.reply_control
        if self.enable_reply_approvals:
            params["enable_reply_approvals"] = "true"
        if self.topic_tag:
            params["topic_tag"] = self.topic_tag
        if self.location_id:
            params["location_id"] = self.location_id

        return params

    def _post(self, endpoint, params, timeout=60, error_label="Threads request failed"):
        response = requests.post(endpoint, params=params, timeout=timeout)
        if response.status_code != 200:
            raise requests.HTTPError(f"{error_label}: {response.text}", response=response)
        return response

    def _get(self, endpoint, params, timeout=30, error_label="Threads request failed"):
        response = requests.get(endpoint, params=params, timeout=timeout)
        if response.status_code != 200:
            raise requests.HTTPError(f"{error_label}: {response.text}", response=response)
        return response

    def post_image(self, image_url, caption):
        return self._create_media_post(image_url, caption, "IMAGE")

    def post_video(self, video_url, caption):
        return self._create_media_post(video_url, caption, "VIDEO")

    def post_text(self, text):
        return self._create_text_post(text)

    def _poll_thread(self, thread_id):
        if not thread_id:
            return False

        url = f"{self.api_host}/{thread_id}"
        params = self._build_base_params()
        params["fields"] = "id"

        for attempt in range(1, self.publish_poll_attempts + 1):
            res = requests.get(url, params=params, timeout=30)
            if res.status_code == 200 and res.json().get("id"):
                self.logger.info(f"   Threads publish confirmed on poll attempt {attempt}")
                return True

            self.logger.warning(
                f"   Threads poll attempt {attempt}/{self.publish_poll_attempts} pending"
            )
            if attempt < self.publish_poll_attempts:
                time.sleep(self.poll_interval)

        return False

    def _wait_for_container(self, container_id):
        check_url = f"{self.api_host}/{container_id}"
        params = self._build_base_params()
        params["fields"] = "status,error_message"

        for attempt in range(1, self.processing_poll_attempts + 1):
            time.sleep(self.poll_interval)
            check_res = self._get(
                check_url,
                params=params,
                timeout=30,
                error_label="Threads Status Check Failed",
            )

            data = check_res.json()
            status = data.get("status", "ERROR")
            self.logger.info(f"   Threads processing status: {status} (attempt {attempt})")

            if status == "FINISHED":
                return True
            if status == "ERROR":
                details = data.get("error_message") or "UNKNOWN"
                raise Exception(f"Threads Processing Error: {details}")
            if status == "PUBLISHED":
                return True
            if status not in {"IN_PROGRESS"}:
                self.logger.warning(f"   Threads returned unexpected container status: {status}")

        return False

    def _publish_container(self, container_id):
        pub_url = f"{self.base_url}/threads_publish"
        params = self._build_base_params()
        params["creation_id"] = container_id
        pub_res = self._post(
            pub_url,
            params=params,
            timeout=60,
            error_label="Threads Publish Failed",
        )

        thread_id = pub_res.json().get("id")
        return self._poll_thread(thread_id)

    def _create_media_container(self, media_url, caption, media_type):
        if not media_url or not str(media_url).strip():
            raise ValueError("Threads media URL is required for image/video posts")

        url = f"{self.base_url}/threads"
        payload = self._build_base_params(caption)
        payload["media_type"] = media_type
        payload["image_url" if media_type == "IMAGE" else "video_url"] = str(media_url).strip()

        res = self._post(
            url,
            params=payload,
            timeout=60,
            error_label="Threads Init Failed",
        )
        return res.json().get("id")

    def _create_media_post(self, media_url, caption, media_type):
        container_id = self._create_media_container(media_url, caption, media_type)
        if not self._wait_for_container(container_id):
            return False

        return self._publish_container(container_id)

    def _create_text_post(self, text):
        url = f"{self.base_url}/threads"
        payload = self._build_base_params(text)
        payload["media_type"] = "TEXT"

        if self.auto_publish_text:
            payload["auto_publish_text"] = "true"

        res = self._post(
            url,
            params=payload,
            timeout=60,
            error_label="Threads Text Init Failed",
        )
        creation_id = res.json().get("id")

        if self.auto_publish_text:
            return self._poll_thread(creation_id)

        return self._publish_container(creation_id)
