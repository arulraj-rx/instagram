import logging
import os

import dropbox
from dropbox.exceptions import ApiError


class DropboxHandler:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

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

    def get_next_file(self):
        files = [
            entry
            for entry in self._list_files(self.conf["source_folder"])
            if self.detect_media_type(entry.name) in {"image", "video"}
        ]
        if not files:
            return None

        selected = random.choice(files)
        self.logger.info(f"Randomly selected file: {selected.name}")
        return selected

    def detect_media_type(self, filename):
        extension = os.path.splitext(filename)[1].lower()
        if extension in self.IMAGE_EXTENSIONS:
            return "image"
        if extension in self.VIDEO_EXTENSIONS:
            return "video"
        return None

    def _list_files(self, path):
        try:
            client = self._get_client()
            results = client.files_list_folder(path)
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
        except Exception as error:
            self.logger.error(f"Dropbox list error ({path}): {error}")
            return []

    def download_file(self, file_metadata):
        try:
            client = self._get_client()
            local_path = os.path.abspath(f"temp_{file_metadata.name}")
            client.files_download_to_file(local_path, file_metadata.path_lower)
            return local_path
        except Exception as error:
            self.logger.error(f"Download failed: {error}")
            return None

    def get_temp_link(self, file_metadata):
        try:
            client = self._get_client()
            return client.files_get_temporary_link(file_metadata.path_lower).link
        except Exception as error:
            self.logger.error(f"Temporary link failed: {error}")
            return None

    def delete_file(self, file_metadata):
        try:
            client = self._get_client()
            client.files_delete_v2(file_metadata.path_lower)
            self.logger.info(f"Deleted {file_metadata.name} from Dropbox")
        except Exception as error:
            self.logger.error(f"Delete failed: {error}")

    def move_to_failed(self, file_metadata):
        client = self._get_client()
        failed_folder = self.conf["failed_folder"].rstrip("/")
        destination = f"{failed_folder}/{file_metadata.name}"

        try:
            self._ensure_folder(failed_folder)
            client.files_move_v2(file_metadata.path_lower, destination, autorename=True)
            self.logger.warning(f"Moved failed file to {destination}")
        except Exception as error:
            self.logger.error(f"Move to failed error: {error}")

    def _ensure_folder(self, folder_path):
        client = self._get_client()
        segments = [segment for segment in folder_path.split("/") if segment]
        current = ""

        for segment in segments:
            current = f"{current}/{segment}"
            try:
                client.files_create_folder_v2(current)
            except ApiError as error:
                if error.error.is_path() and error.error.get_path().is_conflict():
                    continue
                raise
