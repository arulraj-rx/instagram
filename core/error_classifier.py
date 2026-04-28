class ErrorClassifier:
    @staticmethod
    def classify(error_msg, status_code=None, error_code=None, error_subcode=None, is_transient=None):
        msg = str(error_msg).lower()
        code = int(status_code) if status_code else None
        meta_code = int(error_code) if error_code not in (None, "") else None
        meta_subcode = int(error_subcode) if error_subcode not in (None, "") else None

        if is_transient is True:
            return "RETRY"

        # 1. AUTH ERRORS (Refresh Token)
        # 401 is the standard "Unauthorized" signal
        auth_triggers = ["401", "unauthorized", "expired", "token invalid"]
        if code == 401 or any(x in msg for x in auth_triggers):
            return "REFRESH"

        # 2. MEDIA ERRORS (Skip File)
        # 413: File too large, 415: Bad format, 422: Processing error
        media_codes = [413, 415, 422]
        media_triggers = ["payload too large", "unsupported media", "aspect ratio", "invalid format"]
        if code in media_codes or any(x in msg for x in media_triggers):
            return "SKIP"

        # 3. TEMPORARY ERRORS (Retry)
        # 429: Rate limit, 5xx: Server glitch
        retry_codes = [429, 500, 502, 503, 504]
        retry_triggers = [
            "timeout",
            "connection reset",
            "try again",
            "rate limit",
            "processing failed",
            "processing error",
            "publish confirmation timeout",
            "application request limit reached",
            "action is blocked",
        ]
        retry_meta_codes = {4, 17, 32, 341, 613}
        retry_meta_subcodes = {2207051}
        if (
            code in retry_codes
            or meta_code in retry_meta_codes
            or meta_subcode in retry_meta_subcodes
            or any(x in msg for x in retry_triggers)
        ):
            return "RETRY"

        # 4. PERMANENT ERRORS (Stop)
        # 400: Logic error, 403: Permission denied, 404: Missing endpoint
        stop_codes = [400, 403, 404, 405]
        if code in stop_codes or "forbidden" in msg:
            return "STOP"

        # Default fallback
        return "STOP"
