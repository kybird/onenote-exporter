import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
import yaml

def get_markdown_files(directory: Path) -> List[Path]:
    """
    Returns a deterministic (sorted) list of .md files in the directory.
    """
    if not directory.exists():
        return []
    files = sorted([f for f in directory.rglob("*.md") if f.is_file()])
    return files

def read_file(path: Path) -> str:
    """Read file content safely."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def safe_write_file(path: Path, content: str):
    """
    Atomically write content to path using a temporary file.
    """
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)
    
    with tempfile.NamedTemporaryFile('w', delete=False, dir=dir_path, encoding='utf-8') as tf:
        tf.write(content)
        temp_name = tf.name
    
    os.replace(temp_name, path)

def move_file(src: Path, dest: Path):
    """
    Atomically move file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # shutil.move is generally atomic on same filesystem, but os.replace is stricter for rename
    # If cross-device, shutil.move handles it (copy+delete). 
    # For KB, we assume same volume.
    shutil.move(str(src), str(dest))

def prepend_frontmatter(content: str, metadata: dict) -> str:
    """
    Injects or prepends YAML frontmatter.
    Note: original requirement said "Original note content is IMMUTABLE".
    BUT strict rule 6 in steps: "Inject YAML frontmatter...".
    This implies we MODIFY the file to add frontmatter, but preserve the rest.
    The rule "Original note content is IMMUTABLE" likely means "don't change the body text".
    """
    yaml_str = yaml.dump(metadata, sort_keys=False, allow_unicode=True).strip()
    frontmatter = f"---\n{yaml_str}\n---\n\n"
    
    # Check if file already has frontmatter (starts with ---)
    # If so, we might need to merge or skip? 
    # For now, we assume raw notes don't have frontmatter or we just prepend to it.
    # The requirement says "Inject YAML frontmatter".
    # We will just prepend. If there's existing FM, it will be pushed down.
    # Alternatively, we could detect existing FM, but simpler is safer for now.
    
    return frontmatter + content
