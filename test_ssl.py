"""Test Cerebras API with Windows system cert store (for corporate SSL inspection)."""
import os
from dotenv import load_dotenv
load_dotenv()
 
api_key = os.getenv("CEREBRAS_API_KEY", "")
 
# Method 1: Try truststore (uses Windows cert store)
print("--- Method 1: truststore ---")
try:
    import truststore
    truststore.inject_into_ssl()
    print("truststore injected successfully")
   
    from openai import OpenAI
    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    resp = client.chat.completions.create(
        model="llama3.1-8b",
        messages=[{"role": "user", "content": "Say hello in Spanish"}],
        max_tokens=20,
    )
    print(f"SUCCESS: {resp.choices[0].message.content}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
 
# Method 2: Try with SSL verify disabled via httpx
print("\n--- Method 2: httpx with verify=False ---")
try:
    import httpx
    http_client = httpx.Client(verify=False)
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.cerebras.ai/v1",
        api_key=api_key,
        http_client=http_client,
    )
    resp = client.chat.completions.create(
        model="llama3.1-8b",
        messages=[{"role": "user", "content": "Say hello in Spanish"}],
        max_tokens=20,
    )
    print(f"SUCCESS: {resp.choices[0].message.content}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")