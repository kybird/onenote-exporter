
import json
import os

STATE_FILE = "state.json"

if not os.path.exists(STATE_FILE):
    print(f"{STATE_FILE} not found.")
    exit(0)

print(f"Reading {STATE_FILE}...")
with open(STATE_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Re-saving {STATE_FILE} with ensure_ascii=False...")
with open(STATE_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Done! Check the file.")
