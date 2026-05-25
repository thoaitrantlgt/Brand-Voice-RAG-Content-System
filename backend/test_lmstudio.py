"""
test_lmstudio.py - Diagnostic script for LM Studio connection.
Run: python test_lmstudio.py
"""
import requests, json, sys

BASE_URL = "http://127.0.0.1:1234/v1"

# 1. Check loaded models
print("=== 1. Loaded Models ===")
try:
    r = requests.get(f"{BASE_URL}/models", timeout=5)
    models = r.json()
    print(json.dumps(models, indent=2))
    model_id = models["data"][0]["id"] if models.get("data") else None
    print(f"\n>>> Model ID to use: {model_id}\n")
except Exception as e:
    print(f"ERROR connecting to LM Studio: {e}")
    sys.exit(1)

if not model_id:
    print("No model loaded!")
    sys.exit(1)

# 2. Test /nothink in user message
print("=== 2. Test /nothink in user message ===")
payload = {
    "model": model_id,
    "messages": [
        {
            "role": "user",
            "content": '/nothink\nReturn this exact JSON: {"test": true, "status": "ok"}'
        }
    ],
    "max_tokens": 200,
    "temperature": 0.1,
}

try:
    r = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=30)
    resp = r.json()
    content = resp["choices"][0]["message"]["content"]
    print(f"Response: {repr(content)}")
    print(f"Usage: {resp.get('usage', {})}")
except Exception as e:
    print(f"ERROR: {e}")

# 3. Test enable_thinking=False
print("\n=== 3. Test enable_thinking=False ===")
payload2 = {
    "model": model_id,
    "messages": [{"role": "user", "content": "Say: hello"}],
    "max_tokens": 100,
    "temperature": 0.1,
    "enable_thinking": False,
}
try:
    r = requests.post(f"{BASE_URL}/chat/completions", json=payload2, timeout=30)
    resp = r.json()
    content = resp["choices"][0]["message"]["content"]
    print(f"Response: {repr(content)}")
except Exception as e:
    print(f"ERROR: {e}")
