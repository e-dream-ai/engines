import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
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
    config_file = engines_dir / "configs" / "z-image-turbo-config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"z-image-turbo-config.json not found at {config_file}")
    with open(config_file, 'r') as f:
        return json.load(f)


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
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    prompt = config.get("prompt")
    if not prompt:
        print("'prompt' not found in z-image-turbo-config.json", file=sys.stderr)
        sys.exit(1)

    num_generations = config.get("num_generations", 1)
    if num_generations < 1:
        print("'num_generations' must be at least 1", file=sys.stderr)
        sys.exit(1)

    output_folder = config.get("output_folder", "generated-images")
    output_dir = Path(output_folder) if os.path.isabs(output_folder) else engines_dir / output_folder
    output_dir.mkdir(parents=True, exist_ok=True)

    playlist_uuid = config.get("playlist_uuid")

    if playlist_uuid:
        try:
            client.get_playlist(playlist_uuid)
        except Exception:
            playlist_uuid = None

    if not playlist_uuid:
        playlist_config = config.get("playlist", {})
        playlist_data: CreatePlaylistRequest = {
            "name": playlist_config.get("name", "Z-Image Turbo Batch"),
            "description": playlist_config.get("description", f"Batch generated from: {prompt}"),
            "nsfw": playlist_config.get("nsfw", False),
        }
        playlist = client.create_playlist(playlist_data)
        playlist_uuid = playlist["uuid"]
        print(f"Created playlist: {playlist_uuid}")

    active_jobs = []

    for idx in range(1, num_generations + 1):
        seed = config.get("seed")
        if seed is None or seed == -1:
            seed = -1 if idx == 1 else None

        algo_params = {
            "infinidream_algorithm": "z-image-turbo",
            "prompt": prompt,
        }

        if seed is not None and seed != -1:
            algo_params["seed"] = seed

        for param in ["image", "size", "strength", "output_format", "enable_safety_checker"]:
            if param in config:
                algo_params[param] = config[param]

        try:
            dream = client.create_dream_from_prompt({
                "name": f"Z-Image Turbo {idx}",
                "description": f"Generated image {idx}",
                "prompt": json.dumps(algo_params)
            })
            print(f"[{idx}/{num_generations}] Started: {dream['uuid']}")
            try:
                client.add_item_to_playlist(
                    playlist_uuid=playlist_uuid,
                    type=PlaylistItemType.DREAM,
                    item_uuid=dream['uuid']
                )
            except Exception as e:
                print(f"Failed to add to playlist: {e}")
            active_jobs.append((dream['uuid'], idx))
        except Exception as e:
            print(f"[{idx}/{num_generations}] Failed to start: {e}")

    if not active_jobs:
        print("No jobs started.")
        return

    pending = list(active_jobs)
    downloaded_count = 0
    start_time = time.time()

    while pending and (time.time() - start_time) < 3600:
        remaining = []

        for uuid, idx in pending:
            try:
                dream = client.get_dream(uuid)
                status = dream.get("status")

                if status == "processed":
                    image_url = dream.get("thumbnail") or dream.get("video")

                    if image_url:
                        output_format = config.get("output_format", "png")
                        base_filename = config.get("output_filename", "z-image-turbo")
                        filename = f"{base_filename}_{idx:04d}.{output_format}" if num_generations > 1 else f"{base_filename}.{output_format}"
                        output_path = output_dir / filename

                        if client.download_file(image_url, str(output_path)):
                            print(f"Downloaded: {output_path}")
                            downloaded_count += 1
                        else:
                            print(f"Download failed: {uuid}")
                    else:
                        print(f"No image URL for: {uuid}")

                elif status == "failed":
                    print(f"Job failed: {uuid}")
                else:
                    remaining.append((uuid, idx))

            except Exception as e:
                print(f"Error checking {uuid}: {e}")
                remaining.append((uuid, idx))

        pending = remaining
        if pending:
            time.sleep(10)

    if pending:
        print(f"Timeout: {len(pending)} jobs did not complete.")

    print(f"Done. Downloaded {downloaded_count}/{len(active_jobs)} images.")
    print(f"Playlist: {playlist_uuid}")


if __name__ == "__main__":
    main()
