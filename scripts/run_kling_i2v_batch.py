from __future__ import annotations

import sys
from typing import Any

from edream_batch import (
    SourceImage,
    bootstrap,
    get_or_create_playlist,
    poll_until_complete,
    resolve_source_images,
    submit_dream,
)

CONFIG_FILE = "kling-i2v-config.json"
SUPPORTED_MODELS = ("kling-i2v", "kling-25-i2v")
PASS_THROUGH = ("duration", "negative_prompt", "cfg_scale", "seed")


def build_prompt(config: dict[str, Any], model: str, source: SourceImage) -> dict[str, Any]:
    prompt: dict[str, Any] = {
        "infinidream_algorithm": model,
        "prompt": config.get("prompt", ""),
        "source_dream_uuid": source.ref,
    }
    end_source = config.get("end_source_uuid")
    if end_source:
        prompt["end_source_uuid"] = end_source
    for key in PASS_THROUGH:
        if key in config:
            prompt[key] = config[key]
    return prompt


def main() -> None:
    client, config = bootstrap(CONFIG_FILE)

    model = config.get("model", "kling-i2v")
    if model not in SUPPORTED_MODELS:
        print(f"'model' must be one of {SUPPORTED_MODELS}, got '{model}'", file=sys.stderr)
        sys.exit(1)

    try:
        sources = resolve_source_images(client, config)
    except ValueError as e:
        print(f"Error resolving sources: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Resolved {len(sources)} source image(s) for {model}")

    playlist_uuid = get_or_create_playlist(client, config, "Kling I2V Batch")

    submitted: list[str] = []
    for source in sources:
        uuid = submit_dream(
            client,
            name=f"Kling {source.name}",
            description=f"Image-to-video from {source.name}",
            prompt=build_prompt(config, model, source),
            playlist_uuid=playlist_uuid,
            ccby_license=config.get("ccbyLicense", True),
        )
        if uuid:
            print(f"Submitted {source.name}: {uuid}")
            submitted.append(uuid)

    if not submitted:
        print("No jobs submitted.", file=sys.stderr)
        return

    result = poll_until_complete(client, submitted, max_wait=7200)
    print(f"Done. processed={len(result.processed)} failed={len(result.failed)} timed_out={len(result.timed_out)}")
    print(f"Playlist: {playlist_uuid}")


if __name__ == "__main__":
    main()
