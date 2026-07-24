from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "utils"))

from edream_batch import (
    SourceImage,
    bootstrap,
    download_image,
    get_or_create_playlist,
    poll_until_complete,
    resolve_output_dir,
    resolve_source_images,
    submit_dream,
)

ALGORITHM = "flux-kontext-i2i"
CONFIG_FILE = "flux-kontext-i2i-config.json"


def build_prompt(config: dict[str, Any], source: SourceImage) -> dict[str, Any]:
    prompt: dict[str, Any] = {
        "infinidream_algorithm": ALGORITHM,
        "prompt": config["prompt"],
        "source_dream_uuid": source.ref,
    }
    seed = config.get("seed")
    if seed is not None and seed != -1:
        prompt["seed"] = seed
    return prompt


def main() -> None:
    client, config = bootstrap(CONFIG_FILE)

    if not config.get("prompt"):
        print(f"'prompt' is required in {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)

    try:
        sources = resolve_source_images(client, config)
    except ValueError as e:
        print(f"Error resolving sources: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Resolved {len(sources)} source image(s)")

    playlist_uuid = get_or_create_playlist(client, config, "FLUX Kontext I2I Batch")
    output_dir = resolve_output_dir(config.get("output_folder", "generated-images"))
    base_name = config.get("output_filename", ALGORITHM)

    submitted: list[str] = []
    for source in sources:
        uuid = submit_dream(
            client,
            name=f"Kontext {source.name}",
            description=f"Image-to-image from {source.name}",
            prompt=build_prompt(config, source),
            playlist_uuid=playlist_uuid,
            ccby_license=config.get("ccbyLicense", True),
        )
        if uuid:
            print(f"Submitted {source.name}: {uuid}")
            submitted.append(uuid)

    if not submitted:
        print("No jobs submitted.", file=sys.stderr)
        return

    order = {uuid: idx for idx, uuid in enumerate(submitted, 1)}

    def on_processed(dream: dict[str, Any]) -> None:
        idx = order.get(dream["uuid"], 0)
        suffix = f"_{idx:04d}" if len(submitted) > 1 else ""
        download_image(client, dream, output_dir / f"{base_name}{suffix}.png")

    result = poll_until_complete(client, submitted, on_processed=on_processed, max_wait=3600)
    print(f"Done. processed={len(result.processed)} failed={len(result.failed)} timed_out={len(result.timed_out)}")
    print(f"Playlist: {playlist_uuid}")


if __name__ == "__main__":
    main()
