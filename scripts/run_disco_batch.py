import argparse
import json
import os
import sys
import time
from pathlib import Path

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


def load_config(engines_dir: Path, config_name: str) -> dict:
    config_file = Path(config_name)
    if not config_file.is_absolute():
        config_file = engines_dir / "configs" / config_name
    if not config_file.exists():
        raise FileNotFoundError(f"config not found at {config_file}")
    with open(config_file) as f:
        return json.load(f)


def get_or_create_playlist(client, config: dict) -> str:
    playlist_cfg = config.get("playlist", {})
    name = playlist_cfg.get("name", "Disco Diffusion Output")
    nsfw = playlist_cfg.get("nsfw", False)
    playlist = client.create_playlist(CreatePlaylistRequest(name=name, nsfw=nsfw))
    return playlist["uuid"]


def main():
    parser = argparse.ArgumentParser(description="Run a Disco Diffusion batch.")
    parser.add_argument(
        "--style-transfer",
        action="store_true",
        help="Use disco-style-transfer-config.json instead of disco-config.json",
    )
    args = parser.parse_args()

    config_name = "disco-style-transfer-config.json" if args.style_transfer else "disco-config.json"

    backend_url = os.environ.get("BACKEND_URL", "https://api-stage.infinidream.ai/api/v1")
    api_key = os.environ.get("API_KEY")

    if not api_key:
        print("Error: API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    client = create_edream_client(backend_url, api_key)

    config = load_config(engines_dir, config_name)

    playlist_uuid = get_or_create_playlist(client, config)
    print(f"Playlist: {playlist_uuid}")

    prompts = config.get("text_prompts", {"0": ["A beautiful painting, trending on artstation"]})
    source_dream_uuid = config.get("source_dream_uuid")

    settings = {k: v for k, v in config.items() if k not in ("playlist", "source_dream_uuid")}
    settings["text_prompts"] = prompts

    algo_params = {
        "infinidream_algorithm": "discodiffusion",
        **settings,
    }
    if source_dream_uuid:
        algo_params["source_dream_uuid"] = source_dream_uuid

    batch_name = config.get("batch_name", "DiscoTest")
    first_prompt = prompts.get("0", [""])[0][:60]

    print(f"Submitting: {batch_name} — {first_prompt}")

    new_dream = client.create_dream_from_prompt({
        "name": batch_name,
        "prompt": json.dumps(algo_params),
        "ccbyLicense": config.get("ccbyLicense", True),
    })

    dream_uuid = new_dream["uuid"]
    print(f"Started: {dream_uuid}")

    try:
        client.add_item_to_playlist(
            playlist_uuid=playlist_uuid,
            type=PlaylistItemType.DREAM,
            item_uuid=dream_uuid,
        )
    except Exception as e:
        print(f"Warning: could not add to playlist: {e}", file=sys.stderr)

    print("Polling...")
    poll_interval = 15
    start_time = time.time()
    max_wait = 7200

    while (time.time() - start_time) < max_wait:
        try:
            dream = client.get_dream(dream_uuid)
            status = dream.get("status")
            elapsed = int(time.time() - start_time)
            print(f"  [{elapsed}s] {status}")
            if status == "processed":
                url = dream.get("video") or dream.get("original_video")
                print(f"Done: {url}")
                break
            elif status == "failed":
                print(f"Failed: {dream.get('error')}", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"  Error polling: {e}", file=sys.stderr)

        time.sleep(poll_interval)
    else:
        print("Timeout waiting for job", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
