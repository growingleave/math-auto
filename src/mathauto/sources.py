"""Uniform access to a folder of files, whether it lives locally or in Google Drive.

Both LocalFolderSource and DriveFolderSource expose the same list_files /
read_bytes / upload interface so the matching and pipeline logic never needs
to know where the files actually came from. This also lets the matcher be
tested fully offline against a local folder of sample files.
"""

from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    id: str
    name: str
    parent_name: str
    mime_type: str


class FileSource(ABC):
    @abstractmethod
    def list_files(self) -> list[SourceFile]:
        ...

    @abstractmethod
    def read_bytes(self, file: SourceFile) -> bytes:
        ...

    @abstractmethod
    def upload(self, local_path: str | Path, name: str) -> str:
        """Upload a generated file (the workbook PDF). Returns an id/url/path for it."""


class LocalFolderSource(FileSource):
    def __init__(self, root: str | Path, output_dir: str | Path | None = None):
        self.root = Path(root)
        self.output_dir = Path(output_dir) if output_dir else self.root / "output"

    def list_files(self) -> list[SourceFile]:
        files = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            parent_name = "" if path.parent == self.root else path.parent.name
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            files.append(SourceFile(id=str(path), name=path.name, parent_name=parent_name, mime_type=mime_type))
        return files

    def read_bytes(self, file: SourceFile) -> bytes:
        return Path(file.id).read_bytes()

    def upload(self, local_path: str | Path, name: str) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        dest = self.output_dir / name
        dest.write_bytes(Path(local_path).read_bytes())
        return str(dest)


class DriveFolderSource(FileSource):
    """Reads/writes a Google Drive folder tree via a service account.

    Requires google-api-python-client + google-auth (see requirements.txt).
    The service account must have at least read access to `folder_id` and
    write access to `output_folder_id` (defaults to the same folder).
    """

    DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self, folder_id: str, credentials_path: str, output_folder_id: str | None = None):
        self.folder_id = folder_id
        self.output_folder_id = output_folder_id or folder_id
        self._service = self._build_service(credentials_path)

    def _build_service(self, credentials_path: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=creds)

    def list_files(self) -> list[SourceFile]:
        files: list[SourceFile] = []
        to_visit = [(self.folder_id, "")]
        visited: set[str] = set()
        while to_visit:
            folder_id, parent_label = to_visit.pop()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            page_token = None
            while True:
                resp = (
                    self._service.files()
                    .list(
                        q=f"'{folder_id}' in parents and trashed = false",
                        fields="nextPageToken, files(id, name, mimeType)",
                        pageToken=page_token,
                    )
                    .execute()
                )
                for f in resp.get("files", []):
                    if f["mimeType"] == self.DRIVE_FOLDER_MIME:
                        to_visit.append((f["id"], f["name"]))
                    else:
                        files.append(
                            SourceFile(id=f["id"], name=f["name"], parent_name=parent_label, mime_type=f["mimeType"])
                        )
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        return files

    def read_bytes(self, file: SourceFile) -> bytes:
        import io

        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().get_media(fileId=file.id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def upload(self, local_path: str | Path, name: str) -> str:
        from googleapiclient.http import MediaFileUpload

        metadata = {"name": name, "parents": [self.output_folder_id]}
        media = MediaFileUpload(str(local_path), mimetype="application/pdf")
        created = (
            self._service.files()
            .create(body=metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return created.get("webViewLink") or created["id"]
