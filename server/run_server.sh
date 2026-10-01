#!/bin/sh
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 -m uvicorn app:app --host 0.0.0.0 --port 8765
