import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
import requests

try:
    from edream_sdk.client import create_edream_client
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
    """Load qwen-image-config.json from scripts directory."""
    config_file = script_dir / "qwen-image-config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"qwen-image-config.json not found at {config_file}")
    
    with open(config_file, 'r') as f:
        return json.load(f)

def download_image(url: str, output_path: Path) -> bool:
    """Download an image from a URL to a local file."""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True
    except Exception as e:
        print(f"Error downloading image from {url}: {e}", file=sys.stderr)
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
    
    print("\nLoading qwen-image-config.json...")
    try:
        config = load_config(script_file.parent)
        print(f"Loaded qwen-image-config.json")
    except Exception as e:
        print(f"Error loading qwen-image-config.json: {e}", file=sys.stderr)
        sys.exit(1)
    
    prompt = config.get("prompt")
    if not prompt:
        print("'prompt' not found in qwen-image-config.json", file=sys.stderr)
        sys.exit(1)
    
    num_generations = config.get("num_generations", 1)
    if num_generations < 1:
        print("'num_generations' must be at least 1", file=sys.stderr)
        sys.exit(1)
        
    output_folder = config.get("output_folder", "generated-images")
    
    if os.path.isabs(output_folder):
        output_dir = Path(output_folder)
    else:
        output_dir = engines_dir / output_folder
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")
    print(f"\nPrompt: {prompt}")
    print(f"Number of generations: {num_generations}")
    
    active_jobs = []
    
    for idx in range(1, num_generations + 1):
        seed = config.get("seed")
        if seed is None or seed == -1:
            seed = -1 if idx == 1 else None
            
        print(f"[{idx}/{num_generations}] Submitting job...")
        
        algo_params = {
            "infinidream_algorithm": "qwen-image",
            "prompt": prompt,
        }
        
        if seed is not None and seed != -1:
            algo_params["seed"] = seed
            
        for param in ["size", "negative_prompt", "enable_safety_checker"]:
            if param in config:
                algo_params[param] = config[param]

        try:
            dream = client.create_dream_from_prompt({
                "name": f"Qwen Image {idx}",
                "description": f"Generated image {idx}",
                "prompt": json.dumps(algo_params)
            })
            print(f"  -> Job started: {dream['uuid']}")
            active_jobs.append((dream['uuid'], idx))
        except Exception as e:
            print(f"  -> Failed to start job: {e}")

    if not active_jobs:
        print("No jobs started.")
        return

    print(f"\nWaiting for {len(active_jobs)} jobs to complete...")
    
    pending = list(active_jobs)
    downloaded_count = 0
    poll_interval = 10
    start_time = time.time()
    max_wait = 3600
    
    while pending and (time.time() - start_time) < max_wait:
        remaining = []
        
        for uuid, idx in pending:
            try:
                dream = client.get_dream(uuid)
                status = dream.get("status")
                
                if status == "processed":
                    print(f"Job finished: {uuid} (Gen {idx})")
                    
                    image_url = dream.get("thumbnail")
                    
                    if not image_url:
                        image_url = dream.get("video")

                    if image_url:
                        base_filename = config.get("output_filename", "qwen-image")
                        if num_generations > 1:
                            filename = f"{base_filename}_{idx:04d}.png"
                        else:
                            filename = f"{base_filename}.png"
                        
                        output_path = output_dir / filename
                        
                        print(f"  Downloading to {output_path}...")
                        if download_image(image_url, output_path):
                            print("  Success!")
                            downloaded_count += 1
                        else:
                             print("  Download failed.")
                    else:
                        print("  Warning: No image URL found in dream object.")
                        
                elif status == "failed":
                    print(f"Job failed: {uuid}")
                else:
                    remaining.append((uuid, idx))
                    
            except Exception as e:
                print(f"Error checking status for {uuid}: {e}")
                remaining.append((uuid, idx))
        
        pending = remaining
        if pending:
            time.sleep(poll_interval)
            
    if pending:
        print(f"Timeout waiting for {len(pending)} jobs.")
        
    print(f"\nCompleted. Downloaded {downloaded_count} images.")

if __name__ == "__main__":
    main()

