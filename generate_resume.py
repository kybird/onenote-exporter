
import os
import argparse
import json
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load Env Vars
load_dotenv()

from src.config import PAR_DIR
from src.llm import get_llm_client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_par_data():
    """Load all JSON files from the distilled_par directory."""
    if not PAR_DIR.exists():
        logger.error(f"PAR Directory not found: {PAR_DIR}")
        return []

    data = []
    for file_path in PAR_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                
                # Handle list of PARs (if LLM returned multiple)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            data.append({
                                "file": file_path.stem,
                                "problem": item.get("problem", ""),
                                "action": item.get("action", ""),
                                "result": item.get("result", "")
                            })
                # Handle single PAR object
                elif isinstance(content, dict):
                    if content.get("problem") or content.get("action") or content.get("result"):
                        data.append({
                            "file": file_path.stem,
                            "problem": content.get("problem", ""),
                            "action": content.get("action", ""),
                            "result": content.get("result", "")
                        })
        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
            
    return data




def build_prompt(role: str, par_list: list, is_final: bool = True) -> tuple:
    """Constructs the System and User prompts for the LLM."""
    
    context_text = ""
    
    for item in par_list:
        entry = f"""
        [Project: {item['file']}]
        Problem: {item['problem']}
        Action: {item['action']}
        Result: {item['result']}
        ---
        """
        context_text += entry
        
    if not is_final:
        # Mini-Batch Prompt
        system_prompt = f"""
        Row Resume Drafter for {role} role.
        Extract key technical achievements relevant to {role} from the provided project logs.
        Output as raw bullet points (Korean).
        """
        user_prompt = f"""
        DATA:
        {context_text}
        
        TASK:
        Convert the above data into professional resume bullet points affecting the {role} position.
        Return ONLY the bullet points.
        """
        return system_prompt, user_prompt

    # Final Mode (Single Shot or Master) - Assuming this is used for standard Single Shot
    system_prompt = f"""
    You are an expert Technical Recruiter and Resume Writer specializing in {role} positions.
    Your goal is to write a specialized "Experience" section for a resume tailored specifically to a {role} role.
    
    GUIDELINES:
    1. Analyze the provided project experiences (Problem/Action/Result).
    2. SELECT only the experiences relevant to {role} development. Ignore irrelevant ones.
    3. REWRITE the selected experiences into professional bullet points.
    4. Use strong action verbs (e.g., Designed, Optimized, implemented, Reduced).
    5. Highlight quantitative results (metrics) where available.
    6. Group similar experiences if applicable.
    7. Output format: Markdown.
    """
    
    user_prompt = f"""
    TARGET ROLE: {role} Developer
    
    SOURCE EXPERIENCE DATA:
    {context_text}
    
    TASK:
    Write a targeted professional career detailed description (Resume Experience Section) for this candidate based ONLY on the source data above. 
    Focus on showing their expertise in {role} side. 
    Write in Korean (Hangul).
    """
    
    return system_prompt, user_prompt

def main():
    parser = argparse.ArgumentParser(description="Generate a specialized career description from PAR data.")
    parser.add_argument("--role", type=str, required=True, choices=["server", "client", "fullstack"], help="Target role for the resume (e.g., server, client).")
    parser.add_argument("--output", type=str, help="Output file path.")
    
    args = parser.parse_args()
    
    # 1. Load Data
    logger.info("Loading PAR data...")
    par_data = load_par_data()
    if not par_data:
        logger.error("No PAR data found.")
        sys.exit(1)
        
    logger.info(f"Loaded {len(par_data)} project experiences.")
    
    # 2. Filter Data (Skipped/Pass-through)
    filtered_data = par_data
    # logger.info(f"Filtered down to {len(filtered_data)} items relevant to '{args.role}'.")
    
    if not filtered_data:
        logger.warning(f"No experience found for role '{args.role}'. Using all data.")
        filtered_data = par_data

    client = get_llm_client()
    if hasattr(client, 'model_name'):
         logger.info(f"Using Model: {client.model_name}")

    try:
        # 3. Chunking & Generation (Map-Reduce)
        CHUNK_SIZE = 30  # Items per chunk
        result = ""
        
        if len(filtered_data) > CHUNK_SIZE:
            logger.info(f"Data too large ({len(filtered_data)} items). Using Map-Reduce strategy...")
            
            # Phase 1: Map (Drafting per chunk)
            drafts = []
            chunks = [filtered_data[i:i + CHUNK_SIZE] for i in range(0, len(filtered_data), CHUNK_SIZE)]
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing Chunk {i+1}/{len(chunks)}...")
                sys_p, user_p = build_prompt(args.role, chunk, is_final=False)
                
                try:
                    draft = client.generate_content(sys_p, user_p)
                    drafts.append(draft)
                except Exception as e:
                    logger.error(f"Chunk {i+1} failed: {e}")
            
            # Phase 2: Reduce (Final Polish)
            if not drafts:
                raise RuntimeError("All chunks failed.")
                
            logger.info("Aggregating drafts...")
            combined_drafts = "\n\n".join(drafts)
            
            final_system_prompt = f"""
            You are an expert Resume Writer.
            Your task is to SYNTHESIZE several draft sections into one cohesive, high-quality "Experience" section for a {args.role} developer.
            
            INPUT: Several raw drafts of bullet points.
            OUTPUT: A single, de-duplicated, polished list of professional bullet points (Markdown).
            """
            
            final_user_prompt = f"""
            TARGET ROLE: {args.role} Developer
            
            RAW DRAFTS:
            {combined_drafts}
            
            TASK:
            Merge these drafts into a single Professional Experience section.
            - Eliminate duplicates.
            - Pick the top 10-15 most impactful items.
            - Ensure rigorous professional tone (Korean).
            - Focus on {args.role} technical depth.
            """
            
            logger.info("Generating Final Resume...")
            result = client.generate_content(final_system_prompt, final_user_prompt)
            
        else:
            # Standard Single-Shot
            logger.info("Data fits in context. Running Single-Shot generation...")
            system_prompt, user_prompt = build_prompt(args.role, filtered_data, is_final=True)
            result = client.generate_content(system_prompt, user_prompt)
            
        # 5. Save Output
        output_file = args.output
        if not output_file:
            output_file = f"career_description_{args.role}.md"
            
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
            
        logger.info(f"Success! Career description saved to: {output_file}")
            
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
