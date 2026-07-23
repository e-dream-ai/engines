# AGENTS.md — engines

## Overview

Python batch processing scripts for AI generative models. Orchestrates GPU workloads for image-to-video, upscaling, and image generation via the backend API.

## Stack

- **Language:** Python 3
- **Dependencies:** edream_sdk, requests, python-dotenv
- **Configuration:** JSON files

## Project Structure

```
scripts/
  edream_batch.py              # Shared batch plumbing for the fal scripts
  run_wan_i2v_batch.py         # Image-to-video batch (Wan algorithm)
  run_uprez_batch.py           # Video upscaling batch
  run_qwen_image_batch.py      # Image generation batch (Qwen)
  run_z_image_turbo_batch.py   # Fast image generation (Z-Image Turbo)
  run_flux_schnell_batch.py    # Text-to-image (FLUX.1 [schnell], fal)
  run_flux_kontext_i2i_batch.py # Image-to-image (FLUX.1 Kontext, fal)
  run_kling_i2v_batch.py       # Image-to-video (Kling 3.0 / 2.5 Turbo, fal)
  images/                      # Sample image assets
configs/
  job.json                     # Wan I2V config template
  uprez-config.json            # Uprez config
  qwen-image-config.json       # Qwen config
  z-image-turbo-config.json    # Z-Image Turbo config
  flux-schnell-config.json     # FLUX schnell config
  flux-kontext-i2i-config.json # FLUX Kontext i2i config
  kling-i2v-config.json        # Kling i2v config
src/edream-sdk/                # SDK submodule
```

## Commands

```bash
pip install -r requirements.txt
python3 scripts/run_wan_i2v_batch.py         # Image-to-video batch
python3 scripts/run_uprez_batch.py           # Video upscaling batch
python3 scripts/run_qwen_image_batch.py      # Qwen image batch
python3 scripts/run_z_image_turbo_batch.py   # Z-Image Turbo batch
python3 scripts/run_flux_schnell_batch.py    # FLUX schnell text-to-image (fal)
python3 scripts/run_flux_kontext_i2i_batch.py # FLUX Kontext image-to-image (fal)
python3 scripts/run_kling_i2v_batch.py       # Kling image-to-video (fal)
```

## Key Patterns

- JSON-driven configuration in `configs/`
- Supports playlist creation and management
- Tracking/deduplication using markers (e.g., "uprez" marker for processed videos)
- Uses edream_sdk for backend API interactions
- Environment variables for API credentials
