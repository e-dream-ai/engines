from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from dotenv import load_dotenv

try:
    from edream_sdk.client import create_edream_client
    from edream_sdk.types.playlist_types import PlaylistItemType
except ImportError:
    print("Error: edream_sdk not installed. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

ENGINES_DIR = Path(__file__).resolve().parent.parent
IMAGE_URL_FIELDS = ("original_video", "video", "thumbnail")

Dream = dict[str, Any]


class EdreamClient(Protocol):
    def get_dream(self, uuid: str) -> Any: ...
    def create_dream_from_prompt(self, data: dict[str, Any]) -> Any: ...
    def create_playlist(self, data: dict[str, Any]) -> Any: ...
    def get_playlist(self, uuid: str, auto_populate: bool = True) -> Any: ...
    def get_playlist_items(self, uuid: str, take: int | None = None, skip: int | None = None) -> Any: ...
    def add_item_to_playlist(self, playlist_uuid: str, type: PlaylistItemType, item_uuid: str) -> Any: ...
    def download_file(self, url: str, file_path: str | None = None) -> bool: ...


@dataclass(frozen=True)
class SourceImage:
    uuid: str
    name: str
    url: str

    @property
    def ref(self) -> str:
        return self.uuid or self.url


@dataclass
class BatchResult:
    processed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    timed_out: list[str] = field(default_factory=list)


def bootstrap(config_file: str) -> tuple[EdreamClient, dict[str, Any]]:
    load_dotenv(ENGINES_DIR / ".env")
    if not os.environ.get("API_KEY"):
        load_dotenv(ENGINES_DIR.parent / ".env")

    api_key = os.environ.get("API_KEY")
    if not api_key:
        print("Error: API_KEY not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        print("Error: BACKEND_URL not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    config_path = ENGINES_DIR / "configs" / config_file
    if not config_path.exists():
        print(f"Error: {config_file} not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    client = create_edream_client(backend_url, api_key)
    print(f"Connected to {backend_url}")

    with open(config_path) as f:
        return client, json.load(f)


def _image_url(dream: Dream) -> str | None:
    for dream_field in IMAGE_URL_FIELDS:
        url = dream.get(dream_field)
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def resolve_source_images(client: EdreamClient, config: dict[str, Any]) -> list[SourceImage]:
    image_uuid = config.get("image_uuid")
    if image_uuid:
        dream = client.get_dream(image_uuid)
        if dream is None:
            raise ValueError(f"Source dream not found: {image_uuid}")
        url = _image_url(dream)
        if not url:
            raise ValueError(f"Source dream has no image URL: {image_uuid}")
        return [SourceImage(image_uuid, dream.get("name") or image_uuid, url)]

    playlist_uuid = config.get("image_playlist_uuid")
    if not playlist_uuid:
        raise ValueError("Config must set either 'image_uuid' or 'image_playlist_uuid'")

    images: list[SourceImage] = []
    take, skip = 50, 0
    while True:
        response = client.get_playlist_items(playlist_uuid, take=take, skip=skip)
        items = response.get("items", [])
        for item in items:
            if item.get("type") != "dream":
                continue
            dream = item.get("dreamItem") or {}
            url = _image_url(dream)
            if not url:
                continue
            uuid = dream.get("uuid", "")
            images.append(SourceImage(uuid, dream.get("name") or uuid or "dream", url))

        total = response.get("totalCount")
        skip += take
        if total is None or skip >= total:
            break

    if not images:
        raise ValueError(f"No image dreams found in playlist: {playlist_uuid}")
    return images


def get_or_create_playlist(client: EdreamClient, config: dict[str, Any], default_name: str) -> str:
    playlist_uuid = config.get("playlist_uuid")
    if playlist_uuid:
        try:
            client.get_playlist(playlist_uuid)
            return playlist_uuid
        except Exception as e:
            print(f"Cannot access playlist {playlist_uuid}, creating a new one: {e}", file=sys.stderr)

    playlist_config = config.get("playlist", {})
    playlist = client.create_playlist({
        "name": playlist_config.get("name", default_name),
        "description": playlist_config.get("description", ""),
        "nsfw": playlist_config.get("nsfw", False),
    })
    print(f"Created playlist: {playlist['uuid']}")
    return playlist["uuid"]


def submit_dream(
    client: EdreamClient,
    *,
    name: str,
    description: str,
    prompt: dict[str, Any],
    playlist_uuid: str,
    ccby_license: bool = True,
) -> str | None:
    try:
        dream = client.create_dream_from_prompt({
            "name": name,
            "description": description,
            "prompt": json.dumps(prompt),
            "ccbyLicense": ccby_license,
        })
    except Exception as e:
        print(f"  Failed to submit '{name}': {e}", file=sys.stderr)
        return None

    uuid = dream["uuid"]
    try:
        client.add_item_to_playlist(playlist_uuid=playlist_uuid, type=PlaylistItemType.DREAM, item_uuid=uuid)
    except Exception as e:
        print(f"Submitted {uuid} but failed to add to playlist: {e}", file=sys.stderr)
    return uuid


def poll_until_complete(
    client: EdreamClient,
    dream_uuids: list[str],
    *,
    on_processed: Callable[[Dream], None] | None = None,
    poll_interval: int = 10,
    max_wait: int = 7200,
) -> BatchResult:
    pending = set(dream_uuids)
    result = BatchResult()
    start = time.time()

    while pending and (time.time() - start) < max_wait:
        for uuid in list(pending):
            try:
                dream = client.get_dream(uuid)
            except Exception as e:
                print(f"Error polling {uuid}: {e}", file=sys.stderr)
                continue
            if dream is None:
                continue

            status = dream.get("status")
            if status == "processed":
                pending.discard(uuid)
                result.processed.append(uuid)
                print(f"Done: {uuid}")
                if on_processed is not None:
                    on_processed(dream)
            elif status == "failed":
                pending.discard(uuid)
                result.failed.append(uuid)
                print(f"Failed: {uuid} ({dream.get('error')})", file=sys.stderr)

        if pending:
            time.sleep(poll_interval)

    result.timed_out.extend(pending)
    return result


def resolve_output_dir(output_folder: str) -> Path:
    path = Path(output_folder)
    output_dir = path if path.is_absolute() else ENGINES_DIR / path
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def download_image(client: EdreamClient, dream: Dream, output_path: Path) -> bool:
    url = _image_url(dream)
    if not url:
        print(f"No image URL for {dream.get('uuid')}", file=sys.stderr)
        return False
    if client.download_file(url, str(output_path)):
        print(f"Downloaded: {output_path}")
        return True
    print(f"Download failed: {dream.get('uuid')}", file=sys.stderr)
    return False
