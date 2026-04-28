class ErrorClassifier:
    @staticmethod
    def classify(error_msg, status_code=None):
        msg = str(error_msg).lower()
        code = int(status_code) if status_code else None

        auth_triggers = ["401", "unauthorized", "expired", "token invalid"]
        if code == 401 or any(x in msg for x in auth_triggers):
            return "REFRESH"

        media_codes = [413, 415, 422]
        media_triggers = ["payload too large", "unsupported media", "aspect ratio", "invalid format"]
        if code in media_codes or any(x in msg for x in media_triggers):
            return "SKIP"

        retry_codes = [429, 500, 502, 503, 504]
        retry_triggers = ["timeout", "connection reset", "try again", "rate limit"]
        if code in retry_codes or any(x in msg for x in retry_triggers):
            return "RETRY"

        stop_codes = [400, 403, 404, 405]
        if code in stop_codes or "forbidden" in msg:
            return "STOP"

        return "STOP"
