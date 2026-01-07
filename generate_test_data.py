import os
from pathlib import Path

INPUT_DIR = Path("c:/Project/onenote-exporter/input_notes")
INPUT_DIR.mkdir(parents=True, exist_ok=True)

notes = {
    "test_debug_01.md": """
# Server Crash Investigation
I was debugging a null pointer exception in the login handler.
The error seems to be caused by an uninitialized session object.
I need to fix this by adding a check.
    """,
    "test_ref_01.md": """
# API Documentation Guide
This is a reference for the new REST API.
Endpoints include /login, /logout, and /profile.
Make sure to include the Bearer token in the header.
    """,
    "test_thought_01.md": """
# Reflections on Architecture
I've been thinking about the trade-offs between microservices and monolith.
Complexity is high, but scalability is better.
    """,
    "test_inbox_01.md": """
# Random scrap
Just a random note about groceries or something.
    """
}

def create_dummy_notes():
    print(f"Creating {len(notes)} dummy notes in {INPUT_DIR}...")
    for filename, content in notes.items():
        path = INPUT_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content.strip())
    print("Dummy notes created.")

if __name__ == "__main__":
    create_dummy_notes()
