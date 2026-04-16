import json
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Set
from dotenv import load_dotenv

try:
    from edream_sdk.client import create_edream_client
    from edream_sdk.types.playlist_types import CreatePlaylistRequest, PlaylistItemType
except ImportError:
    print("Error: edream_sdk not installed", file=sys.stderr)
    print("Install it with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

script_file = Path(__file__).resolve()
engines_dir = script_file.parent.parent

load_dotenv(engines_dir / ".env")
if not os.environ.get("API_KEY"):
    load_dotenv(engines_dir.parent / ".env")

def load_config(engines_dir: Path) -> Dict[str, Any]:
    config_file = engines_dir / "configs" / "ltx-i2v-config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"ltx-i2v-config.json not found at {config_file}")
    with open(config_file, 'r') as f:
        return json.load(f)

def get_images_from_playlist(client, playlist_uuid: str) -> List[Dict[str, str]]:
    images: List[Dict[str, str]] = []
    take = 50
    skip = 0

    while True:
        response = client.get_playlist_items(playlist_uuid, take=take, skip=skip)
        items = response.get("items", [])

        for item in items:
            if item.get("type") != "dream":
                continue
            dream = item.get("dreamItem") or {}

            image_url = None
            for field in ["original_video", "video", "thumbnail"]:
                url = dream.get(field)
                if isinstance(url, str) and url.startswith("http"):
                    image_url = url
                    break

            if not image_url:
                continue

            images.append({
                "uuid": dream.get("uuid", ""),
                "name": dream.get("name") or dream.get("uuid") or "dream",
                "url": image_url,
            })

        total_count = response.get("totalCount")
        skip += take

        if total_count is None or skip >= total_count:
            break

    if not images:
        raise ValueError(f"No image dreams found in playlist: {playlist_uuid}")

    return images

def create_job_identifier(source_id: str, combo_prompt: str) -> str:
    combo_hash = hashlib.md5(combo_prompt.encode()).hexdigest()[:8]
    return f"{source_id}:{combo_hash}"

def get_existing_dream_identifiers(playlist_uuid: str, client) -> Set[str]:
    existing_identifiers = set()
    try:
        playlist = client.get_playlist(playlist_uuid, auto_populate=True)
        items = playlist.get("items", [])
        for item in items:
            if item.get("type") == "dream" and item.get("dreamItem"):
                dream = item["dreamItem"]
                text_to_check = f"{dream.get('description', '')} {dream.get('name', '')}"
                if "BATCH_IDENTIFIER:" in text_to_check:
                    parts = text_to_check.split("BATCH_IDENTIFIER:")
                    if len(parts) > 1:
                        identifier = parts[1].split()[0] if parts[1].split() else ""
                        if identifier:
                            existing_identifiers.add(identifier)
    except Exception as e:
        print(f"Warning: Error getting existing dreams from playlist: {e}", file=sys.stderr)
    return existing_identifiers

def main():
    backend_url = os.environ.get("BACKEND_URL", "https://api.infinidream.ai/api/v1")
    api_key = os.environ.get("API_KEY")

    if not api_key:
        print("Error: API_KEY not found", file=sys.stderr)
        sys.exit(1)

    client = create_edream_client(backend_url, api_key)

    try:
        config = load_config(engines_dir)
    except Exception as e:
        print(f"Error loading ltx-i2v-config.json: {e}", file=sys.stderr)
        sys.exit(1)

    image_uuid = config.get("image_uuid")
    image_playlist_uuid = config.get("image_playlist_uuid")

    if image_uuid:
        try:
            dream = client.get_dream(image_uuid)
            url = dream.get("original_video") or dream.get("video") or dream.get("thumbnail")
            if not url:
                print(f"No URL found for dream {image_uuid}", file=sys.stderr)
                sys.exit(1)
            images = [{"uuid": image_uuid, "name": dream.get("name") or image_uuid, "url": url}]
            print(f"Using single image: {images[0]['name']}")
        except Exception as e:
            print(f"Error fetching dream {image_uuid}: {e}", file=sys.stderr)
            sys.exit(1)
    elif image_playlist_uuid:
        try:
            images = get_images_from_playlist(client, image_playlist_uuid)
            print(f"Found {len(images)} image(s)")
        except Exception as e:
            print(f"Error getting images: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Either 'image_uuid' or 'image_playlist_uuid' must be set in ltx-i2v-config.json", file=sys.stderr)
        sys.exit(1)

    combos = config.get("combos", []) or [""]
    total_jobs = len(images) * len(combos)

    playlist_uuid = config.get("playlist_uuid")
    existing_identifiers = set()

    if playlist_uuid:
        try:
            client.get_playlist(playlist_uuid)
            existing_identifiers = get_existing_dream_identifiers(playlist_uuid, client)
            print(f"Resuming playlist {playlist_uuid} ({len(existing_identifiers)} existing)")
        except Exception as e:
            print(f"Error accessing playlist: {e}")
            playlist_uuid = None

    if not playlist_uuid:
        playlist_config = config.get("playlist")
        if not playlist_config:
            print("Error: No playlist_uuid and no playlist config in ltx-i2v-config.json")
            sys.exit(1)

        playlist = client.create_playlist({
            "name": playlist_config.get("name", "LTX I2V Batch Output"),
            "description": playlist_config.get("description", ""),
            "nsfw": playlist_config.get("nsfw", False),
        })
        playlist_uuid = playlist['uuid']
        print(f"Created playlist: {playlist_uuid}")

    print(f"Starting {total_jobs} tasks...")

    active_dreams = []
    job_count = 0
    skipped_count = 0
    failed_count = 0

    for image_data in images:
        source_dream_uuid = image_data["url"]
        source_id = image_data.get("uuid") or image_data.get("name")

        for combo in combos:
            ident = create_job_identifier(source_id, combo)
            if ident not in existing_identifiers:
                break
        else:
            skipped_count += len(combos)
            continue

        if not source_dream_uuid:
            skipped_count += len(combos)
            continue

        for combo in combos:
            job_count += 1
            combo_idx = combos.index(combo) + 1
            identifier = create_job_identifier(source_id, combo)

            if identifier in existing_identifiers:
                skipped_count += 1
                continue

            main_prompt = config.get("prompt", "")
            combined_prompt = f"{main_prompt} {combo}".strip()

            print(f"[{job_count}/{total_jobs}] {image_data['name']} combo {combo_idx}")

            algo_params = {
                "infinidream_algorithm": "ltx-i2v",
                "prompt": combined_prompt,
                "source_dream_uuid": source_dream_uuid,
            }

            for param in ["duration", "seed", "negative_prompt", "lora", "lora_strength"]:
                if param in config:
                    algo_params[param] = config[param]

            try:
                new_dream = client.create_dream_from_prompt({
                    "name": f"{image_data['name']}_combo-{combo_idx}",
                    "description": f"Batch generation. BATCH_IDENTIFIER:{identifier}",
                    "prompt": json.dumps(algo_params)
                })

                print(f"  Started: {new_dream['uuid']}")

                try:
                    client.add_item_to_playlist(
                        playlist_uuid=playlist_uuid,
                        type=PlaylistItemType.DREAM,
                        item_uuid=new_dream['uuid']
                    )
                except Exception as e:
                    print(f"  Failed to add to playlist: {e}", file=sys.stderr)

                active_dreams.append(new_dream['uuid'])

            except Exception as e:
                print(f"  Failed: {e}")
                failed_count += 1

    print(f"Submitted {len(active_dreams)}, skipped {skipped_count}, failed {failed_count}")

    if not active_dreams:
        return

    print(f"Polling {len(active_dreams)} jobs...")
    pending = set(active_dreams)
    poll_interval = 10
    start_time = time.time()
    max_wait = 7200

    while pending and (time.time() - start_time) < max_wait:
        completed = set()
        for dream_uuid in pending:
            try:
                dream = client.get_dream(dream_uuid)
                status = dream.get("status")
                if status == "processed":
                    print(f"Done: {dream_uuid}")
                    completed.add(dream_uuid)
                elif status == "failed":
                    print(f"Failed: {dream_uuid} ({dream.get('error')})")
                    completed.add(dream_uuid)
            except Exception as e:
                print(f"Error checking {dream_uuid}: {e}")

        pending -= completed
        if pending:
            time.sleep(poll_interval)

    if pending:
        print(f"Timeout: {len(pending)} jobs still pending")
    else:
        print("All done")

    print(f"Playlist: {playlist_uuid}")

if __name__ == "__main__":
    main()
