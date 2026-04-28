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
from platforms.threads import ThreadsPoster


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


def read_text_file(file_path):
    with open(file_path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def main():
    logger.info("=" * 50)
    logger.info("INSTAGRAM + THREADS DROPBOX WORKFLOW STARTED")
    logger.info("=" * 50)

    config = load_config()
    dropbox_handler = DropboxHandler(config["dropbox"])
    caption_generator = CaptionGenerator(config)
    instagram = InstagramPoster()
    threads = ThreadsPoster(config)
    retry_engine = SmartRetry(max_attempts=config.get("retry_count", 3))
    caption_limit = int(config.get("caption_limit", 2200))
    threads_text_limit = int(config.get("threads_text_limit", 500))
    threads_caption_limit = int(config.get("threads_caption_limit", caption_limit))

    text_metadata = dropbox_handler.get_next_text_file()
    if text_metadata:
        logger.info(f"Selected Threads text file: {text_metadata.name}")

        local_path = dropbox_handler.download_file(text_metadata)
        if not local_path:
            logger.error("Dropbox text download failed")
            dropbox_handler.move_to_failed(text_metadata)
            sys.exit(1)

        try:
            text_content = safe_trim_caption(read_text_file(local_path), threads_text_limit)
            if not text_content:
                raise Exception("Threads text file is empty")

            result = retry_engine.execute(threads.post_text, text_content)
            if result is True:
                dropbox_handler.delete_file(text_metadata)
                logger.info("Threads text post successful, Dropbox source file deleted")
                if os.path.exists(local_path):
                    os.remove(local_path)
                sys.exit(0)

            logger.error("Threads text upload returned an unexpected result")
        except Exception as exc:
            logger.exception(f"Threads text upload failed: {exc}")

        if os.path.exists(local_path):
            os.remove(local_path)
        dropbox_handler.move_to_failed(text_metadata)
        logger.warning("Threads text file moved to failed folder")
        sys.exit(1)

    file_metadata = dropbox_handler.get_next_file()
    if not file_metadata:
        logger.info("No supported image or video files found in the Dropbox source folder")
        sys.exit(0)

    logger.info(f"Selected Dropbox media file: {file_metadata.name}")

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
    threads_caption = safe_trim_caption(caption, threads_caption_limit)

    try:
        instagram_method = instagram.post_video if media_type == "video" else instagram.post_image
        instagram_result = retry_engine.execute(instagram_method, public_url, caption)

        if instagram_result is not True:
            raise Exception("Instagram upload returned an unexpected result")

        threads_url = dropbox_handler.get_temp_link(file_metadata)
        if not threads_url:
            raise Exception("Could not create Dropbox temporary link for Threads")

        threads_method = threads.post_video if media_type == "video" else threads.post_image
        threads_result = retry_engine.execute(threads_method, threads_url, threads_caption)

        if threads_result is True:
            dropbox_handler.delete_file(file_metadata)
            logger.info("Instagram and Threads posts successful, Dropbox source file deleted")
            if os.path.exists(local_path):
                os.remove(local_path)
            sys.exit(0)

        logger.error("Threads upload returned an unexpected result")
    except Exception as exc:
        logger.exception(f"Media upload failed: {exc}")

    if os.path.exists(local_path):
        os.remove(local_path)
    dropbox_handler.move_to_failed(file_metadata)
    logger.warning("File moved to failed folder")
    sys.exit(1)


if __name__ == "__main__":
    main()
