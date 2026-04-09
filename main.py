import json
import os
import sys

from dotenv import load_dotenv

from core.retry_manager import SmartRetry
from core.verifier import MediaVerifier
from modules.caption_generator import CaptionGenerator
from modules.dropbox_handler import DropboxHandler
from modules.utils import setup_logging
from platforms.instagram import InstagramPoster


load_dotenv()
logger = setup_logging()


def safe_trim_caption(text: str, limit: int) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized

    logger.warning(f"Caption trimmed to {limit} characters")
    return normalized[:limit].rsplit(" ", 1)[0]


def load_config():
    with open("config.json", "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def main():
    logger.info("=" * 50)
    logger.info("INSTAGRAM DROPBOX WORKFLOW STARTED")
    logger.info("=" * 50)

    config = load_config()
    dropbox_handler = DropboxHandler(config["dropbox"])
    caption_generator = CaptionGenerator(config)
    instagram = InstagramPoster()
    retry_engine = SmartRetry(max_attempts=config.get("retry_count", 3))
    caption_limit = int(config.get("caption_limit", 2200))

    file_metadata = dropbox_handler.get_next_file()
    if not file_metadata:
        logger.info("No supported image or video files found in the Dropbox source folder")
        sys.exit(0)

    logger.info(f"Selected Dropbox file: {file_metadata.name}")

    local_path = dropbox_handler.download_file(file_metadata)
    if not local_path:
        logger.error("Dropbox download failed")
        dropbox_handler.move_to_failed(file_metadata)
        sys.exit(1)

    media_type = dropbox_handler.detect_media_type(file_metadata.name)
    if media_type not in {"image", "video"}:
        logger.error(f"Unsupported media type for {file_metadata.name}")
        if os.path.exists(local_path):
            os.remove(local_path)
        dropbox_handler.move_to_failed(file_metadata)
        sys.exit(1)

    is_safe, message = MediaVerifier.verify(local_path, "instagram", media_type)
    if not is_safe:
        logger.warning(f"Instagram skipped: {message}")
        if os.path.exists(local_path):
            os.remove(local_path)
        dropbox_handler.move_to_failed(file_metadata)
        sys.exit(1)

    public_url = dropbox_handler.get_temp_link(file_metadata)
    if not public_url:
        logger.error("Could not create Dropbox temporary link")
        if os.path.exists(local_path):
            os.remove(local_path)
        dropbox_handler.move_to_failed(file_metadata)
        sys.exit(1)

    caption = safe_trim_caption(
        caption_generator.generate(file_metadata.name, media_type),
        caption_limit,
    )

    try:
        post_method = instagram.post_video if media_type == "video" else instagram.post_image
        result = retry_engine.execute(post_method, public_url, caption)

        if result is True:
            dropbox_handler.delete_file(file_metadata)
            logger.info("Instagram post successful, Dropbox source file deleted")
            if os.path.exists(local_path):
                os.remove(local_path)
            sys.exit(0)

        logger.error("Instagram upload returned an unexpected result")
    except Exception as exc:
        logger.exception(f"Instagram upload failed: {exc}")

    if os.path.exists(local_path):
        os.remove(local_path)
    dropbox_handler.move_to_failed(file_metadata)
    logger.warning("File moved to failed folder")
    sys.exit(1)


if __name__ == "__main__":
    main()
