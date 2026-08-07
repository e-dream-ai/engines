from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "utils"))

from edream_batch import (
    SourceImage,
    bootstrap,
    get_or_create_playlist,
    poll_until_complete,
    resolve_source_images,
    submit_dream,
)

CONFIG_FILE = "job.json"
PASS_THROUGH = (
    "size",
    "duration",
    "num_inference_steps",
    "guidance",
    "seed",
    "negative_prompt",
    "flow_shift",
    "enable_prompt_optimization",
    "enable_safety_checker",
)


def job_identifier(source: SourceImage, combo: str) -> str:
    return f"{source.ref}:{hashlib.md5(combo.encode()).hexdigest()[:8]}"


def existing_identifiers(client, playlist_uuid: str) -> set[str]:
    """Identifiers of dreams already submitted into the output playlist."""
    found: set[str] = set()
    try:
        playlist = client.get_playlist(playlist_uuid, auto_populate=True)
    except Exception as e:
        print(f"Warning: cannot read existing playlist items: {e}", file=sys.stderr)
        return found

    for item in playlist.get("items", []):
        dream = item.get("dreamItem") if item.get("type") == "dream" else None
        if not dream:
            continue
        text = f"{dream.get('description', '')} {dream.get('name', '')}"
        _, marker, rest = text.partition("BATCH_IDENTIFIER:")
        if marker and rest.split():
            found.add(rest.split()[0])
    return found


def build_prompt(config: dict[str, Any], source: SourceImage, combo: str) -> dict[str, Any]:
    prompt: dict[str, Any] = {
        "infinidream_algorithm": "wan-i2v",
        "prompt": f"{config.get('prompt', '')} {combo}".strip(),
        "image": source.ref,
    }
    for key in PASS_THROUGH:
        if key in config:
            prompt[key] = config[key]
    return prompt


def main() -> None:
    client, config = bootstrap(CONFIG_FILE)

    try:
        sources = resolve_source_images(client, config)
    except ValueError as e:
        print(f"Error resolving sources: {e}", file=sys.stderr)
        sys.exit(1)

    combos = config.get("combos") or [""]
    print(f"Resolved {len(sources)} source image(s) x {len(combos)} combo(s)")

    playlist_uuid = get_or_create_playlist(client, config, "Wan I2V Batch")
    already_done = existing_identifiers(client, playlist_uuid)
    if already_done:
        print(f"Resuming playlist {playlist_uuid} ({len(already_done)} existing)")

    submitted: list[str] = []
    skipped = 0

    for source in sources:
        for combo_idx, combo in enumerate(combos, 1):
            identifier = job_identifier(source, combo)
            if identifier in already_done:
                skipped += 1
                continue

            uuid = submit_dream(
                client,
                name=f"{source.name}_combo-{combo_idx}",
                description=f"Batch generation. BATCH_IDENTIFIER:{identifier}",
                prompt=build_prompt(config, source, combo),
                playlist_uuid=playlist_uuid,
                ccby_license=config.get("ccbyLicense", True),
            )
            if uuid:
                print(f"Submitted {source.name} combo {combo_idx}: {uuid}")
                submitted.append(uuid)

    print(f"Submitted {len(submitted)}, skipped {skipped}")
    if not submitted:
        return

    result = poll_until_complete(client, submitted, max_wait=7200)
    print(f"Done. processed={len(result.processed)} failed={len(result.failed)} timed_out={len(result.timed_out)}")
    print(f"Playlist: {playlist_uuid}")


if __name__ == "__main__":
    main()
