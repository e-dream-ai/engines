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
    Create a `.env` file in the `engines` directory (or use the one in the project root). `BACKEND_URL` and `API_KEY` are required. Deployment-specific UUIDs used as test inputs also live here; configs reference them with `${VAR}` (e.g. `"image_uuid": "${STILL_UUID}"`). You can copy `.env.example` and replace the API_KEY.
    ```
    BACKEND_URL=https://api.infinidream.ai/api/v1
    API_KEY=your_api_key_here
    STILL_UUID=an-image-dream-uuid          # source for i2i / i2v scripts
    DREAM_UUID=a-video-dream-uuid            # source for video scripts
    UPREZ_SOURCE_PLAYLIST_UUID=a-playlist-uuid
    ```

## Batch Processing Scripts

These scripts are located in `engines/scripts/` and use the `edream_sdk` to interact with the API directly.

### 1. Wan Image-to-Video Batch (`run_wan_i2v_batch.py`)

Generates videos from image dreams using the Wan I2V algorithm with various prompt combinations. Source images come from an `image_playlist_uuid` (typically the output playlist of `run_qwen_image_batch.py` or `run_z_image_turbo_batch.py`), or from a single `image_uuid`.

**Configuration (`engines/configs/job.json`):**

```json
{
    "image_playlist_uuid": "${STILL_PLAYLIST_UUID}",
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
    "image_uuid": "${STILL_UUID}",
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

### 5. Disco Diffusion Batch (`run_disco_batch.py`)

Generates images or animations using Disco Diffusion v5.2 (CLIP-guided diffusion with optional optical-flow warp).

**Configuration (`engines/configs/disco-config.json`):**

Single image:

```json
{
    "batch_name": "DiscoTest",
    "animation_mode": "None",
    "width": 512,
    "height": 512,
    "steps": 50,
    "skip_steps": 10,
    "clip_guidance_scale": 5000,
    "cutn_batches": 1,
    "clip_vit_b32": true,
    "seed": 1337,
    "text_prompts": {
        "0": ["A beautiful painting of a cosmic nebula, trending on artstation"]
    },
    "playlist": { "name": "Disco Output", "nsfw": false }
}
```

2D animation (dream zoom):

```json
{
    "batch_name": "DreamZoom",
    "animation_mode": "2D",
    "max_frames": 24,
    "fps": 6,
    "zoom": "0:(1.02)",
    "angle": "0:(0)",
    "frames_skip_steps": "70%",
    "steps": 50,
    "clip_guidance_scale": 3000,
    "cutn_batches": 1,
    "clip_vit_b32": true,
    "seed": 42,
    "text_prompts": {
        "0": ["A cosmic nebula, trending on artstation, by Greg Rutkowski"]
    },
    "playlist": { "name": "Disco Output", "nsfw": false }
}
```

Video Input (optical-flow stylization of a source video):

```json
{
    "batch_name": "VideoWarp",
    "animation_mode": "Video Input",
    "flow_warp": true,
    "flow_blend": 0.5,
    "check_consistency": true,
    "source_dream_uuid": "your-source-video-dream-uuid",
    "steps": 50,
    "clip_guidance_scale": 3000,
    "cutn_batches": 1,
    "clip_vit_b32": true,
    "text_prompts": {
        "0": ["A painting in the style of Van Gogh, trending on artstation"]
    },
    "playlist": { "name": "Disco Output", "nsfw": false }
}
```

**Animation modes:** `None` (single image), `2D` (zoom/rotate/translate), `3D` (depth-warped), `Video Input` (optical-flow warp)

**Usage:**

```bash
python3 scripts/run_disco_batch.py
```

---

### 6. Nvidia VSR Batch (`run_nvidia_vsr_batch.py`)

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

---

### 7. FLUX Schnell Batch (`run_flux_schnell_batch.py`)

Text-to-image generation with FLUX.1 [schnell] (fal). Downloads results locally.

**Configuration (`engines/configs/flux-schnell-config.json`):**

```json
{
    "prompt": "A vibrant sunset over ocean waves, photorealistic.",
    "num_generations": 2,
    "output_folder": "generated-images",
    "output_filename": "flux-schnell",
    "size": "1280*720",
    "num_inference_steps": 4,
    "seed": -1,
    "playlist": { "name": "FLUX Schnell Batch", "nsfw": false }
}
```

Valid `size` options: `1024*768`, `1024*1024`, `768*1024`, `1280*720`, `720*1280`

**Usage:**

```bash
python3 scripts/run_flux_schnell_batch.py
```

### 8. FLUX Kontext Image-to-Image Batch (`run_flux_kontext_i2i_batch.py`)

Re-imagines source images with an edit prompt using FLUX.1 Kontext (fal). Output
follows the source size, so there is no `size` parameter. Sources come from a
single `image_uuid` or an `image_playlist_uuid`.

**Configuration (`engines/configs/flux-kontext-i2i-config.json`):**

```json
{
    "image_uuid": "${STILL_UUID}",
    "prompt": "Turn it into a watercolor painting with soft pastel colors.",
    "seed": -1,
    "output_folder": "generated-images",
    "output_filename": "flux-kontext",
    "playlist": { "name": "FLUX Kontext I2I Batch", "nsfw": false }
}
```

**Usage:**

```bash
python3 scripts/run_flux_kontext_i2i_batch.py
```

### 9. Kling Image-to-Video Batch (`run_kling_i2v_batch.py`)

Animates source images with a prompt using Kling (fal). Set `model` to
`kling-i2v` (Kling 3.0 Pro) or `kling-25-i2v` (Kling 2.5 Turbo Pro). Video results
are auto-uploaded to their dream, so nothing is downloaded locally.

**Configuration (`engines/configs/kling-i2v-config.json`):**

```json
{
    "model": "kling-i2v",
    "image_uuid": "${STILL_UUID}",
    "prompt": "The scene comes alive with gentle, cinematic motion.",
    "duration": 5,
    "negative_prompt": "",
    "cfg_scale": 0.5,
    "playlist": { "name": "Kling I2V Batch", "nsfw": false }
}
```

Durations: `kling-i2v` allows 3–15s; `kling-25-i2v` allows 5s or 10s. Optionally
set `end_source_uuid` for an end frame.

**Usage:**

```bash
python3 scripts/run_kling_i2v_batch.py
```
