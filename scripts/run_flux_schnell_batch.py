from __future__ import annotations

import sys
from typing import Any

from edream_batch import (
    bootstrap,
    download_image,
    get_or_create_playlist,
    poll_until_complete,
    resolve_output_dir,
    submit_dream,
)

ALGORITHM = "flux-schnell"
CONFIG_FILE = "flux-schnell-config.json"
PASS_THROUGH = ("size", "num_inference_steps")


def build_prompt(config: dict[str, Any], seed: int | None) -> dict[str, Any]:
    prompt: dict[str, Any] = {"infinidream_algorithm": ALGORITHM, "prompt": config["prompt"]}
    if seed is not None and seed != -1:
        prompt["seed"] = seed
    for key in PASS_THROUGH:
        if key in config:
            prompt[key] = config[key]
    return prompt


def main() -> None:
    client, config = bootstrap(CONFIG_FILE)

    if not config.get("prompt"):
        print(f"'prompt' is required in {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)

    count = max(1, int(config.get("num_generations", 1)))
    playlist_uuid = get_or_create_playlist(client, config, "FLUX Schnell Batch")
    output_dir = resolve_output_dir(config.get("output_folder", "generated-images"))
    base_name = config.get("output_filename", ALGORITHM)

    submitted: list[str] = []
    for idx in range(1, count + 1):
        seed = config.get("seed") if idx == 1 else None
        uuid = submit_dream(
            client,
            name=f"FLUX Schnell {idx}",
            description=f"Generated image {idx}",
            prompt=build_prompt(config, seed),
            playlist_uuid=playlist_uuid,
            ccby_license=config.get("ccbyLicense", True),
        )
        if uuid:
            print(f"[{idx}/{count}] Submitted: {uuid}")
            submitted.append(uuid)

    if not submitted:
        print("No jobs submitted.", file=sys.stderr)
        return

    order = {uuid: idx for idx, uuid in enumerate(submitted, 1)}

    def on_processed(dream: dict[str, Any]) -> None:
        idx = order.get(dream["uuid"], 0)
        suffix = f"_{idx:04d}" if count > 1 else ""
        download_image(client, dream, output_dir / f"{base_name}{suffix}.png")

    result = poll_until_complete(client, submitted, on_processed=on_processed, max_wait=3600)
    print(f"Done. processed={len(result.processed)} failed={len(result.failed)} timed_out={len(result.timed_out)}")
    print(f"Playlist: {playlist_uuid}")


if __name__ == "__main__":
    main()
