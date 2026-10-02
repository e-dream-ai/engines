"""Copy a playlist of rendered dreams from one environment to another by re-rendering.

Each dream in the source playlist is re-submitted on the target with its prompt
JSON verbatim (algorithm, prompt, seed, size and any metadata such as
``style_prompt``), plus its name, description and license flags. With the same
model deployed on both sides, the same recipe and seed gives the same image.
The playlist's name, description, nsfw flag and ``prompt`` state are copied too,
so a playlist kept by another script (e.g. run_style_preset_playlist.py) can be
maintained by that script on the target afterwards.

Rerunnable: given ``--target``, only source items whose recipe is not already
in the target are rendered. Each batch is added to the target as soon as it has
rendered, so an interrupted run loses at most the batch in flight; rerun with
the same ``--target`` to finish. Items are then put in source order.

Items that are nested playlists, or dreams with no prompt JSON (uploads), cannot
be re-rendered; they are reported and skipped. Nothing is removed from the
target and nothing on the source is written.

Usage:
    python3 scripts/copy_playlist.py --from stage --to alpha --source UUID --dry-run
    python3 scripts/copy_playlist.py --from stage --to alpha --source UUID --limit 1
    python3 scripts/copy_playlist.py --from stage --to alpha --source UUID --target UUID
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "utils"))

from dotenv import dotenv_values

from edream_batch import ENGINES_DIR, poll_until_complete
from edream_sdk.client import create_edream_client
from edream_sdk.types.playlist_types import PlaylistItemType

from run_style_preset_playlist import fetch_items, parse_recipe


def connect(env: str) -> Any:
    env_file = ENGINES_DIR / f".env.{env}"
    if not env_file.exists():
        sys.exit(f"Error: {env_file} not found")
    values = dotenv_values(env_file)
    return create_edream_client(backend_url=values["BACKEND_URL"], api_key=values["API_KEY"])


def recipe_key(recipe: dict[str, Any]) -> str:
    return json.dumps(recipe, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source_env", required=True, help="source env, loads engines/.env.<ENV>")
    parser.add_argument("--to", dest="target_env", required=True, help="target env, loads engines/.env.<ENV>")
    parser.add_argument("--source", required=True, help="source playlist uuid")
    parser.add_argument("--target", help="existing target playlist uuid to fill in (default: create one)")
    parser.add_argument("--limit", type=int, help="render at most N missing items this run")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="report what would be rendered, write nothing")
    args = parser.parse_args()
    if args.source_env == args.target_env:
        sys.exit("Error: --from and --to are the same environment")

    src, dst = connect(args.source_env), connect(args.target_env)
    source = src.get_playlist(args.source, auto_populate=False)
    source_items = sorted(fetch_items(src, args.source), key=lambda i: i["order"])

    wanted: list[dict[str, Any]] = []  # source dreams, in source order
    for item in source_items:
        dream = item.get("dreamItem")
        if item.get("type") != "dream" or not dream:
            label = (item.get("playlistItem") or {}).get("name")
            print(f"  Skipping non-dream item {item['id']}: {label}", file=sys.stderr)
        elif not parse_recipe(dream):
            print(f"  Skipping dream with no prompt JSON: {dream.get('name')} ({dream['uuid']})", file=sys.stderr)
        else:
            wanted.append(dream)

    target = dst.get_playlist(args.target, auto_populate=False) if args.target else None
    have: dict[str, list[dict[str, Any]]] = {}  # recipe -> target items rendered from it
    for item in fetch_items(dst, args.target) if args.target else []:
        if item.get("type") == "dream" and item.get("dreamItem"):
            have.setdefault(recipe_key(parse_recipe(item["dreamItem"])), []).append(item)

    # Count duplicates so a recipe that appears twice in the source is rendered twice.
    claimed: dict[str, int] = {}
    todo: list[dict[str, Any]] = []
    for dream in wanted:
        key = recipe_key(parse_recipe(dream))
        claimed[key] = claimed.get(key, 0) + 1
        if claimed[key] > len(have.get(key, [])):
            todo.append(dream)
    if args.limit is not None:
        todo = todo[:args.limit]

    print(f"Source {args.source_env} {args.source} '{source['name']}': {len(source_items)} items, {len(wanted)} renderable")
    print(f"Target {args.target_env} {args.target or '(new)'}: {sum(map(len, have.values()))} items already copied")
    print(f"To render: {len(todo)}")
    if args.dry_run:
        for dream in todo:
            print(f"  render {dream['name']} (seed {parse_recipe(dream).get('seed')})")
        return

    if target is None:
        target = dst.create_playlist({
            "name": source["name"],
            "description": source.get("description") or "",
            "nsfw": bool(source.get("nsfw")),
        })
        print(f"Created playlist on {args.target_env}: {target['uuid']}")
    target_uuid = target["uuid"]

    added = 0
    for start in range(0, len(todo), args.batch_size):
        batch = todo[start:start + args.batch_size]
        submitted: dict[str, dict[str, Any]] = {}  # new uuid -> source dream
        for dream in batch:
            try:
                new = dst.create_dream_from_prompt({
                    "name": dream["name"],
                    "description": dream.get("description") or "",
                    "prompt": json.dumps(parse_recipe(dream)),
                    "ccbyLicense": bool(dream.get("ccbyLicense")),
                    "nsfw": bool(dream.get("nsfw")),
                })
            except Exception as e:
                print(f"  Failed to submit '{dream['name']}': {e}", file=sys.stderr)
                continue
            submitted[new["uuid"]] = dream
            print(f"Submitted {dream['name']}: {new['uuid']}")

        result = poll_until_complete(dst, list(submitted), poll_interval=5, max_wait=1800)
        for uuid in result.failed + result.timed_out:
            print(f"  Not added: {submitted[uuid]['name']} ({uuid})", file=sys.stderr)
        if result.processed:
            added += dst.add_items_to_playlist(
                target_uuid, [{"type": PlaylistItemType.DREAM, "uuid": u} for u in result.processed])
        print(f"Added {added} so far, {start + len(batch)}/{len(todo)} submitted")

    # Put target items in source order; anything not from the source goes last.
    rank = {}
    for n, dream in enumerate(wanted):
        rank.setdefault(recipe_key(parse_recipe(dream)), []).append(n)
    final = sorted(fetch_items(dst, target_uuid), key=lambda i: i["order"])
    used: dict[str, int] = {}

    def position(item: dict[str, Any]) -> int:
        key = recipe_key(parse_recipe(item.get("dreamItem") or {}))
        slots = rank.get(key, [])
        k = used.get(key, 0)
        used[key] = k + 1
        return slots[k] if k < len(slots) else len(wanted) + item["order"]

    ranked = [i for _, _, i in sorted((position(i), n, i) for n, i in enumerate(final))]
    if [i["id"] for i in ranked] != [i["id"] for i in final]:
        dst.reorder_playlist(target_uuid, [{"id": i["id"], "order": n} for n, i in enumerate(ranked, 1)])
        print("Reordered target to source order")

    update: dict[str, Any] = {"name": source["name"]}
    state = parse_recipe(source)
    if state:
        update["prompt"] = state
    dst.update_playlist(target_uuid, update)
    print(f"Done. {len(final)} items in {args.target_env} playlist {target_uuid}")


if __name__ == "__main__":
    main()
