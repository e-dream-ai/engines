# Engines

This directory contains Python-based engines and batch processing scripts for the E-Dream GPU system.

## Setup

1.  **Install Dependencies**:
    Ensure you have the required packages installed, including the `edream_sdk`.
    ```bash
    cd engines
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file in the `engines` directory (or use the one in the project root) with the following credentials:
    ```
    BACKEND_URL=https://api.infinidream.ai/api/v1
    API_KEY=your_api_key_here
    ```

## Batch Processing Scripts

These scripts are located in `engines/scripts/` and use the `edream_sdk` to interact with the API directly.

### 1. Wan Image-to-Video Batch (`run_wan_i2v_batch.py`)

Generates videos from a directory of images using the Wan I2V algorithm with various prompt combinations.

**Configuration (`engines/scripts/job.json`):**
```json
{
  "image_path": "/absolute/path/to/images",
  "prompt": "A cinematic shot of...",
  "combos": ["in a cyberpunk city", "underwater"],
  "playlist_uuid": "optional-existing-playlist-uuid",
  "playlist": {
    "name": "My Batch Videos",
    "description": "Generated from batch script",
    "nsfw": false
  },
  "size": "1280x720",
  "duration": 5,
  "num_inference_steps": 30
}
```

**Usage:**
```bash
python3 scripts/run_wan_i2v_batch.py
```

### 2. Uprez Batch (`run_uprez_batch.py`)

Upscales video dreams from a source playlist and adds them to an output playlist. It tracks processed videos to avoid duplication.

**Configuration (`engines/scripts/uprez-config.json`):**
```json
{
  "playlist_uuid": "source-playlist-uuid",
  "tracking": {
    "marker": "uprez",
    "existing_playlist_uuid": "optional-output-playlist-uuid"
  },
  "output_playlist": {
    "name": "Uprezed Videos",
    "description": "Upscaled versions"
  },
  "uprez_config": {
    "upscale_factor": 2,
    "quality": "high"
  }
}
```

**Usage:**
```bash
python3 scripts/run_uprez_batch.py
```

### 3. Qwen Image Batch (`run_qwen_image_batch.py`)

Generates multiple images from a prompt and downloads them locally.

**Configuration (`engines/scripts/qwen-image-config.json`):**
```json
{
  "prompt": "A futuristic cityscape...",
  "num_generations": 5,
  "output_folder": "generated_images",
  "size": "1024x1024",
  "seed": -1
}
```

**Usage:**
```bash
python3 scripts/run_qwen_image_batch.py
```
