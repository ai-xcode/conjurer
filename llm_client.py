"""llm_client.py — provider-agnostic LLM client.

One API. Six providers. End user picks via env var:

  LLM_PROVIDER=ollama        # default — local, free, runs on Mac/Linux/Win
  LLM_PROVIDER=vllm          # local vLLM/JARVIS-compatible OpenAI server
  LLM_PROVIDER=openai        # cloud, paid
  LLM_PROVIDER=anthropic     # cloud, paid (Claude)
  LLM_PROVIDER=deepseek      # cloud, very cheap, very capable
  LLM_PROVIDER=groq          # cloud, free tier, fast
  LLM_PROVIDER=xai           # cloud, paid (Grok)
  LLM_PROVIDER=auto          # auto-detect: tries ollama → vllm → first cloud key

Required env per provider (only one set needed):
  OLLAMA_HOST      (default http://127.0.0.1:11434)
  VLLM_BASE_URL    (default http://127.0.0.1:8001/v1)
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  DEEPSEEK_API_KEY
  GROQ_API_KEY
  XAI_API_KEY

Optional model override:
  LLM_MODEL=qwen2.5:14b      (whatever is available in your provider)

Usage:
    from llm.llm_client import LLMClient
    client = LLMClient()
    answer = client.complete("Score AAPL momentum 0-10",
                             system="You are a trading analyst.",
                             max_tokens=200)
"""
from __future__ import annotations
import json, os, urllib.request, urllib.error
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text:        str
    model:       str
    provider:    str
    tokens_in:   int = 0
    tokens_out:  int = 0
    cost_usd:    float = 0.0
    error:       str | None = None


# Approx prices per 1M tokens (input / output) for cost tracking. Update as needed.
_PRICES = {
    "openai":     {"in": 5.00, "out": 15.00},   # gpt-4o
    "anthropic":  {"in": 3.00, "out": 15.00},   # claude-3.5-sonnet
    "deepseek":   {"in": 0.27, "out": 1.10},    # deepseek-chat
    "groq":       {"in": 0.05, "out": 0.08},    # llama-3.1-70b
    "xai":        {"in": 5.00, "out": 15.00},   # grok-2
    "ollama":     {"in": 0,    "out": 0},
    "vllm":       {"in": 0,    "out": 0},
}


def _http_post(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, method="POST",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": f"{e.code}: {e.read().decode()[:400]}"}
    except Exception as e:
        return {"_error": str(e)}


class LLMClient:
    """One client. Multi-provider. Same `.complete()` API everywhere."""

    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "auto")).lower()
        self.model    =  model or os.environ.get("LLM_MODEL")
        if self.provider == "auto":
            self.provider = self._autodetect()

    # ── auto-detect: prefer local, fall back to whichever cloud key is set ──
    def _autodetect(self) -> str:
        # Try Ollama
        try:
            host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
            urllib.request.urlopen(f"{host}/api/tags", timeout=1).read()
            return "ollama"
        except Exception:
            pass
        # Try vLLM (or JARVIS) on 8001
        try:
            base = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8001/v1")
            urllib.request.urlopen(f"{base}/models", timeout=1).read()
            return "vllm"
        except Exception:
            pass
        # Fall back to whichever cloud key is set
        for prov, env in [("anthropic", "ANTHROPIC_API_KEY"),
                          ("openai",    "OPENAI_API_KEY"),
                          ("deepseek",  "DEEPSEEK_API_KEY"),
                          ("groq",      "GROQ_API_KEY"),
                          ("xai",       "XAI_API_KEY")]:
            if os.environ.get(env): return prov
        return "ollama"   # last-ditch; complete() will report missing server

    # ── public API ────────────────────────────────────────────────
    def complete(self, prompt: str, system: str = "",
                 max_tokens: int = 512,
                 temperature: float = 0.3) -> LLMResponse:
        if self.provider == "anthropic":
            return self._anthropic(prompt, system, max_tokens, temperature)
        if self.provider == "bedrock":
            return self._bedrock(prompt, system, max_tokens, temperature)
        if self.provider == "vertex":
            return self._vertex(prompt, system, max_tokens, temperature)
        if self.provider == "gemini":
            return self._gemini(prompt, system, max_tokens, temperature)
        return self._openai_compat(prompt, system, max_tokens, temperature)

    # ── OpenAI-compatible path ────────────────────────────────────
    def _openai_compat(self, prompt, system, max_tokens, temperature) -> LLMResponse:
        cfg = _OPENAI_COMPAT[self.provider]
        url = cfg["url"]()
        api_key = os.environ.get(cfg["key_env"], "")
        headers = {}
        if api_key:
            # Azure uses "api-key: <key>" instead of "Authorization: Bearer".
            auth_header = cfg.get("auth_header", "Authorization")
            headers[auth_header] = (api_key if auth_header == "api-key"
                                            else f"Bearer {api_key}")
        # OpenRouter benefits from referer + title headers (avoids low-priority queue)
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = os.environ.get("OPENROUTER_REFERER",
                                                      "https://sentinel-trader.local")
            headers["X-Title"]      = "Sentinel Trader"
        model = self.model or cfg["default_model"]
        msgs = []
        if system: msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        body = {
            "model":       model,
            "messages":    msgs,
            "max_tokens":  max_tokens,
            "temperature": temperature,
            "stream":      False,
        }
        r = _http_post(url, headers, body)
        if r.get("_error"):
            return LLMResponse(text="", model=model, provider=self.provider,
                               error=r["_error"])
        try:
            text = r["choices"][0]["message"]["content"]
        except Exception:
            return LLMResponse(text="", model=model, provider=self.provider,
                               error=f"unexpected shape: {str(r)[:300]}")
        usage = r.get("usage", {})
        ti, to = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        price = _PRICES.get(self.provider, {"in": 0, "out": 0})
        cost = (ti * price["in"] + to * price["out"]) / 1_000_000
        return LLMResponse(text=text, model=model, provider=self.provider,
                           tokens_in=ti, tokens_out=to, cost_usd=cost)

    # ── Anthropic path: different message shape ────────────────────
    def _anthropic(self, prompt, system, max_tokens, temperature) -> LLMResponse:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return LLMResponse(text="", model="?", provider="anthropic",
                               error="ANTHROPIC_API_KEY not set")
        model = self.model or "claude-sonnet-4-6"
        body = {
            "model":       model,
            "max_tokens":  max_tokens,
            "temperature": temperature,
            "messages":    [{"role": "user", "content": prompt}],
        }
        if system: body["system"] = system
        headers = {
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        }
        r = _http_post("https://api.anthropic.com/v1/messages", headers, body)
        if r.get("_error"):
            return LLMResponse(text="", model=model, provider="anthropic",
                               error=r["_error"])
        try:
            text = r["content"][0]["text"]
        except Exception:
            return LLMResponse(text="", model=model, provider="anthropic",
                               error=f"unexpected shape: {str(r)[:300]}")
        usage = r.get("usage", {})
        ti, to = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cost = (ti * _PRICES["anthropic"]["in"] +
                to * _PRICES["anthropic"]["out"]) / 1_000_000
        return LLMResponse(text=text, model=model, provider="anthropic",
                           tokens_in=ti, tokens_out=to, cost_usd=cost)

    # ── AWS Bedrock (Anthropic + Llama + Mistral on AWS IAM) ───────
    def _bedrock(self, prompt, system, max_tokens, temperature) -> LLMResponse:
        try:
            import boto3
        except ImportError:
            return LLMResponse(text="", model="?", provider="bedrock",
                error="boto3 not installed (pip install boto3)")
        region = os.environ.get("AWS_REGION", "us-east-1")
        model_id = self.model or "anthropic.claude-3-5-sonnet-20241022-v2:0"
        client = boto3.client("bedrock-runtime", region_name=region)
        msgs = [{"role": "user", "content": [{"text": prompt}]}]
        body = {"messages": msgs, "inferenceConfig":
                {"maxTokens": max_tokens, "temperature": temperature}}
        if system: body["system"] = [{"text": system}]
        try:
            r = client.converse(modelId=model_id, **body)
            text = r["output"]["message"]["content"][0]["text"]
            usage = r.get("usage", {})
            return LLMResponse(text=text, model=model_id, provider="bedrock",
                tokens_in=usage.get("inputTokens", 0),
                tokens_out=usage.get("outputTokens", 0))
        except Exception as e:
            return LLMResponse(text="", model=model_id, provider="bedrock",
                error=str(e))

    # ── Google Vertex AI (Anthropic + Gemini + Llama on GCP) ───────
    def _vertex(self, prompt, system, max_tokens, temperature) -> LLMResponse:
        try:
            from google.auth import default
            from google.auth.transport.requests import Request
        except ImportError:
            return LLMResponse(text="", model="?", provider="vertex",
                error="google-auth not installed (pip install google-auth)")
        project = os.environ.get("GCP_PROJECT", "")
        location = os.environ.get("GCP_LOCATION", "us-central1")
        model = self.model or "claude-sonnet-4-5@20250929"
        if not project:
            return LLMResponse(text="", model=model, provider="vertex",
                error="GCP_PROJECT env var not set")
        try:
            creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            creds.refresh(Request())
            url = (f"https://{location}-aiplatform.googleapis.com/v1"
                   f"/projects/{project}/locations/{location}"
                   f"/publishers/anthropic/models/{model}:rawPredict")
            body = {
                "anthropic_version": "vertex-2023-10-16",
                "max_tokens":  max_tokens,
                "temperature": temperature,
                "messages":    [{"role": "user", "content": prompt}],
            }
            if system: body["system"] = system
            r = _http_post(url, {"Authorization": f"Bearer {creds.token}"}, body)
            if r.get("_error"):
                return LLMResponse(text="", model=model, provider="vertex",
                    error=r["_error"])
            text = r["content"][0]["text"]
            usage = r.get("usage", {})
            return LLMResponse(text=text, model=model, provider="vertex",
                tokens_in=usage.get("input_tokens", 0),
                tokens_out=usage.get("output_tokens", 0))
        except Exception as e:
            return LLMResponse(text="", model=model, provider="vertex",
                error=str(e))

    # ── Google Gemini (direct API, separate from Vertex) ───────────
    def _gemini(self, prompt, system, max_tokens, temperature) -> LLMResponse:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return LLMResponse(text="", model="?", provider="gemini",
                error="GEMINI_API_KEY not set")
        model = self.model or "gemini-2.0-flash"
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        contents = []
        if system:
            contents.append({"role": "user",
                             "parts": [{"text": f"[System]\n{system}"}]})
            contents.append({"role": "model",
                             "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        body = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature":     temperature,
            }
        }
        r = _http_post(url, {}, body)
        if r.get("_error"):
            return LLMResponse(text="", model=model, provider="gemini",
                error=r["_error"])
        try:
            text = r["candidates"][0]["content"]["parts"][0]["text"]
            usage = r.get("usageMetadata", {})
            return LLMResponse(text=text, model=model, provider="gemini",
                tokens_in=usage.get("promptTokenCount", 0),
                tokens_out=usage.get("candidatesTokenCount", 0))
        except Exception as e:
            return LLMResponse(text="", model=model, provider="gemini",
                error=f"unexpected shape: {e}; raw={str(r)[:300]}")

    # ── helpers ────────────────────────────────────────────────────
    def health(self) -> dict:
        """Quick handshake. Useful for installer + health dashboard."""
        r = self.complete("ping", system="Reply with the single word: pong",
                          max_tokens=8, temperature=0)
        return {
            "provider": self.provider,
            "model":    self.model or _default_model_for(self.provider),
            "ok":       r.error is None and "pong" in r.text.lower(),
            "error":    r.error,
            "raw":      r.text[:60],
        }


_OPENAI_COMPAT = {
    # ── LOCAL ──
    "ollama": {
        "url":           lambda: f"{os.environ.get('OLLAMA_HOST','http://127.0.0.1:11434')}/v1/chat/completions",
        "key_env":       "OLLAMA_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "qwen2.5:14b"),
    },
    "vllm": {
        "url":           lambda: f"{os.environ.get('VLLM_BASE_URL','http://127.0.0.1:8001/v1')}/chat/completions",
        "key_env":       "VLLM_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-32B-Instruct-AWQ"),
    },
    "lmstudio": {
        "url":           lambda: f"{os.environ.get('LMSTUDIO_HOST','http://127.0.0.1:1234')}/v1/chat/completions",
        "key_env":       "LMSTUDIO_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "loaded-model"),
    },
    "llamacpp": {
        "url":           lambda: f"{os.environ.get('LLAMACPP_HOST','http://127.0.0.1:8080')}/v1/chat/completions",
        "key_env":       "LLAMACPP_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "llamacpp-model"),
    },
    "custom": {   # any OpenAI-compatible self-hosted endpoint
        "url":           lambda: os.environ.get("CUSTOM_LLM_URL", "http://127.0.0.1:8000/v1/chat/completions"),
        "key_env":       "CUSTOM_LLM_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "custom"),
    },
    # ── DIRECT CLOUD APIs ──
    "openai": {
        "url":           lambda: "https://api.openai.com/v1/chat/completions",
        "key_env":       "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "deepseek": {
        "url":           lambda: "https://api.deepseek.com/v1/chat/completions",
        "key_env":       "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "url":           lambda: "https://api.groq.com/openai/v1/chat/completions",
        "key_env":       "GROQ_API_KEY",
        "default_model": "llama-3.1-70b-versatile",
    },
    "xai": {
        "url":           lambda: "https://api.x.ai/v1/chat/completions",
        "key_env":       "XAI_API_KEY",
        "default_model": "grok-2-latest",
    },
    # ── AGGREGATORS ──
    "openrouter": {  # one key, hundreds of models, including Claude/GPT/Llama
        "url":           lambda: "https://openrouter.ai/api/v1/chat/completions",
        "key_env":       "OPENROUTER_API_KEY",
        "default_model": os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4.5"),
    },
    "together": {
        "url":           lambda: "https://api.together.xyz/v1/chat/completions",
        "key_env":       "TOGETHER_API_KEY",
        "default_model": "meta-llama/Llama-3.1-70B-Instruct-Turbo",
    },
    "mistral": {
        "url":           lambda: "https://api.mistral.ai/v1/chat/completions",
        "key_env":       "MISTRAL_API_KEY",
        "default_model": "mistral-large-latest",
    },
    "cohere": {
        "url":           lambda: "https://api.cohere.ai/compatibility/v1/chat/completions",
        "key_env":       "COHERE_API_KEY",
        "default_model": "command-r-plus",
    },
    "perplexity": {
        "url":           lambda: "https://api.perplexity.ai/chat/completions",
        "key_env":       "PERPLEXITY_API_KEY",
        "default_model": "llama-3.1-sonar-large-128k-online",
    },
    "fireworks": {
        "url":           lambda: "https://api.fireworks.ai/inference/v1/chat/completions",
        "key_env":       "FIREWORKS_API_KEY",
        "default_model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
    },
    # ── ENTERPRISE CLOUD (still OpenAI-compat) ──
    "azure": {   # Azure OpenAI Service
        "url":           lambda: f"{os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')}"
                                  f"/openai/deployments/{os.environ.get('AZURE_OPENAI_DEPLOYMENT','gpt-4o')}"
                                  f"/chat/completions?api-version="
                                  f"{os.environ.get('AZURE_OPENAI_API_VERSION','2024-02-15-preview')}",
        "key_env":       "AZURE_OPENAI_API_KEY",   # uses 'api-key' header, not Bearer
        "default_model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "auth_header":   "api-key",
    },
}


def _default_model_for(prov: str) -> str:
    if prov == "anthropic": return "claude-sonnet-4-6"
    if prov == "bedrock":   return "anthropic.claude-3-5-sonnet-20241022-v2:0"
    if prov == "vertex":    return "claude-sonnet-4-5@20250929"
    if prov == "gemini":    return "gemini-2.0-flash"
    return _OPENAI_COMPAT.get(prov, {}).get("default_model", "?")


def list_providers() -> list[dict]:
    """For installer: which providers can we actually use right now?"""
    out = []

    # Local — probe each
    local_probes = [
        ("ollama",   "http://127.0.0.1:11434/api/tags",    "OLLAMA_HOST",
         "curl -fsSL https://ollama.com/install.sh | sh"),
        ("vllm",     "http://127.0.0.1:8001/v1/models",    "VLLM_BASE_URL",
         "needs GPU + vLLM server"),
        ("lmstudio", "http://127.0.0.1:1234/v1/models",    "LMSTUDIO_HOST",
         "download LM Studio + start its local server"),
        ("llamacpp", "http://127.0.0.1:8080/v1/models",    "LLAMACPP_HOST",
         "run llama-server -m <model.gguf> --host 127.0.0.1 --port 8080"),
    ]
    for name, default_url, env, hint in local_probes:
        url = os.environ.get(env, default_url)
        try:
            urllib.request.urlopen(url, timeout=1).read()
            out.append({"name": name, "type": "local", "ready": True})
        except Exception:
            out.append({"name": name, "type": "local", "ready": False, "hint": hint})

    # Direct cloud APIs — readiness = key set
    for prov, env in [
        ("anthropic",  "ANTHROPIC_API_KEY"),
        ("openai",     "OPENAI_API_KEY"),
        ("deepseek",   "DEEPSEEK_API_KEY"),
        ("groq",       "GROQ_API_KEY"),
        ("xai",        "XAI_API_KEY"),
        ("gemini",     "GEMINI_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("together",   "TOGETHER_API_KEY"),
        ("mistral",    "MISTRAL_API_KEY"),
        ("cohere",     "COHERE_API_KEY"),
        ("perplexity", "PERPLEXITY_API_KEY"),
        ("fireworks",  "FIREWORKS_API_KEY"),
    ]:
        out.append({"name": prov, "type": "cloud",
                    "ready": bool(os.environ.get(env)),
                    "hint":  f"set {env}=…"})

    # Enterprise cloud — readiness = appropriate creds
    out.append({"name": "azure", "type": "enterprise",
                "ready": bool(os.environ.get("AZURE_OPENAI_API_KEY")
                              and os.environ.get("AZURE_OPENAI_ENDPOINT")),
                "hint": "set AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT"})
    out.append({"name": "bedrock", "type": "enterprise",
                "ready": bool(os.environ.get("AWS_ACCESS_KEY_ID")
                              or os.path.exists(os.path.expanduser("~/.aws/credentials"))),
                "hint": "configure AWS creds (aws configure / IAM role)"})
    out.append({"name": "vertex", "type": "enterprise",
                "ready": bool(os.environ.get("GCP_PROJECT")
                              and (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                                   or os.path.exists(os.path.expanduser(
                                       "~/.config/gcloud/application_default_credentials.json")))),
                "hint": "set GCP_PROJECT + run 'gcloud auth application-default login'"})

    # Custom self-hosted endpoint
    out.append({"name": "custom", "type": "self-hosted",
                "ready": bool(os.environ.get("CUSTOM_LLM_URL")),
                "hint": "set CUSTOM_LLM_URL=https://your-endpoint/v1/chat/completions"})
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list",   action="store_true", help="list providers + readiness")
    ap.add_argument("--health", action="store_true", help="ping the configured provider")
    ap.add_argument("--ask",    help="one-shot prompt; prints answer")
    args = ap.parse_args()

    if args.list:
        for p in list_providers():
            mark = "✓" if p["ready"] else "·"
            print(f"  {mark} {p['name']:<10} ({p['type']})  "
                  f"{'' if p['ready'] else p.get('hint','')}")
    elif args.health:
        c = LLMClient()
        print(json.dumps(c.health(), indent=2))
    elif args.ask:
        c = LLMClient()
        r = c.complete(args.ask, max_tokens=400)
        if r.error:
            print(f"ERROR: {r.error}")
        else:
            print(r.text)
            print(f"\n[{r.provider}/{r.model}  tokens={r.tokens_in}+{r.tokens_out}  ${r.cost_usd:.4f}]")
    else:
        ap.print_help()
