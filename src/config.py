import os
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent.parent
INPUT_DIR = ROOT_DIR / "input_notes"
KB_DIR = ROOT_DIR / "kb"
PAR_DIR = ROOT_DIR / "distilled_par"
STATE_FILE = ROOT_DIR / "state.json"

# Subdirectories for KB
KB_SUBDIRS = ["reference", "problems", "thinking", "inbox"]

# Valid Classification Values
VALID_TYPES = ["reference", "problems", "thinking", "inbox"]
VALID_CONTEXTS = ["personal", "work", "practice", "research", "debugging"]

# Processing Settings
MAX_CONTENT_CHARS = 4000  # Character limit for LLM context window optimization
CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.9

# LLM Settings
# Placeholder for API definitions. 
# Ideally, this would use environment variables or a secrets manager.
LLM_MODEL = "google/gemini-2.0-flash-exp:free" 
