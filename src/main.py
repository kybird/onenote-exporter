import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Import components
from src.config import (
    INPUT_DIR, 
    KB_DIR, 
    PAR_DIR, 
    MAX_CONTENT_CHARS, 
    LLM_MODEL
)
from src.state_manager import StateManager
from src.file_ops import (
    get_markdown_files, 
    read_file, 
    safe_write_file, 
    prepend_frontmatter
)
from src.llm import get_llm_client, validate_classification

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description="Note Classification Pipeline")
    parser.add_argument(
        "--input-dir", 
        type=Path, 
        default=INPUT_DIR, 
        help="Path to the input directory containing markdown notes"
    )
    parser.add_argument(
        "--delay", 
        type=float, 
        default=2.0, 
        help="Delay in seconds between processing each file to avoid rate limits"
    )
    return parser.parse_args()

def main():
    import time
    args = parse_arguments()
    input_dir = args.input_dir
    delay = args.delay
    
    logger.info(f"Starting Note Classification Pipeline")
    logger.info(f"Input Directory: {input_dir}")
    logger.info(f"Inter-file Delay: {delay}s")
    
    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        return

    # Initialize
    state_manager = StateManager()
    llm_client = get_llm_client()
    
    # Scan input
    files = get_markdown_files(input_dir)
    logger.info(f"Found {len(files)} files in {input_dir}")
    
    count_processed = 0
    
    for file_path in files:
        file_name = file_path.name
        
        # Check State
        if state_manager.is_processed(file_name):
            logger.info(f"Skipping {file_name} (Already Processed)")
            continue
            
        try:
            logger.info(f"Processing {file_name}...")
            
            # 1. Read Content
            original_content = read_file(file_path)
            
            # 2. Classify (using limited context)
            context_snippet = original_content[:MAX_CONTENT_CHARS]
            
            # Calculate relative path from the specific input dir
            try:
                rel_path = str(file_path.relative_to(input_dir))
            except ValueError:
                rel_path = file_name # Fallback if path issues
                
            try:
                classification_raw = llm_client.classify_note(context_snippet, file_path=rel_path)
            except PermissionError as e:
                logger.error(f"CRITICAL AUTH FAILURE: {e}")
                sys.exit(1)
            
            classification = validate_classification(classification_raw)
            
            logger.info(f"Classified {file_name} as {classification['type']} (conf: {classification['confidence']})")
            
            # 3. Inject Frontmatter
            # We construct the metadata from the classification result
            final_content = prepend_frontmatter(original_content, classification)
            
            # 4. Move to KB (Write to new location, delete old)
            # Determine destination
            dest_subdir = classification['type']
            dest_path = KB_DIR / dest_subdir / file_name
            
            # Safe Write to KB
            safe_write_file(dest_path, final_content)
            
            # Delete from Input (simulating a "Move" with modification)
            # User Preference: Do NOT delete original files.
            # try:
            #     os.remove(file_path)
            # except OSError as e:
            #     logger.warning(f"Could not remove source file {file_path}: {e}")
            #     # If we consider 'read-only' strictly, we might expect this.
            #     # However, we proceed to PAR extraction regardless.
            
            # 5. Extract PAR
            try:
                par_data = llm_client.extract_par(original_content, file_path=rel_path)
            except PermissionError as e:
                logger.error(f"CRITICAL AUTH FAILURE: {e}")
                sys.exit(1)
            
            # 6. Save PAR
            par_filename = file_path.stem + ".json"
            par_path = PAR_DIR / par_filename
            import json
            par_json_str = json.dumps(par_data, indent=2, ensure_ascii=False)
            safe_write_file(par_path, par_json_str)
            
            # 7. Update State
            state_manager.mark_processed(
                file_name=file_name,
                status="completed",
                classification=classification
            )
            count_processed += 1
            
            # Delay to avoid rate limits
            if delay > 0:
                time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Failed to process {file_name}: {e}", exc_info=True)
            # Ensure we don't crash the whole pipeline, but maybe mark as failed?
            # State manager doesn't track failures persistently to prevent retry loops yet, 
            # allowing standard retry on next run.
            continue

    logger.info(f"Pipeline Complete. Processed {count_processed} files.")

if __name__ == "__main__":
    main()
