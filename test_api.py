"""Quick test of Cerebras API connectivity."""
import os
from dotenv import load_dotenv
load_dotenv()
 
api_key = os.getenv("CEREBRAS_API_KEY", "")
print(f"API Key loaded: {'Yes' if api_key else 'No'} ({api_key[:10]}...)")
 
# Test 1: DNS resolution
import socket
try:
    ip = socket.getaddrinfo("api.cerebras.ai", 443)
    print(f"DNS resolved: api.cerebras.ai -> {ip[0][4][0]}")
except Exception as e:
    print(f"DNS FAILED: {e}")
 
# Test 2: HTTPS connection
import urllib.request
import ssl
 
try:
    ctx = ssl.create_default_context()
    req = urllib.request.Request("https://api.cerebras.ai/v1/models", headers={
        "Authorization": f"Bearer {api_key}"
    })
    resp = urllib.request.urlopen(req, timeout=10, context=ctx)
    print(f"Direct HTTPS: {resp.status} - {resp.read()[:200].decode()}")
except Exception as e:
    print(f"Direct HTTPS FAILED: {e}")
 
# Test 3: Check proxy settings
proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"]
for v in proxy_vars:
    val = os.environ.get(v, "")
    if val:
        print(f"  {v} = {val}")
    else:
        print(f"  {v} = (not set)")
 
# Test 4: Try with openai client
print("\nTesting OpenAI client to Cerebras...")
try:
    from openai import OpenAI
    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    models = client.models.list()
    print(f"Models available: {[m.id for m in models.data]}")
except Exception as e:
    print(f"OpenAI client FAILED: {type(e).__name__}: {e}")