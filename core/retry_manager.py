import time
import random
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from .error_classifier import ErrorClassifier


def backoff_with_full_jitter(attempt, base=2, cap=900):
    exp = base * (2 ** attempt)
    wait = min(cap, exp)
    return random.uniform(0, wait)


class SmartRetry:
    def __init__(self, max_attempts=5, backoff_base=5, max_backoff=900):
        # cap exponential growth to avoid unbounded waits
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _parse_retry_after(value):
        if value is None:
            return None

        # Retry-After can be delta-seconds or an HTTP date.
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
        # func may return a result or raise an exception with optional status_code/headers
        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                response = getattr(e, "response", None)
                status_code = getattr(e, "status_code", None) or getattr(response, "status_code", None)
                headers = getattr(e, "headers", None) or getattr(response, "headers", {}) or {}
                action = ErrorClassifier.classify(str(e), status_code=status_code)

                if action == "STOP":
                    self.logger.error(f"Permanent error: {e}. Stopping.")
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
                if status_code == 429:
                    wait_seconds = retry_after if retry_after is not None else 30
                    wait_seconds = min(wait_seconds, self.max_backoff)
                    self.logger.warning(
                        f"Rate limit hit (429). Sleeping for {wait_seconds}s before retry..."
                    )
                    time.sleep(wait_seconds + 1)
                    continue

                wait = (
                    min(retry_after, self.max_backoff)
                    if retry_after is not None
                    else backoff_with_full_jitter(
                        attempt, base=self.backoff_base, cap=self.max_backoff
                    )
                )

                self.logger.warning(
                    f"{action} error. Attempt {attempt + 1}/{self.max_attempts}. Retrying in {wait:.1f}s..."
                )
                time.sleep(wait)
