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
  run_wan_i2v_batch.py         # Image-to-video batch (Wan algorithm)
  run_uprez_batch.py           # Video upscaling batch
  run_qwen_image_batch.py      # Image generation batch (Qwen)
  run_z_image_turbo_batch.py   # Fast image generation (Z-Image Turbo)
  images/                      # Sample image assets
configs/
  job.json                     # Wan I2V config template
  uprez-config.json            # Uprez config
  qwen-image-config.json       # Qwen config
  z-image-turbo-config.json    # Z-Image Turbo config
src/edream-sdk/                # SDK submodule
```

## Commands

```bash
pip install -r requirements.txt
python3 scripts/run_wan_i2v_batch.py         # Image-to-video batch
python3 scripts/run_uprez_batch.py           # Video upscaling batch
python3 scripts/run_qwen_image_batch.py      # Qwen image batch
python3 scripts/run_z_image_turbo_batch.py   # Z-Image Turbo batch
```

## Key Patterns

- JSON-driven configuration in `configs/`
- Supports playlist creation and management
- Tracking/deduplication using markers (e.g., "uprez" marker for processed videos)
- Uses edream_sdk for backend API interactions
- Environment variables for API credentials
