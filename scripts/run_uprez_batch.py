import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv

try:
    from edream_sdk.client import create_edream_client
    from edream_sdk.types.playlist_types import CreatePlaylistRequest, PlaylistItemType
    from edream_sdk.types.dream_types import UpdateDreamRequest
except ImportError:
    print("Error: edream_sdk not installed", file=sys.stderr)
    print("Install it with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

script_file = Path(__file__).resolve()
engines_dir = script_file.parent.parent
load_dotenv(engines_dir / ".env")
if not os.environ.get("API_KEY"):
     load_dotenv(engines_dir.parent / ".env")

def load_config(script_dir: Path) -> Dict[str, Any]:
    config_file = script_dir / "uprez-config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"uprez-config.json not found at {config_file}")
    
    with open(config_file, 'r') as f:
        return json.load(f)

def get_all_playlist_dreams(client, playlist_uuid: str) -> List[Dict[str, Any]]:
    all_dreams = []
    skip = 0
    take = 100
    
    while True:
        try:
            response = client.get_playlist_items(playlist_uuid, take=take, skip=skip)
            items = response.get("items", [])
            
            if not items:
                break
            
            for item in items:
                if item.get("type") == "dream" and item.get("dreamItem"):
                    dream = item["dreamItem"]
                    all_dreams.append({
                        "dream": dream,
                        "playlist_item_id": item.get("id"),
                    })
            
            total_count = response.get("totalCount", 0)
            if len(all_dreams) >= total_count or len(items) < take:
                break
            
            skip += take
        except Exception as e:
            print(f"Error fetching playlist items: {e}", file=sys.stderr)
            break
    
    return all_dreams

def is_dream_already_uprezed(client, original_dream_uuid: str, marker: str = "uprez") -> bool:
    try:
        dream = client.get_dream(original_dream_uuid)
        if not dream:
            return False
        description = dream.get("description", "") or ""
        return marker.lower() in description.lower()
    except Exception:
        return False

def update_dream_description(client, dream_uuid: str, marker: str = "uprez") -> bool:
    try:
        dream = client.get_dream(dream_uuid)
        if not dream:
            return False
        
        current_description = dream.get("description") or ""
        
        if marker.lower() in current_description.lower():
            return True
        
        if current_description:
            new_description = f"{current_description} {marker}"
        else:
            new_description = marker
        
        update_data: UpdateDreamRequest = {
            "description": new_description
        }
        
        client.update_dream(dream_uuid, update_data)
        return True
    except Exception as e:
        print(f"Error updating dream description: {e}", file=sys.stderr)
        return False

def main():
    print(f"Script directory: {script_file.parent}")
    
    backend_url = os.environ.get("BACKEND_URL", "https://api.infinidream.ai/api/v1")
    api_key = os.environ.get("API_KEY")
    
    if not api_key:
        print("Error: API_KEY not found", file=sys.stderr)
        sys.exit(1)
        
    client = create_edream_client(backend_url, api_key)
    print(f"Connected to {backend_url}")
    
    print("\nLoading uprez-config.json...")
    try:
        config = load_config(script_file.parent)
        print(f"Loaded uprez-config.json")
    except Exception as e:
        print(f"Error loading uprez-config.json: {e}", file=sys.stderr)
        sys.exit(1)
    
    playlist_uuid = config.get("playlist_uuid")
    if not playlist_uuid:
        print("'playlist_uuid' not found in uprez-config.json", file=sys.stderr)
        sys.exit(1)
    
    uprez_config = config.get("uprez_config", {})
    tracking_config = config.get("tracking", {})
    marker = tracking_config.get("marker", "uprez")
    existing_playlist_uuid = tracking_config.get("existing_playlist_uuid")
    
    output_playlist = None
    if existing_playlist_uuid:
        try:
            output_playlist = client.get_playlist(existing_playlist_uuid)
            print(f"Using output playlist: {output_playlist.get('name')}")
        except Exception:
            print("Could not access existing output playlist")
            
    if not output_playlist:
        output_playlist_config = config.get("output_playlist", {})
        if not output_playlist_config:
            output_playlist_config = {"name": "Uprez Output"}
             
        print(f"Creating new output playlist: {output_playlist_config.get('name')}")
        playlist_data: CreatePlaylistRequest = {
            "name": output_playlist_config.get("name", "Uprezed Playlist"),
            "description": output_playlist_config.get("description"),
            "nsfw": output_playlist_config.get("nsfw", False),
        }
        output_playlist = client.create_playlist(playlist_data)
        print(f"Created playlist: {output_playlist['uuid']}")
        
    output_playlist_uuid = output_playlist["uuid"]

    print(f"\nFetching dreams from source playlist {playlist_uuid}...")
    try:
        all_dreams = get_all_playlist_dreams(client, playlist_uuid)
        print(f"Found {len(all_dreams)} dream(s)")
    except Exception as e:
        print(f"Error fetching dreams: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"\nScanning for already processed dreams (marker: '{marker}')...")
    dreams_to_process = []
    
    for dream_data in all_dreams:
        dream = dream_data["dream"]
        if is_dream_already_uprezed(client, dream.get("uuid"), marker):
            pass
        else:
            dreams_to_process.append(dream_data)
            
    print(f"Dreams to process: {len(dreams_to_process)}")
    if not dreams_to_process:
        print("Nothing to do.")
        return

    active_jobs = []
    
    for idx, dream_data in enumerate(dreams_to_process, 1):
        dream = dream_data["dream"]
        dream_uuid = dream.get("uuid")
        dream_name = dream.get("name") or "Untitled"
        
        print(f"[{idx}/{len(dreams_to_process)}] Processing: {dream_name} ({dream_uuid})")
        
        algo_params = {
            "infinidream_algorithm": "uprez",
            "video_uuid": dream_uuid,
            "upscale_factor": uprez_config.get("upscale_factor", 2),
            "interpolation_factor": uprez_config.get("interpolation_factor", 2),
            "output_format": uprez_config.get("output_format", "mp4"),
            "tile_size": uprez_config.get("tile_size", 1024),
            "tile_padding": uprez_config.get("tile_padding", 10),
            "quality": uprez_config.get("quality", "high"),
        }
         
        try:
            new_dream = client.create_dream_from_prompt({
                "name": f"{dream_name} (Uprez)",
                "description": f"Uprez of {dream_uuid}",
                "prompt": json.dumps(algo_params)
            })
            
            print(f"  -> Uprez job started: {new_dream['uuid']}")
            
            try:
                client.add_item_to_playlist(
                    playlist_uuid=output_playlist_uuid,
                    type=PlaylistItemType.DREAM,
                    item_uuid=new_dream['uuid']
                )
            except Exception as e:
                print(f"  -> Failed to add to playlist: {e}")
            
            update_dream_description(client, dream_uuid, marker)
            
            active_jobs.append(new_dream['uuid'])
            
        except Exception as e:
            print(f"  -> Failed to start uprez: {e}")
            
    print(f"\nPolling {len(active_jobs)} active jobs...")
    pending = set(active_jobs)
    poll_interval = 10
    start_time = time.time()
    max_wait = 7200
    
    while pending and (time.time() - start_time) < max_wait:
        completed = set()
        for uuid in pending:
            try:
                d = client.get_dream(uuid)
                status = d.get("status")
                if status == "processed":
                    print(f"Job finished: {uuid}")
                    completed.add(uuid)
                elif status == "failed":
                    print(f"Job failed: {uuid}")
                    completed.add(uuid)
            except Exception:
                pass
        
        pending -= completed
        if pending:
             time.sleep(poll_interval)

    if pending:
        print("Timeout waiting for jobs.")
    else:
        print("All jobs finished.")

if __name__ == "__main__":
    main()

