import os
import json
import time
import hashlib
import base64
import secrets
import webbrowser
import logging
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode

logger = logging.getLogger(__name__)

# Constants from opencode-antigravity-auth/src/constants.ts
CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]
REDIRECT_URI = "http://localhost:51121/oauth-callback"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
TOKEN_FILE = ".antigravity_token.json"

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/oauth-callback":
            query_params = parse_qs(parsed_path.query)
            if 'code' in query_params:
                self.server.auth_code = query_params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<h1>Authentication Successful!</h1><p>You can close this window and return to the application.</p>")
            else:
                self.send_response(400)
                self.wfile.write(b"Missing code parameter.")
        else:
            self.send_response(404)

def generate_pkce_pair():
    # 1. Generate random verifier
    verifier = secrets.token_urlsafe(64)
    
    # 2. Create challenge: SHA256(verifier)
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    
    # 3. Base64 URL encode the digest (no padding)
    challenge = base64.urlsafe_b64encode(digest).decode('utf-8').replace('=', '')
    
    return verifier, challenge

def authenticate_user():
    """
    Performs full OAuth 2.0 Authorization Code flow with PKCE.
    """
    verifier, challenge = generate_pkce_pair()
    
    # Construct Auth URL
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = f"{AUTH_ENDPOINT}?{urlencode(params)}"
    
    print(f"Opening browser for authentication: {auth_url}")
    webbrowser.open(auth_url)
    
    # Start Local Server to catch callback
    server_address = ('localhost', 51121)
    httpd = HTTPServer(server_address, OAuthCallbackHandler)
    httpd.auth_code = None
    
    print("Waiting for callback...")
    while httpd.auth_code is None:
        httpd.handle_request()
    
    auth_code = httpd.auth_code
    httpd.server_close()
    
    # Exchange Code for Token
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    
    response = requests.post(TOKEN_ENDPOINT, data=data)
    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.text}")
    
    token_data = response.json()
    token_data['expires_at'] = time.time() + token_data['expires_in']
    save_token(token_data)
    return token_data['access_token']

def refresh_access_token(token_data):
    """
    Refreshes the access token using the refresh token.
    """
    refresh_token = token_data.get('refresh_token')
    if not refresh_token:
        # If no refresh token, must re-authenticate
        return authenticate_user()
        
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    response = requests.post(TOKEN_ENDPOINT, data=data)
    if response.status_code != 200:
        logger.warning(f"Failed to refresh token: {response.text}. Re-authenticating.")
        return authenticate_user()
        
    new_data = response.json()
    # Update token data (keep old refresh token if new one not provided)
    token_data['access_token'] = new_data['access_token']
    token_data['expires_in'] = new_data['expires_in']
    token_data['expires_at'] = time.time() + new_data['expires_in']
    if 'refresh_token' in new_data:
        token_data['refresh_token'] = new_data['refresh_token']
        
    save_token(token_data)
    return token_data['access_token']

def save_token(token_data):
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
    except Exception as e:
        logger.error(f"Failed to save token: {e}")

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def get_valid_token():
    """
    Main entry point. Returns a valid access token.
    Handles loading, checking expiry, refreshing, or full auth.
    """
    token_data = load_token()
    
    if not token_data:
        return authenticate_user()
    
    # Check expiry (with 60s buffer)
    if time.time() > token_data.get('expires_at', 0) - 60:
        return refresh_access_token(token_data)
        
    return token_data['access_token']
