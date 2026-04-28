import logging
import os
import random
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import dropbox
from dropbox.exceptions import ApiError


class DropboxHandler:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
    TEXT_EXTENSIONS = {".txt"}

    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.conf = config
        self.client = None

    def _get_client(self):
        if self.client is None:
            self.client = dropbox.Dropbox(
                app_key=os.getenv("DROPBOX_APP_KEY"),
                app_secret=os.getenv("DROPBOX_APP_SECRET"),
                oauth2_refresh_token=os.getenv("DROPBOX_REFRESH_TOKEN"),
                timeout=30,
            )
            self.logger.info("Dropbox client initialized")
        return self.client

    # ✅ detect type
    def detect_media_type(self, filename):
        ext = os.path.splitext(filename)[1].lower()

        if ext in self.IMAGE_EXTENSIONS:
            return "image"
        elif ext in self.VIDEO_EXTENSIONS:
            return "video"
        elif ext in self.TEXT_EXTENSIONS:
            return "text"

        return None

    # ✅ UPDATED: weighted file selection
    def get_file(self):
        path = self.conf.get("folder")
        if not path:
            return None

        files = self._list_files(path)

        images = []
        videos = []
        texts = []

        for entry in files:
            media_type = self.detect_media_type(entry.name)

            if media_type == "image":
                images.append(entry)
            elif media_type == "video":
                videos.append(entry)
            elif media_type == "text":
                texts.append(entry)

        if not images and not videos and not texts:
            self.logger.warning("No valid files found")
            return None

        # 🎯 CHANGE RATIO HERE
        types = ["image", "video", "text"]
        weights = [20, 60, 20]

        selected_type = random.choices(types, weights=weights)[0]

        if selected_type == "image" and images:
            selected = random.choice(images)
        elif selected_type == "video" and videos:
            selected = random.choice(videos)
        elif selected_type == "text" and texts:
            selected = random.choice(texts)
        else:
            # fallback
            selected = random.choice(images or videos or texts)
            selected_type = self.detect_media_type(selected.name)
        
        actual_type = self.detect_media_type(selected.name)
        
        self.logger.info(
            f"Selected {actual_type}: {selected.name} | "
            f"I={len(images)}, V={len(videos)}, T={len(texts)}"
        )

        return selected

    def get_folder_stats(self):
        inbox_files = self._list_files(self.conf.get("folder", ""))
        failed_files = self._list_files(self.conf.get("failed_folder", ""), recursive=True)
        return {
            "pending": len(inbox_files),
            "failed": len(failed_files),
            "total": len(inbox_files) + len(failed_files),
        }

    def get_failed_platform_stats(self, platform_names=None):
        failed_root = self.conf.get("failed_folder", "/failed")
        normalized = []

        for name in platform_names or []:
            value = str(name).strip().lower()
            if value and value not in normalized:
                normalized.append(value)

        per_platform = {}
        filename_sets = []
        filename_counter = Counter()

        for platform_name in normalized:
            failed_path = f"{failed_root}/{platform_name}"
            files = self._list_files(failed_path, recursive=True)
            names = sorted({entry.name for entry in files})

            per_platform[platform_name] = {
                "count": len(files),
                "files": names,
            }
            filename_sets.append(set(names))
            filename_counter.update(names)

        common_files = (
            sorted(set.intersection(*filename_sets))
            if filename_sets else []
        )
        shared_files = {
            name: count
            for name, count in sorted(filename_counter.items())
            if count > 1
        }

        return {
            "per_platform": per_platform,
            "common_files": common_files,
            "common_count": len(common_files),
            "shared_files": shared_files,
            "filename_occurrences": dict(sorted(filename_counter.items())),
        }

    def _list_files(self, path, recursive=False):
        if not path:
            return []

        try:
            client = self._get_client()
            results = client.files_list_folder(path, recursive=recursive)

            files = [
                entry
                for entry in results.entries
                if isinstance(entry, dropbox.files.FileMetadata)
            ]

            while results.has_more:
                results = client.files_list_folder_continue(results.cursor)
                files.extend(
                    entry
                    for entry in results.entries
                    if isinstance(entry, dropbox.files.FileMetadata)
                )

            return files

        except Exception as exc:
            self.logger.error(f"Dropbox list error ({path}): {exc}")
            return []

    def download_file(self, file_metadata):
        try:
            client = self._get_client()
            local_path = f"temp_{file_metadata.name}"
            client.files_download_to_file(local_path, file_metadata.path_lower)
            return local_path
        except Exception as exc:
            self.logger.error(f"Download failed: {exc}")
            return None

    def get_temp_link(self, file_metadata):
        try:
            client = self._get_client()
            return client.files_get_temporary_link(file_metadata.path_lower).link
        except Exception as exc:
            self.logger.error(f"Temp link failed: {exc}")
            return None

    @staticmethod
    def _to_direct_shared_media_url(url):
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.pop("dl", None)
        query["raw"] = "1"
        return urlunparse(parsed._replace(query=urlencode(query)))

    def get_public_media_url(self, file_metadata):
        try:
            client = self._get_client()
            links = client.sharing_list_shared_links(
                path=file_metadata.path_lower,
                direct_only=True,
            ).links

            if links:
                shared_url = links[0].url
            else:
                shared_url = client.sharing_create_shared_link_with_settings(
                    file_metadata.path_lower
                ).url

            direct_url = self._to_direct_shared_media_url(shared_url)
            self.logger.info(f"Using Dropbox shared media URL for {file_metadata.name}")
            return direct_url
        except Exception as exc:
            self.logger.warning(f"Shared media URL failed for {file_metadata.name}: {exc}")
            return self.get_temp_link(file_metadata)

    def delete_file(self, file_metadata):
        try:
            client = self._get_client()
            client.files_delete_v2(file_metadata.path_lower)
            self.logger.info(f"Deleted {file_metadata.name} from Dropbox")
        except Exception as exc:
            self.logger.error(f"Delete failed: {exc}")

    def _ensure_folder(self, path):
        client = self._get_client()
        try:
            client.files_create_folder_v2(path)
        except ApiError as exc:
            if exc.error.is_path() and exc.error.get_path().is_conflict():
                return
            raise

    def move_to_failed(self, file_metadata, platform_names=None):
        client = self._get_client()
        failed_root = self.conf.get("failed_folder", "/failed")

        targets = platform_names or ["unclassified"]
        targets = [str(target).strip().lower() for target in targets if str(target).strip()]
        targets = list(dict.fromkeys(targets))

        try:
            self._ensure_folder(failed_root)

            for target in targets:
                failed_path = f"{failed_root}/{target}"
                destination = f"{failed_path}/{file_metadata.name}"

                self._ensure_folder(failed_path)

                client.files_copy_v2(
                    file_metadata.path_lower,
                    destination,
                    autorename=True,
                )

                self.logger.warning(f"Copied failed file to {destination}")

            client.files_delete_v2(file_metadata.path_lower)
            self.logger.warning(f"Removed source file: {file_metadata.name}")

        except Exception as exc:
            self.logger.error(f"Move to failed error: {exc}")
