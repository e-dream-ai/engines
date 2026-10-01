"""Render a style-preset playlist: one dream per style, same subject and seed.

Each style in the styles file (a JSON list of {"name", "prompt", "section"}) is
rendered with the configured text-to-image algorithm. ``style_template`` gives
the style's own text and ``prompt_template`` adds the example subject, so the
style is the only variable. Each dream is named for its style, and its prompt
JSON carries ``style_prompt`` (the style text alone, what "apply style"
inserts) and ``section`` (for search) next to the recipe. The example subject is
stored on the playlist as ``{"subject": ...}``.

With no playlist, every style is rendered into a new playlist. Given a playlist
(``--playlist`` or ``playlist_uuid`` in the config), it is brought up to date:

- styles new to the playlist are rendered and added;
- items whose recipe no longer matches (subject, prose, algorithm, size) are
  re-rendered, and the new dream takes the old one's place;
- names, ``style_prompt`` and ``section`` are synced in place (no re-render),
  descriptions are cleared, and items are put in styles-file order.

Curation done in the app is respected, using state kept in the playlist's
``prompt`` field: ``{"subject", "known", "exclude"}``. ``known`` lists the
styles the playlist held after the last run, so a known style that is now
missing was removed by hand and moves to ``exclude`` instead of being rendered
again; ``--include NAME`` brings one back, as does re-adding its dream by hand.
An item's seed is not part of its recipe check, so a dream re-rolled with
another seed is kept. A playlist without ``known`` (made before this script)
treats missing styles as new; pass ``--exclude-missing`` to mark them removed.

Items are never removed unless ``--prune`` is passed, which drops items whose
style is gone from the styles file. Dreams are never deleted.

Usage:
    python3 scripts/run_style_preset_playlist.py --env stage --dry-run
    python3 scripts/run_style_preset_playlist.py --env stage --sample 10
    python3 scripts/run_style_preset_playlist.py --env stage --playlist UUID
    python3 scripts/run_style_preset_playlist.py --env stage --playlist UUID --no-render
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "utils"))

from dotenv import load_dotenv

from edream_batch import ENGINES_DIR, bootstrap, poll_until_complete
from edream_sdk.types.playlist_types import PlaylistItemType

CONFIG_FILE = "style-preset-playlist-config.json"
_DUP_SUFFIX = re.compile(r"\s*\(\d+\)$")


@dataclass(frozen=True)
class Style:
    key: str  # unique name from the styles file, e.g. "Film Noir (2)"
    name: str  # display name, duplicate suffix stripped
    section: str
    prose: str


def load_styles(source: str) -> list[Style]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source) as response:
            raw = json.load(response)
    else:
        path = Path(source)
        raw = json.loads((path if path.is_absolute() else ENGINES_DIR / path).read_text())
    return [
        Style(s["name"], _DUP_SUFFIX.sub("", s["name"]), s.get("section", ""), s["prompt"].rstrip().rstrip("."))
        for s in raw
    ]


# Fields that change the rendered image; the rest of the recipe is metadata.
RENDER_FIELDS = ("infinidream_algorithm", "prompt", "size")


def build_recipe(config: dict[str, Any], style: Style, seed: Any = None) -> dict[str, Any]:
    style_prompt = config["style_template"].format(name=style.name, prose=style.prose)
    recipe: dict[str, Any] = {
        "infinidream_algorithm": config["algorithm"],
        "prompt": config["prompt_template"].format(style_prompt=style_prompt, subject=config["subject"]),
        "style_prompt": style_prompt,
        "section": style.section,
    }
    if config.get("size"):
        recipe["size"] = config["size"]
    seed = config.get("seed") if seed is None else seed
    if seed is not None:
        recipe["seed"] = seed
    return recipe


def is_current(recipe: dict[str, Any], config: dict[str, Any], style: Style) -> bool:
    """Whether the item's image still matches; the seed is ignored so re-rolls survive."""
    want = build_recipe(config, style)
    return all(recipe.get(f) == want.get(f) for f in RENDER_FIELDS)


def metadata_update(dream: dict[str, Any], config: dict[str, Any], style: Style) -> dict[str, Any] | None:
    """The update_dream body that syncs a current item's name, description and
    prompt metadata, or None if it is already in sync."""
    recipe = parse_recipe(dream)
    want = {**build_recipe(config, style, seed=recipe.get("seed")),
            **{k: v for k, v in recipe.items() if k not in RENDER_FIELDS + ("style_prompt", "section", "seed")}}
    update: dict[str, Any] = {}
    if dream.get("name") != style.name:
        update["name"] = style.name
    if dream.get("description"):
        update["description"] = ""
    if json.dumps(recipe) != json.dumps(want):
        update["prompt"] = json.dumps(want)
    return update or None


def parse_recipe(dream: dict[str, Any]) -> dict[str, Any]:
    """The JSON object in a dream's or playlist's ``prompt`` field, or {}."""
    prompt = dream.get("prompt")
    if isinstance(prompt, str):
        try:
            prompt = json.loads(prompt)
        except json.JSONDecodeError:
            return {}
    return prompt if isinstance(prompt, dict) else {}


def match_style(recipe: dict[str, Any], styles: list[Style]) -> Style | None:
    """Identify an item's style by its prose, which survives subject/seed changes,
    falling back to the name in the prompt when the styles file rewrote the prose."""
    text = recipe.get("prompt") or ""
    hits = [s for s in styles if s.prose and s.prose in text]
    if hits:
        return max(hits, key=lambda s: len(s.prose))
    named = [s for s in styles if text.startswith(f"Style: {s.name}:")]
    return min(named, key=lambda s: len(s.key)) if named else None


def fetch_items(client: Any, playlist_uuid: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    skip = 0
    while True:
        response = client.get_playlist_items(playlist_uuid, take=100, skip=skip)
        items += response.get("items", [])
        skip += 100
        if skip >= (response.get("totalCount") or 0):
            return items


def render(client: Any, config: dict[str, Any], styles: list[Style], batch_size: int) -> dict[str, str]:
    """Render styles in batches; return style key -> processed dream uuid."""
    done: dict[str, str] = {}
    for start in range(0, len(styles), batch_size):
        batch = styles[start:start + batch_size]
        submitted: dict[str, Style] = {}
        for style in batch:
            try:
                dream = client.create_dream_from_prompt({
                    "name": style.name,
                    "description": "",
                    "prompt": json.dumps(build_recipe(config, style)),
                    "ccbyLicense": config.get("ccbyLicense", True),
                })
            except Exception as e:
                print(f"  Failed to submit '{style.key}': {e}", file=sys.stderr)
                continue
            submitted[dream["uuid"]] = style
            print(f"Submitted {style.key}: {dream['uuid']}")

        result = poll_until_complete(client, list(submitted), poll_interval=5, max_wait=1800)
        for uuid in result.processed:
            done[submitted[uuid].key] = uuid
        for uuid in result.failed + result.timed_out:
            print(f"  Not added: {submitted[uuid].key} ({uuid})", file=sys.stderr)
        print(f"Rendered {len(done)} so far, {start + len(batch)}/{len(styles)} submitted")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=CONFIG_FILE, help="config file in configs/")
    parser.add_argument("--env", help="load engines/.env.<ENV> (e.g. stage, alpha) before .env")
    parser.add_argument("--playlist", help="existing playlist uuid to update (overrides config)")
    parser.add_argument("--styles", help="styles file path or URL (overrides config)")
    parser.add_argument("--sample", type=int, help="render only N random styles from those that need it")
    parser.add_argument("--rng-seed", type=int, help="seed for --sample")
    parser.add_argument("--include", action="append", default=[], metavar="NAME",
                        help="un-exclude a style so it is rendered again (repeatable)")
    parser.add_argument("--exclude-missing", action="store_true",
                        help="mark every wanted style missing from the playlist as removed by hand")
    parser.add_argument("--prune", action="store_true", help="remove items whose style is gone from the styles file")
    parser.add_argument("--no-render", action="store_true",
                        help="only sync metadata, names and order; submit no jobs")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    if args.env:
        env_file = ENGINES_DIR / f".env.{args.env}"
        if not env_file.exists():
            sys.exit(f"Error: {env_file} not found")
        load_dotenv(env_file)
    client, config = bootstrap(args.config)

    styles = load_styles(args.styles or config["styles"])
    keys = {s.key for s in styles}
    unknown = set(args.include) - keys
    if unknown:
        sys.exit(f"Error: --include names not in styles file: {sorted(unknown)}")

    playlist_uuid = args.playlist or config.get("playlist_uuid")
    playlist = client.get_playlist(playlist_uuid, auto_populate=False) if playlist_uuid else {}
    state = parse_recipe(playlist)
    items = fetch_items(client, playlist_uuid) if playlist_uuid else []

    current: dict[str, dict[str, Any]] = {}  # style key -> up-to-date item
    stale: dict[str, list[dict[str, Any]]] = {}  # style key -> items with an old recipe
    orphans: list[dict[str, Any]] = []
    for item in items:
        dream = item.get("dreamItem")
        style = match_style(parse_recipe(dream), styles) if item.get("type") == "dream" and dream else None
        if style is None:
            orphans.append(item)
        elif is_current(parse_recipe(dream), config, style) and style.key not in current:
            current[style.key] = item
        else:
            stale.setdefault(style.key, []).append(item)

    present = set(current) | set(stale)
    known = set(state.get("known") or present)
    excluded = set(state.get("exclude") or []) - present - set(args.include)
    removed = {k for k in keys - present - excluded - set(args.include) if k in known or args.exclude_missing}
    excluded |= removed
    wanted = [s for s in styles if s.key not in excluded]
    order = {s.key: i for i, s in enumerate(wanted)}

    todo = [] if args.no_render else [s for s in wanted if s.key not in current]
    if args.sample is not None:
        todo = random.Random(args.rng_seed).sample(todo, min(args.sample, len(todo)))
        todo.sort(key=lambda s: order[s.key])
    stale_count = sum(len(v) for v in stale.values())
    print(f"{len(styles)} styles, {len(excluded)} excluded ({len(removed)} newly removed by hand)")
    if not state.get("known") and items:
        print("Playlist has no 'known' state; missing styles count as new (see --exclude-missing)")
    for key in sorted(removed):
        print(f"  removed by hand: {key}")
    print(f"Playlist: {playlist_uuid or '(new)'} with {len(items)} items: "
          f"{len(current)} current, {stale_count} stale, {len(orphans)} not in styles file")
    print(f"To render: {len(todo)}" + (f" ({sum(s.key in stale for s in todo)} replacing stale)" if stale else ""))
    for item in orphans:
        label = (item.get("dreamItem") or item.get("playlistItem") or {}).get("name")
        print(f"  {'Will remove' if args.prune else 'Keeping'} unmatched item {item['id']}: {label}")

    by_key = {s.key: s for s in styles}
    patches = {item["dreamItem"]["uuid"]: u for key, item in current.items()
               if (u := metadata_update(item["dreamItem"], config, by_key[key]))}
    print(f"To update in place: {len(patches)} dreams")

    if args.dry_run:
        for s in todo:
            print(f"  render {s.key} [{s.section}]")
        return

    if not playlist_uuid:
        meta = config.get("playlist", {})
        playlist = client.create_playlist({
            "name": meta.get("name", "Style Presets"),
            "description": meta.get("description", ""),
            "nsfw": meta.get("nsfw", False),
        })
        playlist_uuid = playlist["uuid"]
        print(f"Created playlist: {playlist_uuid}")

    rendered = render(client, config, todo, args.batch_size)
    new = [{"type": PlaylistItemType.DREAM, "uuid": rendered[s.key]} for s in todo if s.key in rendered]
    for start in range(0, len(new), 100):
        client.add_items_to_playlist(playlist_uuid, new[start:start + 100])
    print(f"Added {len(new)} items")

    # A stale item goes only once its replacement has landed.
    removals = [i for key in rendered for i in stale.get(key, [])]
    if args.prune:
        removals += orphans
    for item in removals:
        client.delete_item_from_playlist(playlist_uuid, item["id"])
    print(f"Removed {len(removals)} items")

    failed = 0
    for uuid, update in patches.items():
        try:
            client.update_dream(uuid, update)
        except Exception as e:
            failed += 1
            print(f"  Failed to update {uuid}: {e}", file=sys.stderr)
    print(f"Updated {len(patches) - failed} dreams in place" + (f", {failed} failed" if failed else ""))

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        style = match_style(parse_recipe(item.get("dreamItem") or {}), styles)
        return (order.get(style.key, len(order)) if style else len(order), item["order"])

    final = fetch_items(client, playlist_uuid)
    ranked = sorted(final, key=rank)
    if [i["id"] for i in ranked] != [i["id"] for i in sorted(final, key=lambda i: i["order"])]:
        client.reorder_playlist(playlist_uuid, [{"id": i["id"], "order": n} for n, i in enumerate(ranked, 1)])
        print("Reordered playlist to styles-file order")

    final_keys = {style.key for i in final if (style := match_style(parse_recipe(i.get("dreamItem") or {}), styles))}
    client.update_playlist(playlist_uuid, {"name": playlist["name"], "prompt": {
        **state,
        "subject": config["subject"],
        "known": sorted(final_keys),
        "exclude": sorted(excluded),
    }})
    print(f"Done. {len(final)} items in playlist {playlist_uuid}, {len(excluded)} styles excluded")


if __name__ == "__main__":
    main()
