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

Generates videos from a playlist of image dreams using the Wan I2V algorithm with various prompt combinations.

**Configuration (`engines/configs/job.json`):**
```json
{
  "image_playlist_uuid": "source-image-playlist-uuid",
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

**Configuration (`engines/configs/uprez-config.json`):**
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

**Configuration (`engines/configs/qwen-image-config.json`):**
```json
{
  "prompt": "A futuristic cityscape...",
  "num_generations": 5,
  "output_folder": "generated_images",
  "size": "1024x1024",
  "seed": -1
}
```
Example (use an existing playlist):
```json
{
  "prompt": "A futuristic cityscape...",
  "num_generations": 5,
  "output_folder": "generated_images",
  "size": "1024x1024",
  "seed": -1,
  "playlist_uuid": "existing-playlist-uuid"
}
```

Example (create a new playlist):
```json
{
  "prompt": "A futuristic cityscape...",
  "num_generations": 5,
  "output_folder": "generated_images",
  "size": "1024x1024",
  "seed": -1,
  "playlist": {
    "name": "Qwen Image Batch",
    "description": "Generated from qwen image batch script",
    "nsfw": false
  }
}
```

**Usage:**
```bash
python3 scripts/run_qwen_image_batch.py
```

### 4. LTX Image-to-Video Batch (`run_ltx_i2v_batch.py`)

Generates videos from a playlist of image dreams using LTX 2.3.

**Configuration (`engines/configs/ltx-i2v-config.json`):**

Single image:
```json
{
  "image_uuid": "your-dream-uuid",
  "prompt": "A cinematic shot of...",
  "duration": 5,
  "seed": -1,
  "playlist": { "name": "LTX I2V Output", "nsfw": false }
}
```

Batch from playlist:
```json
{
  "image_playlist_uuid": "source-image-playlist-uuid",
  "prompt": "A cinematic shot of...",
  "combos": ["in a cyberpunk city", "underwater"],
  "playlist_uuid": "optional-existing-playlist-uuid",
  "playlist": { "name": "LTX I2V Batch Output", "nsfw": false },
  "duration": 5,
  "seed": -1,
  "lora": "ltx-2-19b-lora-camera-control-static.safetensors",
  "lora_strength": 0.4
}
```

**Usage:**
```bash
python3 scripts/run_ltx_i2v_batch.py
```

### 5. Nvidia VSR Batch (`run_nvidia_vsr_batch.py`)

Upscales video dreams using Nvidia RTX Video Super Resolution. Tracks processed videos to avoid duplication.

**Configuration (`engines/configs/nvidia-vsr-config.json`):**

Single video:
```json
{
  "video_uuid": "your-dream-uuid",
  "output_playlist": { "name": "Nvidia VSR Output", "nsfw": false },
  "vsr_config": { "upscale_factor": 2, "quality": "ULTRA" },
  "tracking": { "marker": "nvidia-vsr" }
}
```

Batch from playlist:
```json
{
  "playlist_uuid": "source-playlist-uuid",
  "output_playlist": { "name": "Nvidia VSR Output", "nsfw": false },
  "vsr_config": { "upscale_factor": 2, "quality": "ULTRA" },
  "tracking": {
    "marker": "nvidia-vsr",
    "existing_playlist_uuid": "optional-output-playlist-uuid"
  }
}
```

Valid `quality` options: `LOW`, `MEDIUM`, `HIGH`, `ULTRA`

**Usage:**
```bash
python3 scripts/run_nvidia_vsr_batch.py
```

### 6. Z-Image Turbo Batch (`run_z_image_turbo_batch.py`)

Generates images using the Z-Image Turbo model. Supports text-to-image and image-to-image generation.

**Configuration (`engines/configs/z-image-turbo-config.json`):**
```json
{
  "prompt": "a beautiful landscape with mountains and a lake",
  "num_generations": 2,
  "output_folder": "generated-images",
  "output_filename": "z-image-turbo",
  "size": "1024*1024",
  "seed": -1,
  "output_format": "png",
  "enable_safety_checker": true,
  "playlist": {
    "name": "Z-Image Turbo Batch",
    "description": "Generated from z-image-turbo batch script",
    "nsfw": false
  }
}
```

For image-to-image, add `image` (URL) and optionally `strength` (0.0–1.0):
```json
{
  "prompt": "a futuristic version of this scene",
  "image": "https://example.com/input.jpg",
  "strength": 0.8,
  "output_format": "jpeg"
}
```

Valid `size` options: `512*512`, `768*768`, `1024*1024`, `1280*1280`, `1024*768`, `768*1024`, `1280*720`, `720*1280`

Valid `output_format` options: `png`, `jpeg`, `webp`

**Usage:**
```bash
python3 scripts/run_z_image_turbo_batch.py
```
