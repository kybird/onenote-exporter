import json
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .config import VALID_TYPES, VALID_CONTEXTS, CONFIDENCE_THRESHOLD, LLM_MODEL

logger = logging.getLogger(__name__)

class LLMInterface(ABC):
    @abstractmethod
    def classify_note(self, content: str, file_path: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def extract_par(self, content: str, file_path: str) -> Dict[str, Any]:
        pass

class MockLLM(LLMInterface):
    """
    Mock LLM for testing/verification without API keys.
    Deterministically classifies based on keywords.
    """
    def classify_note(self, content: str, file_path: str) -> Dict[str, Any]:
        lower_content = content.lower()
        lower_path = file_path.lower()
        
        # Simple keyword-based classification for mock purposes
        if "error" in lower_content or "fail" in lower_content or "debug" in lower_path:
            return {
                "type": "problems",
                "context": "debugging",
                "tags": ["mock_error", "fix"],
                "confidence": 0.95
            }
        elif "api" in lower_content or "guide" in lower_content or "reference" in lower_path:
            return {
                "type": "reference",
                "context": "work",
                "tags": ["mock_ref", "docs"],
                "confidence": 0.95
            }
        elif "think" in lower_content or "reflect" in lower_content:
            return {
                "type": "thinking",
                "context": "personal",
                "tags": ["mock_thought"],
                "confidence": 0.95
            }
        else:
            return {
                "type": "inbox",
                "context": "practice",
                "tags": ["mock_random"],
                "confidence": 0.5  # Low confidence -> force inbox
            }

    def extract_par(self, content: str, file_path: str) -> Dict[str, Any]:
        lower_content = content.lower()
        if "problem" in lower_content:
            return {
                "problem": "Mock problem extracted from content",
                "action": "Mock action taken",
                "result": "Mock result achieved"
            }
        return {
            "problem": "",
            "action": "",
            "result": ""
        }

class ProductionLLM(LLMInterface):
    """
    Production LLM using OpenAI-compatible API (OpenRouter).
    """
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        if not OpenAI:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        # Allow model override from env, else use config default
        self.model_name = os.environ.get("LLM_MODEL", LLM_MODEL)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        import time
        from openai import RateLimitError, APIError
        
        max_retries = 5
        base_delay = 5  # Start with 5 seconds wait for free tier
        
        for attempt in range(max_retries):
            try:
                # Log what we are sending (Debug level usually, but User asked)
                logger.debug(f"Sending Request [Attempt {attempt+1}]: Type check or PAR extraction")
                
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                return completion.choices[0].message.content
                
            except RateLimitError as e:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(f"Rate Limit (429) Hit. Waiting {wait_time}s before retry... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                
            except APIError as e:
                # If it's a 429 but raised as APIError
                if e.status_code == 429:
                    wait_time = base_delay * (2 ** attempt)
                    logger.warning(f"API Error 429. Waiting {wait_time}s before retry... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"OpenAI API Error: {e}")
                    logger.error(f"Failed Prompt Context: {user_prompt[:200]}...") # Show snippet
                    return "{}"
                    
            except Exception as e:
                logger.error(f"LLM Call Failed: {e}")
                logger.error(f"Failed Prompt Context: {user_prompt[:200]}...") # Show snippet
                return "{}"
        
        logger.error("Max retries exceeded for LLM call.")
        return "{}"

    def classify_note(self, content: str, file_path: str) -> Dict[str, Any]:
        system_prompt = f"""
        You are a note classifier. Return JSON only.
        
        Possible 'type': {json.dumps(VALID_TYPES)}
        Possible 'context': {json.dumps(VALID_CONTEXTS)}
        RULES:
        1. Extract up to 5 tags.
        2. Provide confidence (0.0-1.0).
        3. Use FILE PATH as context.
        """
        
        user_prompt = f"""
        FILE PATH: {file_path}
        
        CONTENT:
        {content}
        """
        
        response_text = self._call_llm(system_prompt, user_prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Classification JSON: {response_text}")
            return {}

    def extract_par(self, content: str, file_path: str) -> Dict[str, Any]:
        system_prompt = """
        Extract Problem, Action, Result (PAR) as JSON.
        Keys: "problem", "action", "result".
        If missing, use empty string "".
        Do not shorten significantly. Use FILE PATH for context.
        """
        
        user_prompt = f"""
        FILE PATH: {file_path}
        
        CONTENT:
        {content}
        """
        
        response_text = self._call_llm(system_prompt, user_prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse PAR JSON: {response_text}")
            return {"problem": "", "action": "", "result": ""}

    def extract_par(self, content: str, file_path: str) -> Dict[str, Any]:
        system_prompt = """
        Extract Problem, Action, Result (PAR) as JSON.
        Keys: "problem", "action", "result".
        If missing, use empty string "".
        Do not shorten significantly. Use FILE PATH for context.
        """
        
        user_prompt = f"""
        FILE PATH: {file_path}
        
        CONTENT:
        {content}
        """
        
        response_text = self._call_llm(system_prompt, user_prompt)
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse PAR JSON: {response_text}")
            return {"problem": "", "action": "", "result": ""}

class AntigravityLLM(LLMInterface):
    """
    LLM implementation using the reverse-engineered Antigravity API (Google Internal/Sandbox).
    """
    def __init__(self):
        from .auth import get_valid_token
        import requests
        
        self.endpoint = "https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal:generateContent"
        
        # 1. Base Model Resolution (Env -> Alias -> Default)
        default_model = "models/antigravity-gemini-3-pro"
        env_model = os.environ.get("LLM_MODEL", default_model)
        
        # Simple Aliases for Base Models
        aliases = {
            "gemini": "models/antigravity-gemini-3-pro",
            "flash": "models/antigravity-gemini-3-flash", 
            "claude": "models/antigravity-claude-sonnet-4-5",
            "opus": "models/antigravity-claude-opus-4-5",
        }
        base_model = aliases.get(env_model.lower(), env_model)
        
        # 2. Apply Mode Suffix (LLM_MODE)
        # Usage: LLM_MODE=plan (High Thinking), LLM_MODE=fast (Low Thinking)
        mode = os.environ.get("LLM_MODE", "").lower()
        
        self.mode = mode # Store mode for request time
        
        # Do NOT append suffix to model name based on user feedback.
        # "Alias" shouldn't be used to mix Model with Mode.
        # fast/plan should only control the generationConfig parameters.
        
        self.model_name = base_model
             
        logger.info(f"Antigravity Config: Model={self.model_name}, Mode={self.mode}")
        
        try:
            self.access_token = get_valid_token()
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise ImportError(f"Antigravity Auth Failed: {e}")

    def _call_api(self, messages: list) -> str:
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.11.5 windows/amd64",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        }
        
        # Construct Gemini-style body
        # Convert OpenAI-style messages to Gemini contents
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            if msg["role"] == "system":
                # Gemini often handles system prompt differently or just as user/model
                # We'll prepend to user for simplicity or use system_instruction if supported
                # For this internal API, let's try standard 'user' for system prompt first
                role = "user" 
            
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
            
        # Parse model name for API (Strip prefix/suffix)
        # e.g., models/antigravity-gemini-3-pro-high -> models/gemini-3-pro
        api_model = self.model_name
        thinking_level = None
        
        # Determine thinking level from Mode
        if self.mode == "plan":
            thinking_level = "high"
        elif self.mode == "fast":
            thinking_level = "low"
            
        # 1c. Remove 'models/' prefix just in case (API expects just the ID)
        api_model = api_model.replace("models/", "") 
        # (Assuming Antigravity proxy handles the 'antigravity-' part if present, or we strip it if needed)
        api_model = api_model.replace("antigravity-", "")
            
        # 3. Handle specific prefixes like 'models/' + proper ID
        # If it became 'models/gemini-3-flash', that's likely correct.
        
        gen_config = {"responseMimeType": "application/json"}
        if thinking_level:
             # Based on opencode-antigravity-auth/src/plugin/transform/gemini.ts:
             # generationConfig.thinkingConfig = { includeThoughts: true, thinkingLevel: "..." }
             gen_config["thinkingConfig"] = {
                 "includeThoughts": True,
                 "thinkingLevel": thinking_level
             }
            
        payload = {
            "model": api_model,
            "project": "rising-fact-p41fc",
            "request": {
                "contents": contents,
                "generationConfig": gen_config
            }
        }
        
        logger.info(f"Antigravity Req: Model={api_model} (Orig: {self.model_name})")
        try:
            response = requests.post(self.endpoint, headers=headers, json=payload)
            
            if response.status_code == 401:
                # Token might keep expired if script runs long? 
                # Ideally auth logic handles refresh, but if we catch 401 here we could retry
                logger.error("Antigravity API 401 Unauthorized. Token might need refresh.")
                # raise Exception to stop execution
                raise PermissionError("Antigravity API 401 Unauthorized")
                
            if response.status_code != 200:
                logger.error(f"Antigravity API Error {response.status_code}: {response.text}")
                return "{}"
                
            data = response.json()
            
            # Extract candidates (Handle wrapped response)
            # Some proxies return { response: { candidates: [...] } }
            candidates = []
            if 'candidates' in data:
                candidates = data['candidates']
            elif 'response' in data and 'candidates' in data['response']:
                candidates = data['response']['candidates']
            
            if candidates:
                try:
                    # We concatenate ALL parts, including thoughts.
                    # Rationale: Sometimes the model puts the final answer inside the thought block,
                    # or marks the whole response as a thought. _clean_json will extract the code block.
                    parts = candidates[0]['content']['parts']
                    final_text = ""
                    for part in parts:
                        final_text += part.get('text', "")
                    
                    if not final_text:
                        logger.warning(f"Empty text in response: {data}")
                        return "{}"
                        
                    return final_text
                except (KeyError, IndexError, TypeError):
                     logger.error(f"Unexpected JSON structure: {data}")
                     return "{}"
            else:
                logger.error(f"No candidates in response: {data}")
                return "{}"
            
        except Exception as e:
            logger.error(f"Antigravity Request Failed: {e}")
            return "{}"

    def _clean_json(self, text: str) -> str:
        """
        Cleans markdown formatting and extracts JSON object or list.
        """
        # 1. Try to extract content from markdown code blocks
        if "```" in text:
            import re
            # Find ALL code blocks, blindly capturing everything inside
            matches = re.findall(r"```(.*?)```", text, re.DOTALL)
            for match in matches:
                clean_match = match.strip()
                # Remove common language identifiers if present at the start
                # e.g. "json\n{...}" -> "{...}"
                # Handle cases like "json {", "json\n{", or just "{"
                # Simple heuristic: if it doesn't start with { or [, try stripping the first word
                if not (clean_match.startswith("{") or clean_match.startswith("[")):
                    # Split by whitespace to check first word
                    parts = clean_match.split(None, 1)
                    if len(parts) > 1:
                        potential_lang = parts[0].lower()
                        # If first word looks like a lang tag (json, text, etc) and second part starts with brace
                        if potential_lang in ['json', 'json5', 'text', 'code'] or (parts[1].strip().startswith("{") or parts[1].strip().startswith("[")):
                            clean_match = parts[1].strip()
                
                # Check if it looks like JSON
                if (clean_match.startswith("{") and clean_match.endswith("}")) or \
                   (clean_match.startswith("[") and clean_match.endswith("]")):
                    # Validate if it's parseable
                    try:
                        json.loads(clean_match)
                        return clean_match
                    except json.JSONDecodeError:
                        continue
        
        # 2. Fallback: simple strip and brace finder
        text = text.strip()
        
        # Find first { or [
        first_brace = text.find("{")
        first_bracket = text.find("[")
        
        start = -1
        is_object = False
        
        # Determine if we are looking for valid Object or Array
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            start = first_brace
            is_object = True
        elif first_bracket != -1:
            start = first_bracket
            is_object = False
            
        if start != -1:
            if is_object:
                end = text.rfind("}")
            else:
                end = text.rfind("]")
                
            if end != -1 and end > start:
                 candidate = text[start:end+1]
                 # Try parsing fallback
                 try:
                     json.loads(candidate)
                     return candidate
                 except json.JSONDecodeError:
                     pass # Fallback failed
                
        # If all else fails, return original (will likely fail json.loads upstream but logs will show why)
        return text

    def classify_note(self, content: str, file_path: str) -> Dict[str, Any]:
        system_prompt = f"""
        You are a note classifier. Return JSON only.
        valid_types: {json.dumps(VALID_TYPES)}
        valid_contexts: {json.dumps(VALID_CONTEXTS)}
        RULES: Extract 5 tags, confidence (0.0-1.0). Use FILE PATH as context.
        """
        user_prompt = f"FILE PATH: {file_path}\nCONTENT:\n{content}"
        
        response_text = self._call_api([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        try:
            cleaned = self._clean_json(response_text)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"JSON Parse Failed. Raw: {response_text}")
            return {}

    def extract_par(self, content: str, file_path: str) -> Dict[str, Any]:
        system_prompt = "Extract PAR (problem, action, result) as JSON. Use FILE PATH for context."
        user_prompt = f"FILE PATH: {file_path}\nCONTENT:\n{content}"
        
        response_text = self._call_api([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        try:
            cleaned = self._clean_json(response_text)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"PAR JSON Parse Failed. Raw: {response_text}")
            return {"problem": "", "action": "", "result": ""}

def get_llm_client() -> LLMInterface:
    # 1. Check for Configured Model to force Antigravity
    # If user removed keys or explicitly asks for it?
    # Actually, let's prioritize Antigravity if keys are missing OR if a flag is present.
    # User asked to "switch to this".
    
    # We'll try Antigravity if explicitly requested via Config or Env, 
    # OR if other keys are missing but we want to try to be smart.
    # Given the user request "Use this", we should probably default to it if available?
    # But for safety, let's look for an env var or just try it if others fail?
    
    # Let's check for a specific env var "USE_ANTIGRAVITY" or just assumes this is the new default requested.
    # I will make it the PRIMARY choice for now since that's what the user asked.
    
    try:
        logger.info("Attempting to use Antigravity LLM (Google Internal Auth)...")
        return AntigravityLLM()
    except Exception as e:
        logger.warning(f"Antigravity init failed: {e}")
    
    # Fallback to OpenRouter
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        logger.info(f"Using Production LLM (OpenRouter) with model {os.environ.get('LLM_MODEL', LLM_MODEL)}")
        return ProductionLLM(api_key)
    
    logger.warning("No valid LLM credentials found. Using Mock LLM.")
    return MockLLM()

def validate_classification(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strict validation of classification JSON.
    """
    fallback = {
        "type": "inbox",
        "context": "practice",
        "tags": [],
        "confidence": 0.0
    }
    
    if not isinstance(data, dict):
        return fallback

    # Validate Type
    if data.get("type") not in VALID_TYPES:
        data["type"] = "inbox"
    
    # Validate Context
    if data.get("context") not in VALID_CONTEXTS:
        data["context"] = "practice" # Default fallback
    
    # Validate Tags
    if not isinstance(data.get("tags"), list):
        data["tags"] = []
    data["tags"] = [str(t) for t in data["tags"][:5]] # Max 5, ensure strings
    
    # Validate Confidence
    try:
        conf = float(data.get("confidence", 0.0))
    except (ValueError, TypeError):
        conf = 0.0
    
    # Apply Confidence Rule
    if conf < CONFIDENCE_THRESHOLD:
        data["type"] = "inbox"
    
    data["confidence"] = conf
    return data
