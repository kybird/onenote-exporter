import os
import sys
import shutil
import logging
import time
import json
import argparse
import atexit
import psutil
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
from src.llm import get_llm_client, validate_classification, AntigravityLLM, GroqLLM, LocalLLM

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Singleton Lock Mechanism ---
LOCK_FILE = Path(".lock")

def cleanup_lock():
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass

def acquire_lock():
    """
    Ensures single instance using a lock file and PID check.
    """
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            curr_proc = psutil.Process(old_pid)
            if curr_proc.is_running():
                print(f"Lock file exists. Process {old_pid} is running. Exiting.")
                sys.exit(1)
        except (ValueError, psutil.NoSuchProcess):
            print("Found stale lock file. Removing...")
            pass
            
    LOCK_FILE.write_text(str(os.getpid()))
    atexit.register(cleanup_lock)
# -------------------------------

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
    # Singleton Check
    acquire_lock()
    
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
            
            # Calculate relative path
            try:
                rel_path = str(file_path.relative_to(input_dir))
            except ValueError:
                rel_path = file_name
            


            # Call CLASSIFY with Fallback Logic
            classification_raw = {}
            while True:
                try:
                    classification_raw = llm_client.classify_note(context_snippet, file_path=rel_path)
                    break # Success
                except BlockingIOError:
                    logger.warning("Antigravity Quota Exhausted.")
                    # Fallback Logic: Antigravity -> Groq -> Local
                    if isinstance(llm_client, AntigravityLLM) and os.environ.get("GROQ_API_KEY"):
                        logger.info("Switching to GroqLLM (Groq) Fallback...")
                        try:
                            from src.config import GROQ_LLM_MODEL as CONFIG_GROQ_MODEL
                            api_key = os.environ.get("GROQ_API_KEY")
                            llm_client = GroqLLM(api_key=api_key)
                            llm_client.model_name = os.environ.get("GROQ_LLM_MODEL", CONFIG_GROQ_MODEL) 
                            logger.info(f"Fallback Model: {llm_client.model_name}")
                            continue 
                        except Exception as ex:
                            logger.error(f"Groq Init Failed: {ex}")
                            # Fall through to Local check
                    
                    # If Groq not available or failed init, try Local
                    if not isinstance(llm_client, LocalLLM):
                         logger.info("Switching to LocalLLM Fallback...")
                         try:
                             from src.config import LOCAL_LLM_URL, LOCAL_LLM_MODEL
                             llm_client = LocalLLM(base_url=LOCAL_LLM_URL)
                             llm_client.model_name = LOCAL_LLM_MODEL
                             logger.info(f"Fallback Model: {llm_client.model_name} at {LOCAL_LLM_URL}")
                             continue
                         except Exception as ex:
                             logger.error(f"Local Fallback Failed: {ex}")
                             sys.exit(1)
                    else:
                        logger.error("CRITICAL FAILURE: Quota Exhausted and all Fallbacks failed.")
                        sys.exit(1)

                except (RuntimeError, PermissionError, TimeoutError) as e:
                    # Catch RuntimeError from Groq/Local failures
                    logger.error(f"Provider Error: {e}")
                    
                    # Build Fallback Chain here too if not BlockingIOError (e.g. Rate Limit on Groq)
                    if isinstance(llm_client, GroqLLM):
                         logger.info("Groq Failed. Switching to LocalLLM Fallback...")
                         try:
                             from src.config import LOCAL_LLM_URL, LOCAL_LLM_MODEL
                             llm_client = LocalLLM(base_url=LOCAL_LLM_URL)
                             llm_client.model_name = LOCAL_LLM_MODEL
                             logger.info(f"Fallback Model: {llm_client.model_name} at {LOCAL_LLM_URL}")
                             continue
                         except Exception as ex:
                             logger.error(f"Local Fallback Failed: {ex}")
                             sys.exit(1)
                    
                    logger.error("CRITICAL FAILURE: No more fallbacks.")
                    sys.exit(1)
            
            classification = validate_classification(classification_raw)
            
            logger.info(f"Classified {file_name} as {classification['type']} (conf: {classification['confidence']})")
            
            # 3. Inject Frontmatter
            final_content = prepend_frontmatter(original_content, classification)
            
            # 4. Move to KB
            dest_subdir = classification['type']
            dest_path = KB_DIR / dest_subdir / file_name
            
            safe_write_file(dest_path, final_content)
            
            # 5. Extract PAR
            par_data = {}
            while True:
                try:
                    par_data = llm_client.extract_par(original_content, file_path=rel_path)
                    break 
                except BlockingIOError:
                    logger.warning("Antigravity Quota Exhausted during PAR extraction.")
                    if isinstance(llm_client, AntigravityLLM) and os.environ.get("GROQ_API_KEY"):
                        logger.info("Switching to GroqLLM (Groq) Fallback...")
                        try:
                            from src.config import GROQ_LLM_MODEL as CONFIG_GROQ_MODEL
                            api_key = os.environ.get("GROQ_API_KEY")
                            llm_client = GroqLLM(api_key=api_key)
                            llm_client.model_name = os.environ.get("GROQ_LLM_MODEL", CONFIG_GROQ_MODEL) 
                            logger.info(f"Fallback Model: {llm_client.model_name}")
                            continue
                        except Exception as ex:
                             logger.error(f"Groq Init Failed: {ex}")
                    
                    if not isinstance(llm_client, LocalLLM):
                         logger.info("Switching to LocalLLM Fallback...")
                         try:
                             from src.config import LOCAL_LLM_URL, LOCAL_LLM_MODEL
                             llm_client = LocalLLM(base_url=LOCAL_LLM_URL)
                             llm_client.model_name = LOCAL_LLM_MODEL
                             logger.info(f"Fallback Model: {llm_client.model_name} at {LOCAL_LLM_URL}")
                             continue
                         except Exception as ex:
                             logger.error(f"Local Fallback Failed: {ex}")
                             sys.exit(1)
                    else:
                        logger.error("CRITICAL FAILURE: All Fallbacks failed.")
                        sys.exit(1)

                except (RuntimeError, PermissionError, TimeoutError) as e:
                    logger.error(f"Provider Error: {e}")
                    if isinstance(llm_client, GroqLLM):
                         logger.info("Groq Failed. Switching to LocalLLM Fallback...")
                         try:
                             from src.config import LOCAL_LLM_URL, LOCAL_LLM_MODEL
                             llm_client = LocalLLM(base_url=LOCAL_LLM_URL)
                             llm_client.model_name = LOCAL_LLM_MODEL
                             logger.info(f"Fallback Model: {llm_client.model_name} at {LOCAL_LLM_URL}")
                             continue
                         except Exception as ex:
                             logger.error(f"Local Fallback Failed: {ex}")
                             sys.exit(1)
                    
                    logger.error("CRITICAL FAILURE: No more fallbacks.")
                    sys.exit(1)
            
            # 6. Save PAR
            par_filename = file_path.stem + ".json"
            par_path = PAR_DIR / par_filename
            
            par_json_str = json.dumps(par_data, indent=2, ensure_ascii=False)
            safe_write_file(par_path, par_json_str)
            
            # 7. Update State
            state_manager.mark_processed(
                file_name=file_name,
                status="completed",
                classification=classification
            )
            count_processed += 1
            
            # Delay
            if delay > 0:
                time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Failed to process {file_name}: {e}", exc_info=True)
            continue

    logger.info(f"Pipeline Complete. Processed {count_processed} files.")

if __name__ == "__main__":
    main()
