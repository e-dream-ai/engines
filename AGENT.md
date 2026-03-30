# AGENT.md — engines

## Overview
Batch processing scripts for bulk dream generation. Orchestrates large-scale image and video creation jobs.

## Stack
- **Language:** Python
- **Dependencies:** edream_sdk, requests, python-dotenv

## Project Structure
```
scripts/
  run_wan_i2v_batch.py       # Image-to-video batch processing
  run_uprez_batch.py         # Video upscaling batch
  run_qwen_image_batch.py    # Image generation batch
```

## Commands
```bash
pip install -r requirements.txt
python3 scripts/run_wan_i2v_batch.py     # I2V batch
python3 scripts/run_uprez_batch.py       # Upscaling batch
python3 scripts/run_qwen_image_batch.py  # Image gen batch
```

## Key Patterns
- Uses edream_sdk to communicate with the backend API
- Each script handles a specific algorithm's batch workflow
- Reads configuration from environment variables (.env)
