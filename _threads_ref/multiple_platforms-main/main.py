import os
import json
import time
import sys
from collections import defaultdict
from dotenv import load_dotenv

from core.retry_manager import SmartRetry
from core.verifier import MediaVerifier
from modules.dropbox_handler import DropboxHandler
from modules.caption_generator import CaptionGenerator
from modules.utils import setup_logging
from platforms.facebook import FacebookPoster
from platforms.threads import ThreadsPoster
from platforms.telegram import TelegramPoster
from platforms.discord import DiscordPoster
from platforms.tumblr import TumblrPoster


load_dotenv()
logger = setup_logging()

PLATFORM_RESULTS = defaultdict(lambda: {
    "success": 0,
    "failed": 0,
    "skipped": 0,
})

TEXT_EXTENSIONS = {".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def build_caption(payload, platform_name):
    if isinstance(payload, dict):
        text = str(payload.get("text", "")).strip()
        brand = str(payload.get("brand_tag", "")).strip()
        tags = payload.get("tags", [])

        limits = {"facebook": 4, "threads": 3, "telegram": 4, "discord": 4}
        tag_limit = limits.get(platform_name, 4)

        if isinstance(tags, str):
            tags = tags.split(",") if "," in tags else tags.split()

        tag_string = " ".join([f"#{str(tag).lstrip('#')}" for tag in tags[:tag_limit]])
        return f"{text}\n\n{tag_string}\n\n{brand}".strip()

    return str(payload)


def safe_trim_caption(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    logger.warning(f"Caption trimmed to {limit} characters")
    trimmed = text[:limit]
    return trimmed.rsplit(" ", 1)[0] or trimmed


def detect_file_type(filename):
    extension = os.path.splitext(filename)[1].lower()
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    return None


def read_text_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file_obj:
        return file_obj.read().strip()


def safe_post(platform_name, platform_obj, method_name, args, retry_engine,
              local_path=None, media_type=None):
    if media_type in {"image", "video"}:
        is_safe, msg = MediaVerifier.verify(local_path, platform_name, media_type)
        if not is_safe:
            logger.warning(f"{platform_name.upper()} skipped: {msg}")
            PLATFORM_RESULTS[platform_name]["skipped"] += 1
            return False

    try:
        logger.info(f"{platform_name.upper()} starting publish")
        method = getattr(platform_obj, method_name)
        result = retry_engine.execute(method, *args)

        if result is True:
            PLATFORM_RESULTS[platform_name]["success"] += 1
            logger.info(f"{platform_name.upper()} success")
            return True

        if result == "SKIPPED":
            PLATFORM_RESULTS[platform_name]["skipped"] += 1
            logger.warning(f"{platform_name.upper()} skipped by retry manager")
            return False

        PLATFORM_RESULTS[platform_name]["failed"] += 1
        logger.error(f"{platform_name.upper()} failed (API returned False)")
        return False
    except Exception as exc:
        PLATFORM_RESULTS[platform_name]["failed"] += 1
        logger.exception(f"{platform_name.upper()} exception: {str(exc)}")
        return False


def print_final_summary(enabled_platforms, total_platforms, dbx):
    total_success = sum(d["success"] for d in PLATFORM_RESULTS.values())
    total_failed = sum(d["failed"] for d in PLATFORM_RESULTS.values())
    total_skipped = sum(d["skipped"] for d in PLATFORM_RESULTS.values())
    dropbox_stats = dbx.get_folder_stats()
    failed_stats = dbx.get_failed_platform_stats(enabled_platforms)

    summary_lines = []
    summary_lines.append("=" * 60)
    summary_lines.append("UNIVERSAL WORKFLOW FINAL SUMMARY")
    summary_lines.append("=" * 60)
    summary_lines.append(f"Enabled Platforms : {len(enabled_platforms)}")
    summary_lines.append(f"Disabled Platforms: {total_platforms - len(enabled_platforms)}")
    summary_lines.append("-" * 60)
    summary_lines.append(f"Total Success     : {total_success}")
    summary_lines.append(f"Total Failed      : {total_failed}")
    summary_lines.append(f"Total Skipped     : {total_skipped}")
    summary_lines.append("=" * 60)

    for name in enabled_platforms:
        data = PLATFORM_RESULTS[name]
        summary_lines.append(
            f"{name.upper():10} -> "
            f"S:{data['success']} | "
            f"F:{data['failed']} | "
            f"SK:{data['skipped']}"
        )

    summary_lines.append("=" * 60)
    summary_lines.append("DROPBOX REMAINING FILES")
    summary_lines.append("-" * 60)
    summary_lines.append(f"Inbox           : {dropbox_stats['pending']}")
    summary_lines.append(f"Failed          : {dropbox_stats['failed']}")
    summary_lines.append("-" * 60)
    summary_lines.append(f"TOTAL FILES     : {dropbox_stats['total']}")
    summary_lines.append("=" * 60)
    summary_lines.append("FAILED FOLDER PLATFORM BREAKDOWN")
    summary_lines.append("-" * 60)

    for name in enabled_platforms:
        data = failed_stats["per_platform"].get(name, {"count": 0, "files": []})
        summary_lines.append(f"{name.upper():10} -> Failed Files: {data['count']}")

    summary_lines.append("-" * 60)
    summary_lines.append(
        f"Common Files Across Enabled Failed Folders: {failed_stats['common_count']}"
    )

    if failed_stats["common_files"]:
        summary_lines.append("Common File Names:")
        for filename in failed_stats["common_files"]:
            summary_lines.append(f" - {filename}")

    if failed_stats["shared_files"]:
        summary_lines.append("-" * 60)
        summary_lines.append("Files Present In Multiple Failed Platform Folders:")
        for filename, count in failed_stats["shared_files"].items():
            summary_lines.append(f" - {filename} -> {count} folders")
    summary_lines.append("=" * 60)

    logger.info("\n" + "\n".join(summary_lines))

    if total_success == 0 and total_failed > 0:
        sys.exit(1)

    sys.exit(0)


def main():
    logger.info("=" * 50)
    logger.info("UNIVERSAL ROTATING WORKFLOW STARTED")
    logger.info("=" * 50)

    with open("config.json", "r", encoding="utf-8-sig") as config_file:
        config = json.load(config_file)

    settings = config.get("settings", {})
    dbx = DropboxHandler(config["dropbox"])
    ai = CaptionGenerator(config)
    p_conf = config["platforms"]

    retry_engine = SmartRetry(
        max_attempts=settings.get("retry_count", 3),
        retry_delay=settings.get("retry_delay", 20),
    )
    delay = settings.get("post_delay", 10)

    mapping = {
        "facebook": FacebookPoster,
        "threads": ThreadsPoster,
        "telegram": TelegramPoster,
        "discord": DiscordPoster,
        "tumblr": TumblrPoster,
    }

    total_platforms = len(mapping)
    platforms = {
        name: cls(settings)
        for name, cls in mapping.items()
        if name in p_conf
    }
    enabled_names = list(platforms.keys())

    file_metadata = dbx.get_file()
    if not file_metadata or not enabled_names:
        print_final_summary(enabled_names, total_platforms, dbx)

    logger.info(f"Processing FILE -> {file_metadata.name}")
    file_type = detect_file_type(file_metadata.name)

    if not file_type:
        logger.warning(f"Unsupported file type: {file_metadata.name}")
        dbx.move_to_failed(file_metadata, enabled_names)
        print_final_summary(enabled_names, total_platforms, dbx)

    local_path = dbx.download_file(file_metadata)
    if not local_path:
        logger.error("Download failed, moving file to failed folder")
        dbx.move_to_failed(file_metadata, enabled_names)
        print_final_summary(enabled_names, total_platforms, dbx)

    failed_platforms = []

    if file_type == "text":
        text_content = read_text_file(local_path)
        if not text_content:
            logger.warning("Text file is empty")
            failed_platforms = enabled_names[:]
        else:
            for platform_name in enabled_names:
                limit = p_conf[platform_name].get("limit", 2000)
                final_text = safe_trim_caption(text_content, limit)
                result = safe_post(
                    platform_name,
                    platforms[platform_name],
                    "post_text",
                    (final_text,),
                    retry_engine,
                )
                if not result:
                    failed_platforms.append(platform_name)
                time.sleep(delay)
    else:
        caption_payload = ai.generate(file_metadata.name, file_type)
        public_url = dbx.get_public_media_url(file_metadata) if file_type in {"image", "video"} else None

        for platform_name in enabled_names:
            method_name = "post_video" if file_type == "video" else "post_image"

            if platform_name == "tumblr":
                post_args = (local_path, caption_payload)
            else:
                limit = p_conf[platform_name].get("limit", 2000)
                formatted = build_caption(caption_payload, platform_name)
                final_caption = safe_trim_caption(formatted, limit)
                post_target = public_url if platform_name == "threads" else local_path
                post_args = (post_target, final_caption)

            result = safe_post(
                platform_name,
                platforms[platform_name],
                method_name,
                post_args,
                retry_engine,
                local_path=local_path,
                media_type=file_type,
            )
            if not result:
                failed_platforms.append(platform_name)
            time.sleep(delay)

    if os.path.exists(local_path):
        os.remove(local_path)

    if failed_platforms:
        logger.warning(f"Failed platforms for {file_metadata.name}: {', '.join(failed_platforms)}")
        dbx.move_to_failed(file_metadata, failed_platforms)
        logger.warning("File copied to platform-specific failed folders")
    else:
        dbx.delete_file(file_metadata)
        logger.info("Dropbox file deleted (all targets success)")

    print_final_summary(enabled_names, total_platforms, dbx)


if __name__ == "__main__":
    main()
