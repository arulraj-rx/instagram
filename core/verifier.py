import logging
import os


class MediaVerifier:
    LIMITS = {
        "instagram": {"image": 8, "video": 300}
    }

    @staticmethod
    def verify(file_path, platform_name, media_type):
        logger = logging.getLogger(__name__)

        if not os.path.exists(file_path):
            return False, "File not found on local disk"

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        platform_limits = MediaVerifier.LIMITS.get(platform_name.lower())
        if not platform_limits:
            return True, "No limits defined for this platform"

        max_allowed = platform_limits.get(media_type.lower(), 10)
        if file_size_mb > max_allowed:
            error_message = (
                f"File too large: {file_size_mb:.2f}MB "
                f"(Max {max_allowed}MB for {platform_name} {media_type})"
            )
            logger.warning(error_message)
            return False, error_message

        return True, "Safe"
