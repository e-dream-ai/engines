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
    from edream_sdk.types.file_upload_types import FileType
    from edream_sdk.types.dream_types import DreamMediaType
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

def load_job_config(script_dir: Path) -> Dict[str, Any]:
    """Load job.json from scripts directory."""
    job_file = script_dir / "job.json"
    if not job_file.exists():
        raise FileNotFoundError(f"job.json not found at {job_file}")
    
    with open(job_file, 'r') as f:
        return json.load(f)

def get_images_from_path(image_path: str, base_dir: Path) -> List[Path]:
    """Get all image files from the image_path directory."""
    if os.path.isabs(image_path):
        image_dir = Path(image_path)
    else:
        image_dir = base_dir / image_path
    
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")
    
    if not image_dir.is_dir():
        raise ValueError(f"image_path must be a directory: {image_dir}")
    
    image_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
    images = [
        img for img in image_dir.iterdir()
        if img.is_file() and img.suffix.lower() in image_extensions
    ]
    
    if not images:
        raise ValueError(f"No image files found in {image_dir}")
    
    return sorted(images)

def create_job_identifier(image_path: Path, combo_prompt: str) -> str:
    """Create a unique identifier for an image+combo combination."""
    image_name = image_path.name
    combo_hash = hashlib.md5(combo_prompt.encode()).hexdigest()[:8]
    return f"{image_name}:{combo_hash}"

def get_existing_dream_identifiers(playlist_uuid: str, client) -> Set[str]:
    """Get set of existing dream identifiers from a playlist."""
    existing_identifiers = set()
    
    try:
        playlist = client.get_playlist(playlist_uuid, auto_populate=True)
        items = playlist.get("items", [])
        
        for item in items:
            if item.get("type") == "dream" and item.get("dreamItem"):
                dream = item["dreamItem"]
                description = dream.get("description", "")
                name = dream.get("name", "")
                
                text_to_check = f"{description} {name}"
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
    print(f"Script directory: {script_file.parent}")
    
    backend_url = os.environ.get("BACKEND_URL", "https://api.infinidream.ai/api/v1")
    api_key = os.environ.get("API_KEY")
    
    if not api_key:
        print("Error: API_KEY not found in environment variables or .env file", file=sys.stderr)
        sys.exit(1)
        
    client = create_edream_client(backend_url, api_key)
    print(f"Connected to {backend_url}")

    print("\nLoading job.json...")
    try:
        job_config = load_job_config(script_file.parent)
        print(f"Loaded job.json")
    except Exception as e:
        print(f"Error loading job.json: {e}", file=sys.stderr)
        sys.exit(1)
    
    image_path_str = job_config.get("image_path")
    if not image_path_str:
        print("'image_path' not found in job.json", file=sys.stderr)
        sys.exit(1)
    
    print(f"\nScanning images from: {image_path_str}")
    try:
        images = get_images_from_path(image_path_str, script_file.parent)
        print(f"Found {len(images)} image(s)")
    except Exception as e:
        print(f"Error getting images: {e}", file=sys.stderr)
        sys.exit(1)

    combos = job_config.get("combos", [])
    if not combos:
        print("\nNo 'combos' found in job.json, using empty combo")
        combos = [""]
    
    total_jobs = len(images) * len(combos)
    
    playlist_uuid = job_config.get("playlist_uuid")
    playlist = None
    existing_identifiers = set()

    if playlist_uuid:
        print(f"\nChecking existing playlist: {playlist_uuid}")
        try:
            playlist = client.get_playlist(playlist_uuid)
            print(f"Found playlist: {playlist.get('name', 'Unnamed')}")
            existing_identifiers = get_existing_dream_identifiers(playlist_uuid, client)
            print(f"Found {len(existing_identifiers)} existing dream(s) in playlist")
        except Exception as e:
            print(f"Error accessing playlist: {e}")
            playlist_uuid = None
    
    if not playlist_uuid:
        playlist_config = job_config.get("playlist")
        if not playlist_config:
            print("Error: No playlist_uuid and no playlist config in job.json")
            sys.exit(1)
            
        print(f"\nCreating new playlist: {playlist_config.get('name')}")
        playlist_data: CreatePlaylistRequest = {
            "name": playlist_config.get("name", "Batch Output"),
            "description": playlist_config.get("description", ""),
            "nsfw": playlist_config.get("nsfw", False)
        }
        playlist = client.create_playlist(playlist_data)
        playlist_uuid = playlist['uuid']
        print(f"Created playlist: {playlist_uuid}")

    uploaded_image_map = {}

    print(f"\nStarting batch processing ({total_jobs} total tasks)...")
    
    active_dreams = []

    job_count = 0
    skipped_count = 0
    failed_count = 0
    
    for image_idx, image_path in enumerate(images, 1):
        source_dream_uuid = uploaded_image_map.get(str(image_path))
        
        needs_upload = False
        for combo in combos:
            ident = create_job_identifier(image_path, combo)
            if ident not in existing_identifiers:
                needs_upload = True
                break
        
        if not needs_upload:
            print(f"Skipping image {image_path.name} (all combos exist)")
            skipped_count += len(combos)
            continue

        if not source_dream_uuid:
            print(f"\nUploading {image_path.name}...")
            try:
                upload_options = {"mediaType": DreamMediaType.IMAGE}
                uploaded_dream = client.upload_file(
                    str(image_path), 
                    type=FileType.DREAM,
                    options=upload_options
                )
                dream_uuid = uploaded_dream['uuid']
                print(f"  Uploaded as dream: {dream_uuid}")
                
                image_url = None
                max_retries = 10
                
                for attempt in range(max_retries):
                    try:
                        fetched_dream = client.get_dream(dream_uuid)
                        
                        for field in ['original_video', 'video', 'thumbnail']:
                            url = fetched_dream.get(field)
                            if url and isinstance(url, str) and url.startswith('http'):
                                image_url = url
                                print(f"  Got presigned URL from '{field}'")
                                break
                        
                        if image_url:
                            break
                            
                        if attempt < max_retries - 1:
                            time.sleep(0.5)
                            
                    except Exception as e:
                        print(f"  Retry {attempt + 1}/{max_retries}: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(0.5)
                
                if image_url:
                    source_dream_uuid = image_url
                else:
                    print(f"  Warning: No presigned URL after {max_retries} attempts. Using UUID (may fail).")
                    source_dream_uuid = dream_uuid
                
                uploaded_image_map[str(image_path)] = source_dream_uuid
            except Exception as e:
                print(f"  Failed to upload image: {e}")
                failed_count += len(combos)
                continue

        for combo in combos:
            job_count += 1
            combo_idx = combos.index(combo) + 1
            identifier = create_job_identifier(image_path, combo)
            
            if identifier in existing_identifiers:
                print(f"[{job_count}/{total_jobs}] Skipping existing: {identifier}")
                skipped_count += 1
                continue
                
            main_prompt = job_config.get("prompt", "")
            combined_prompt = f"{main_prompt} {combo}".strip()
            
            print(f"[{job_count}/{total_jobs}] creating dream for {image_path.name} + combo {combo_idx}")
            
            algo_params = {
                "infinidream_algorithm": "wan-i2v",
                "prompt": combined_prompt,
                "image": source_dream_uuid,
            }
            
            for param in ["size", "duration", "num_inference_steps", "guidance", "seed",
                          "negative_prompt", "flow_shift", "enable_prompt_optimization", "enable_safety_checker"]:
                if param in job_config:
                    algo_params[param] = job_config[param]

            try:
                dream_name = f"{image_path.stem}_combo-{combo_idx}"
                desc_identifier = f"BATCH_IDENTIFIER:{identifier}"
                
                new_dream = client.create_dream_from_prompt({
                    "name": dream_name,
                    "description": f"Batch generation. {desc_identifier}",
                    "prompt": json.dumps(algo_params)
                })
                
                print(f"  -> Job started: {new_dream['uuid']}")
                
                client.add_item_to_playlist(
                    playlist_uuid=playlist_uuid,
                    type=PlaylistItemType.DREAM,
                    item_uuid=new_dream['uuid']
                )
                
                active_dreams.append(new_dream['uuid'])
                
            except Exception as e:
                print(f"  -> Failed to start job: {e}")
                failed_count += 1

    print("\n" + "="*60)
    print("Submission Complete")
    print(f"Active jobs: {len(active_dreams)}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed to start: {failed_count}")
    print("="*60)
    
    if not active_dreams:
        return

    print(f"\nPolling {len(active_dreams)} active jobs...")
    pending = set(active_dreams)
    
    poll_interval = 10
    start_time = time.time()
    max_wait = 7200 # 2 hours
    
    while pending and (time.time() - start_time) < max_wait:
        completed = set()
        
        for dream_uuid in pending:
            try:
                dream = client.get_dream(dream_uuid)
                status = dream.get("status")
                
                if status == "processed":
                    print(f"Job finished: {dream_uuid}")
                    completed.add(dream_uuid)
                elif status == "failed":
                    print(f"Job failed: {dream_uuid} (Error: {dream.get('error')})")
                    completed.add(dream_uuid)
                    
            except Exception as e:
                print(f"Error checking status for {dream_uuid}: {e}")
        
        pending -= completed
        
        if pending:
             time.sleep(poll_interval)
             
    if pending:
        print(f"\nTimeout waiting for {len(pending)} jobs.")
    else:
        print("\nAll jobs accounted for.")
        
    print(f"\nBatch process finished. Playlist: {playlist_uuid}")

if __name__ == "__main__":
    main()
