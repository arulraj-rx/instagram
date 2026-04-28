import time
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from .error_classifier import ErrorClassifier


class SmartRetry:
    def __init__(self, max_attempts=5, retry_delay=20, max_backoff=900):
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.max_backoff = max_backoff
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _parse_retry_after(value):
        if value is None:
            return None

        try:
            return max(0, int(str(value).strip()))
        except Exception:
            pass

        try:
            dt = parsedate_to_datetime(str(value))
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            return None

    def execute(self, func, *args, **kwargs):
        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
                headers = getattr(exc, "headers", None) or getattr(response, "headers", {}) or {}
                action = ErrorClassifier.classify(str(exc), status_code=status_code)

                if action == "STOP":
                    self.logger.error(f"Permanent error: {exc}. Stopping.")
                    raise

                if action == "REFRESH":
                    self.logger.critical("Token expired. Stop and refresh manually.")
                    raise

                if action == "SKIP":
                    self.logger.warning("Media error. Skipping this file.")
                    return "SKIPPED"

                if attempt == self.max_attempts - 1:
                    self.logger.error("Max retries reached.")
                    raise

                retry_after = self._parse_retry_after(headers.get("Retry-After"))
                wait_seconds = retry_after if retry_after is not None else self.retry_delay
                wait_seconds = min(wait_seconds, self.max_backoff)

                self.logger.warning(
                    f"{action} error. Attempt {attempt + 1}/{self.max_attempts}. Retrying in {wait_seconds}s..."
                )
                time.sleep(wait_seconds)
