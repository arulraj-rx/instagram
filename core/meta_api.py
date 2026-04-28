import json


class MetaPublishRetryExhausted(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response
        self.status_code = getattr(response, "status_code", None)
        self.headers = getattr(response, "headers", {}) or {}
        self.disable_outer_retry = True


def parse_meta_error(response):
    if response is None:
        return {}

    try:
        payload = response.json()
    except Exception:
        try:
            payload = json.loads(response.text)
        except Exception:
            payload = {}

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    return {
        "message": error.get("message"),
        "type": error.get("type"),
        "code": error.get("code"),
        "subcode": error.get("error_subcode"),
        "is_transient": error.get("is_transient"),
        "user_title": error.get("error_user_title"),
        "user_msg": error.get("error_user_msg"),
        "fbtrace_id": error.get("fbtrace_id"),
    }


def build_meta_error_message(prefix, response):
    details = parse_meta_error(response)
    if details.get("message"):
        extra = []
        if details.get("code") is not None:
            extra.append(f"code={details['code']}")
        if details.get("subcode") is not None:
            extra.append(f"subcode={details['subcode']}")
        if details.get("user_title"):
            extra.append(f"title={details['user_title']}")
        if details.get("user_msg"):
            extra.append(f"user_msg={details['user_msg']}")
        if details.get("fbtrace_id"):
            extra.append(f"fbtrace_id={details['fbtrace_id']}")

        suffix = f" ({', '.join(extra)})" if extra else ""
        return f"{prefix}: {details['message']}{suffix}"

    return f"{prefix}: {getattr(response, 'text', 'Unknown Meta error')}"
