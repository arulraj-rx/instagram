import os
import logging

class MediaVerifier:
    # Limits in Megabytes (MB)
    LIMITS = {
        'discord':   {'image': 10,  'video': 10},   # Recent 2026 adjustment
        'facebook':  {'image': 30,  'video': 1024}, # Large video support, 30MB images
        'telegram':  {'image': 10,  'video': 50},   # Bot API limit is 50MB for videos
        'threads':   {'image': 8,   'video': 1024}, # 8MB JPEG limit, 1GB video
        'tumblr':    {'image': 10,  'video': 100}   # Conservative 10MB/100MB limits
    }

    @staticmethod
    def verify(file_path, platform_name, media_type):
        """
        Validates if a file meets platform-specific size requirements.
        media_type: 'image' or 'video'
        """
        logger = logging.getLogger(__name__)
        
        if not os.path.exists(file_path):
            return False, "File not found on local disk"

        # Get file size in MB
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        # Get platform limits
        platform_limits = MediaVerifier.LIMITS.get(platform_name.lower())
        if not platform_limits:
            return True, "No limits defined for this platform, proceeding..."

        max_allowed = platform_limits.get(media_type.lower(), 10) # Default 10MB if type missing

        if file_size_mb > max_allowed:
            error_msg = f"File too large: {file_size_mb:.2f}MB (Max {max_allowed}MB for {platform_name} {media_type})"
            logger.warning(f"   ⚠️ {error_msg}")
            return False, error_msg

        return True, "Safe"
