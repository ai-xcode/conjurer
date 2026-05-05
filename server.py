"""server.py — registers /conjurer/* routes on ComfyUI's own aiohttp server.

Endpoints:
  POST /conjurer/chat       — { text, provider } → { reply, plan, error }
  GET  /conjurer/status     — { vllm_tiers, deepseek_key, workflows }
  GET  /conjurer/workflow/<name>  — returns the raw workflow JSON
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from aiohttp import web
from server import PromptServer  # provided by ComfyUI

EXT_DIR = Path(__file__).resolve().parent

# ── env loader (so DEEPSEEK_API_KEY etc. flow in from .env) ────────
def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        if k and v and k not in os.environ:
            os.environ[k] = v


_load_env_file(EXT_DIR / ".env")
sys.path.insert(0, str(EXT_DIR))

# Top-level workflows dir — scanned recursively at startup AND on each /chat
# (cheap scan, ~50 files).
WORKFLOW_DIR = Path.home() / "ComfyUI/user/default/workflows"


# Map folder names under _organized/NN-name/ to user-facing categories
_FOLDER_CATEGORY = {
    "01-text-to-image":  "photo",
    "02-image-edit":     "edit-photo",
    "03-image-edit-flux": "edit-photo",
    "04-image-to-video": "video",
    "05-text-to-video":  "video",
    "06-controlnet":     "controlnet",
    "07-product":        "product",
    "08-portrait":       "portrait",
    "09-animation":      "animation",
    "10-utility":        "utility",
    "11-style-transfer": "style-transfer",
    "12-face-swap":      "face-swap",
    "13-dance":          "dance",
    "14-lipsync":        "audio→video",
    "99-misc":           "misc",
}


def _categorize(rel_path: str) -> tuple[str, str]:
    """Filename + path → (category, short tagline).

    Uses the folder hierarchy first (_organized/NN-name/sub/file.json),
    falls back to filename keyword scoring for files at the top level.
    """
    parts = rel_path.replace("\\", "/").split("/")
    name = parts[-1].lower().replace(".json", "")
    folders = [p.lower() for p in parts[:-1]]

    # 1) folder-based categorization (Sam's _organized/ tree)
    for folder in folders:
        if folder in _FOLDER_CATEGORY:
            sub = parts[-2] if len(parts) >= 2 and parts[-2] != folder else ""
            tagline = name.replace("-", " ").replace("_", " ")
            if sub:
                tagline = f"{sub} · {tagline}"
            return (_FOLDER_CATEGORY[folder], tagline)

    # 2) structured naming convention (t2v_..., i2v_..., etc.)
    if name.startswith(("t2v_", "i2v_", "ti2v_", "flf_")):
        prefix = name.split("_", 1)[0]
        kind = {"t2v": "text→video", "i2v": "image→video",
                "ti2v": "text/image→video", "flf": "first-last-frame video"}[prefix]
        return ("video", f"{kind} ({name.replace('_', ' ')})")

    # 3) numbered-library filename keywords
    body = name.split("_", 1)[1] if name[:2].isdigit() else name
    keyword_map = [
        (("text-to-image", "portrait-studio", "headshot", "txt2img", "txt-to-image"), "photo"),
        (("edit-photo", "portrait-fixer", "color-grade", "clarity", "remove-objects",
          "extend-image", "swap-background", "img2img", "inpaint", "outpaint"), "edit-photo"),
        (("face-swap", "instantid", "reactor"), "face-swap"),
        (("dance", "animatediff", "motion-lora", "from-reference", "video-to-video"), "dance"),
        (("controlnet", "openpose", "depth-map", "lineart", "softedge", "normal-map", "shuffle"), "controlnet"),
        (("upscale-video",), "upscale-video"),
        (("upscale-image", "hd-upscale", "ccsr", "supir", "apisr"), "upscale-image"),
        (("smooth-fps", "frame-interp", "rife"), "interpolate"),
        (("lipsync", "wan22-s2v", "audio-to-video", "audio→video"), "audio→video"),
        (("long-video", "text-to-video-long", "video-chain"), "long-video"),
        (("ad-maker", "social-reel", "cinematic-short", "product-showcase"), "video-format"),
        (("text-to-video", "photo-to-video", "image-to-video", "image2video", "img2vid"), "video"),
        (("ipadapter",), "style-transfer"),
        (("interrogate", "joycaption", "describe-image", "image-to-prompt"), "utility"),
    ]
    for kws, cat in keyword_map:
        if any(k in body for k in kws):
            return (cat, body.replace("-", " "))
    return ("other", body.replace("-", " "))


def _build_catalog() -> dict:
    """Scan WORKFLOW_DIR recursively and produce {rel_path: {category, tagline}}."""
    catalog = {}
    if not WORKFLOW_DIR.is_dir():
        return catalog
    for p in sorted(WORKFLOW_DIR.rglob("*.json")):
        rel = str(p.relative_to(WORKFLOW_DIR))
        cat, tagline = _categorize(rel)
        catalog[rel] = {"category": cat, "tagline": tagline}
    return catalog


# Built once per request (cheap, ~50 file stats); always reflects what's on disk.
def CATALOG():
    return _build_catalog()

SYSTEM_PROMPT = """You are a ComfyUI assistant running inside ComfyUI itself.

You handle three kinds of requests:

  RENDER  — user asks for an image/video/edit. Pick a workflow + write prompts.
  ASK     — user asks a question about ComfyUI ("what does CLIPTextEncode do?",
            "find me a node for face swap"). Answer in plain text. NO render block.
  DEBUG   — user pastes an error or asks "why isn't this working". Diagnose and
            suggest specific fixes. NO render block unless they ask you to swap
            in a working workflow.

For RENDER requests:
  1. Pick the BEST workflow from the catalog (use EXACT filename including any subfolder)
  2. Compose strong positive + sensible negative prompts
  3. Output ONE render plan as a fenced code block:

```render
{
  "workflow":        "<exact filename from catalog>",
  "positive_prompt": "<the visual description, 1-3 sentences>",
  "negative_prompt": "<things to avoid; default 'low quality, blurry, distorted'>",
  "rationale":       "<one sentence why you picked this>"
}
```

  4. Briefly explain your choice in plain English after the block.

Routing by category:
  • PHOTO (text→image)         → "01_text-to-image_qwen_FAST.json" or "27_PORTRAIT-STUDIO-allinone_qwen_FAST.json"
  • EDIT a photo               → 02 (general edit), 12 (portrait fix), 13 (color grade), 14 (sharpen),
                                 15 (remove objects), 16 (extend canvas), 17 (swap background)
  • UPSCALE photo              → "10_upscale-image_realesrgan_FAST.json"
  • UPSCALE video              → "08_upscale-video_realesrgan_MED.json"
  • SMOOTH 60fps video         → "09_smooth-fps_film_FAST.json"
  • SHORT video (1-5s)         → sentinel-fast-video/* (t2v/i2v/ti2v/flf) or 03/04/19/20
  • LONG video (10s+)          → "11_text-to-video-long_wan22_SLOW.json" or
                                 "06_long-video-chain_wan22-flf_MED.json" (chained, longest)
  • CINEMATIC / AD / REEL      → 23 (ad), 24 (vertical reel), 25 (cinematic), 26 (product)
  • LIPSYNC from audio         → "05_lipsync-from-audio_wan22-s2v_SLOW.json"
  • PHOTO → animated video     → 04 (Wan), 20 (LTX fast), 22 (LTX HD), 18 (quick preview)

Rules:
  - ONLY one ```render block per response
  - Use the FULL filename including subfolder (e.g. "sentinel-fast-video/t2v_FAST_512p_1s_wan2.2-14B.json")
  - If user wants > 5 seconds, prefer 06 (chained FLF, longest) or 11 (single-pass long)
  - For "make a photo of X" — pick a PHOTO workflow, never a video one
  - When unsure between Wan and LTX: Wan = better humans, LTX = faster + longer
  - Don't invent workflow names

When the user just asks a question (not a render), answer normally without a render block."""

RENDER_BLOCK = re.compile(r"```render\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_plan(text: str):
    m = RENDER_BLOCK.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _strip_render_block(text: str) -> str:
    return RENDER_BLOCK.sub("", text).strip()


_VLLM_TIERS = {
    "vllm":          "http://127.0.0.1:8001/v1",
    "vllm-medium":   "http://127.0.0.1:8002/v1",
    "vllm-creative": "http://127.0.0.1:8003/v1",
}


def _vllm_tier_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False


def _vllm_model_name(base_url: str) -> str | None:
    """Query a running vLLM tier for its actual served model id."""
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=2) as r:
            data = json.load(r).get("data", [])
            return data[0]["id"] if data else None
    except Exception:
        return None


def _llm_reply(user_text: str, provider: str | None = None):
    # Group catalog by category so the LLM can scan it quickly
    cat = CATALOG()
    by_cat: dict[str, list[str]] = {}
    for fname, info in cat.items():
        by_cat.setdefault(info["category"], []).append(f"{fname} — {info['tagline']}")
    sections = []
    for category in ("photo", "edit-photo", "upscale-image", "video", "long-video",
                     "video-format", "audio→video", "upscale-video", "interpolate", "other"):
        items = by_cat.get(category) or []
        if not items:
            continue
        sections.append(f"\n[{category.upper()}]\n  " + "\n  ".join(items))
    catalog_str = "".join(sections)
    full_user = f"\nAVAILABLE WORKFLOWS:{catalog_str}\n\nUSER: {user_text}"
    try:
        from llm_client import LLMClient

        # Pass model EXPLICITLY per-provider so a stale LLM_MODEL env var
        # (e.g. from ~/.env left over from another project) can't pollute.
        if provider in _VLLM_TIERS:
            base = _VLLM_TIERS[provider]
            os.environ["VLLM_BASE_URL"] = base
            client = LLMClient(provider="vllm", model=_vllm_model_name(base))
        elif provider == "deepseek":
            client = LLMClient(provider="deepseek", model="deepseek-chat")
        else:
            base = _VLLM_TIERS["vllm"]
            os.environ["VLLM_BASE_URL"] = base
            client = LLMClient(provider="vllm", model=_vllm_model_name(base))

        r = client.complete(full_user, system=SYSTEM_PROMPT,
                            max_tokens=900, temperature=0.3)

        # auto-fallback to DeepSeek if vLLM fails and key is set
        if r.error and (provider or "vllm").startswith("vllm") and os.environ.get("DEEPSEEK_API_KEY"):
            try:
                fb = LLMClient(provider="deepseek", model="deepseek-chat")
                r = fb.complete(full_user, system=SYSTEM_PROMPT,
                                max_tokens=900, temperature=0.3)
                if not r.error:
                    plan = _extract_plan(r.text)
                    return {
                        "reply": _strip_render_block(r.text) if plan else r.text,
                        "plan": plan,
                        "error": None,
                        "fallback": "deepseek",
                    }
            except Exception:
                pass

        if r.error:
            return {"reply": "", "plan": None, "error": f"LLM: {r.error}"}
        plan = _extract_plan(r.text)
        return {
            "reply": _strip_render_block(r.text) if plan else r.text,
            "plan": plan,
            "error": None,
        }
    except Exception as e:
        return {"reply": "", "plan": None, "error": str(e)}


# ── routes registered on ComfyUI's PromptServer ────────────────────
@PromptServer.instance.routes.get("/conjurer/status")
async def status(_request):
    tiers = {k: _vllm_tier_alive(v) for k, v in _VLLM_TIERS.items()}
    cat = CATALOG()
    return web.json_response({
        "vllm_tiers":   tiers,
        "deepseek_key": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "workflows":    sorted(cat.keys()),
        "catalog":      cat,
    })


@PromptServer.instance.routes.post("/conjurer/chat")
async def chat(request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    provider = body.get("provider") or None
    if not text:
        return web.json_response({"error": "no text"}, status=400)
    return web.json_response(_llm_reply(text, provider))


@PromptServer.instance.routes.get("/conjurer/debug")
async def debug(_request):
    """Diagnostic — show what the chat path would actually send."""
    import sys as _sys
    info = {
        "env_LLM_MODEL":     os.environ.get("LLM_MODEL", "(unset)"),
        "env_LLM_PROVIDER":  os.environ.get("LLM_PROVIDER", "(unset)"),
        "env_VLLM_BASE_URL": os.environ.get("VLLM_BASE_URL", "(unset)"),
        "env_DEEPSEEK_API_KEY_set": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "sys_path_head":     _sys.path[:3],
    }
    try:
        from llm_client import LLMClient, _OPENAI_COMPAT
        info["llm_client_file"] = LLMClient.__module__
        c = LLMClient(provider="deepseek")
        info["client_provider"] = c.provider
        info["client_model"]    = c.model
        info["deepseek_default_model"] = _OPENAI_COMPAT["deepseek"]["default_model"]
        info["effective_model"] = c.model or _OPENAI_COMPAT["deepseek"]["default_model"]
    except Exception as e:
        info["error"] = repr(e)
    return web.json_response(info)


@PromptServer.instance.routes.post("/conjurer/debug-graph")
async def debug_graph(request):
    """Diagnose problems with a workflow graph + recent error.

    POST body: { graph: <UI-format JSON>, error: "<error text>", provider?, hint? }

    Returns: { reply: <markdown analysis>, suggestions: [...], error: None }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad json"}, status=400)

    graph = body.get("graph")
    error_text = (body.get("error") or "").strip()
    user_hint = (body.get("hint") or "").strip()
    provider = body.get("provider") or None

    if not graph and not error_text:
        return web.json_response(
            {"error": "need at least one of {graph, error}"}, status=400)

    # Compact the graph: keep only what an LLM needs to reason about.
    summary_lines = []
    if isinstance(graph, dict):
        nodes = graph.get("nodes") or []
        for n in nodes[:80]:  # cap context size
            t = n.get("type") or "?"
            wid = n.get("id")
            wv = n.get("widgets_values") or []
            wv_str = ", ".join(str(v)[:60] for v in wv[:3]) if wv else ""
            summary_lines.append(f"  #{wid} {t}" + (f"  [{wv_str}]" if wv_str else ""))
        summary_lines.append(f"  ({len(nodes)} nodes total)")
    graph_summary = "\n".join(summary_lines) if summary_lines else "(no graph supplied)"

    DEBUG_SYSTEM = """You are a ComfyUI debug assistant. The user has a
broken or misbehaving workflow. They've given you the graph and the error.

Your job:
  1. Identify the most likely root cause in ONE concise paragraph.
  2. List 1-3 SPECIFIC fixes — which node to change, what value to set, or
     which model is missing. Be concrete (filenames, parameter names).
  3. If a fix needs a model file the user might not have, name the model.

Be terse. Markdown bullet points are fine. Don't speculate about ten possibilities."""

    user_msg = f"""GRAPH SUMMARY ({len(summary_lines)} entries):
{graph_summary}

ERROR / SYMPTOM:
{error_text or '(none provided)'}

USER NOTE:
{user_hint or '(none)'}"""

    try:
        from llm_client import LLMClient
        # Use whichever provider the chat is using; default to deepseek (better at code/JSON)
        if provider == "deepseek" or not provider:
            client = LLMClient(provider="deepseek", model="deepseek-chat")
        elif provider in _VLLM_TIERS:
            base = _VLLM_TIERS[provider]
            os.environ["VLLM_BASE_URL"] = base
            client = LLMClient(provider="vllm", model=_vllm_model_name(base))
        else:
            client = LLMClient(provider="deepseek", model="deepseek-chat")
        r = client.complete(user_msg, system=DEBUG_SYSTEM,
                            max_tokens=600, temperature=0.2)
        if r.error:
            return web.json_response({"reply": "", "error": f"LLM: {r.error}"})
        return web.json_response({"reply": r.text, "error": None})
    except Exception as e:
        return web.json_response({"reply": "", "error": str(e)})


@PromptServer.instance.routes.get("/conjurer/nodes")
async def list_nodes(request):
    """Search ComfyUI's available node classes. ?q=keyword filters by name.

    Returns a slim list — just node names + brief input/output summary.
    """
    q = (request.query.get("q") or "").lower()
    try:
        # Tap into ComfyUI's own object_info via internal API
        import nodes as comfy_nodes
        node_classes = list(comfy_nodes.NODE_CLASS_MAPPINGS.keys())
    except Exception:
        node_classes = []
    if q:
        node_classes = [n for n in node_classes if q in n.lower()]
    return web.json_response({"nodes": sorted(node_classes)[:200],
                              "total": len(node_classes)})


# ── workflow generation FROM SCRATCH ──────────────────────────────
# Curated essential node classes for from-scratch generation. Keeps the LLM
# focused on a manageable schema (~30 nodes vs 3000+).
_GEN_ESSENTIAL_NODES = [
    # Loading
    "CheckpointLoaderSimple", "UNETLoader", "VAELoader", "CLIPLoader",
    "DualCLIPLoader", "LoraLoader", "LoraLoaderModelOnly", "ControlNetLoader",
    "UpscaleModelLoader", "LoadImage", "LoadImageMask",
    # Conditioning
    "CLIPTextEncode", "ConditioningCombine", "ConditioningConcat",
    "ConditioningAverage", "ConditioningSetTimestepRange",
    "ControlNetApplyAdvanced", "FluxGuidance",
    # Latents
    "EmptyLatentImage", "EmptyHunyuanLatentVideo", "EmptyLTXVLatentVideo",
    "EmptySD3LatentImage", "VAEEncode", "VAEDecode", "RepeatLatentBatch",
    # Sampling
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "BasicGuider",
    "BasicScheduler", "RandomNoise", "ModelSamplingSD3", "ModelSamplingFlux",
    # Image ops
    "ImageScale", "ImageScaleBy", "ImageUpscaleWithModel", "ImageBatch",
    "PreviewImage", "SaveImage", "SaveAnimatedWEBP",
    # Video-specific (Wan family)
    "WanImageToVideo", "WanFirstLastFrameToVideo",
    # Video output (VHS = VideoHelperSuite custom_node — common)
    "VHS_VideoCombine", "VHS_LoadVideo",
    # Common control / preprocess
    "PreviewImage",
]


def _slim_input_spec(spec):
    """Normalize one INPUT_TYPES spec value to compact form.
    spec is typically (type_name,) | (type_name, options_dict) |
    a list of choices (file dropdown) | a list of choices + dict."""
    if isinstance(spec, tuple) or isinstance(spec, list):
        if not spec:
            return ["?"]
        t = spec[0]
        if isinstance(t, list) or isinstance(t, tuple):
            # Enumerated dropdown — collapse to a placeholder
            sample = t[0] if t else ""
            if isinstance(sample, str) and "." in sample:
                return ["<filename>"]
            return ["<choice>"]
        return [str(t)]
    return [str(spec)]


def _digest_object_info(node_names: list[str]) -> dict:
    """Compact schema for given nodes. Reads in-process (no HTTP)
    to avoid event-loop deadlock when called from inside aiohttp."""
    try:
        import nodes as comfy_nodes
        mappings = comfy_nodes.NODE_CLASS_MAPPINGS
    except Exception as e:
        return {"_error": f"NODE_CLASS_MAPPINGS unavailable: {e}"}

    out = {}
    for name in node_names:
        cls = mappings.get(name)
        if cls is None:
            continue
        try:
            it = cls.INPUT_TYPES()
        except Exception as e:
            out[name] = {"_error": f"INPUT_TYPES: {e}"}
            continue
        slim = {"required": {}, "optional": {}, "outputs": list(getattr(cls, "RETURN_TYPES", ()))}
        for k, v in (it.get("required") or {}).items():
            slim["required"][k] = _slim_input_spec(v)
        for k, v in list((it.get("optional") or {}).items())[:6]:
            slim["optional"][k] = _slim_input_spec(v)
        out[name] = slim
    return out


# Two canonical API-format examples — small, well-formed, used as in-context
# learning for the LLM. These are the SHAPE it should imitate.
_GEN_EXAMPLE_TXT2IMG = {
    "3":  {"class_type": "KSampler",
           "inputs": {"seed": 42, "steps": 20, "cfg": 8.0, "sampler_name": "euler",
                      "scheduler": "normal", "denoise": 1.0,
                      "model": ["4", 0], "positive": ["6", 0],
                      "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4":  {"class_type": "CheckpointLoaderSimple",
           "inputs": {"ckpt_name": "<USER_PROVIDED>"}},
    "5":  {"class_type": "EmptyLatentImage",
           "inputs": {"width": 512, "height": 512, "batch_size": 1}},
    "6":  {"class_type": "CLIPTextEncode",
           "inputs": {"text": "<USER_POSITIVE>", "clip": ["4", 1]}},
    "7":  {"class_type": "CLIPTextEncode",
           "inputs": {"text": "<USER_NEGATIVE>", "clip": ["4", 1]}},
    "8":  {"class_type": "VAEDecode",
           "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9":  {"class_type": "SaveImage",
           "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]}},
}


_GEN_SYSTEM = """You compose ComfyUI workflows in API format from natural-language descriptions.

Output rules — read carefully:
  • Output ONE fenced JSON code block, format: ```json\\n{...}\\n```
  • The JSON is a flat dict: {"<node_id_str>": {"class_type": "<NodeClass>", "inputs": {...}}}
  • Each connection is a 2-element array: [<source_node_id_str>, <output_slot_int>]
  • class_type MUST be from the SCHEMA provided. Don't invent.
  • For file inputs (ckpt_name, lora_name, etc.) leave value "<USER_PROVIDED>" — the user picks afterwards.
  • For prompts, use "<USER_POSITIVE>" and "<USER_NEGATIVE>" placeholders.
  • Use small integer string IDs starting from "1".
  • Always end with a SaveImage or VHS_VideoCombine or SaveAnimatedWEBP node.

After the JSON block, write 2-3 sentences explaining what you built and what the user
needs to fill in (which models, prompts, etc.).

If the request is too complex (needs nodes outside the schema, or deep multi-stage
pipelines), say so honestly and suggest the user pick from the existing template
catalog instead — DO NOT produce broken JSON to satisfy the request."""


_GEN_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _autofill_defaults(workflow: dict) -> int:
    """For any missing required input that has a default in INPUT_TYPES,
    fill it in. Returns count of fills. This rescues LLM output that forgot
    widget values (common for VHS_VideoCombine, SaveAnimatedWEBP, etc.)."""
    try:
        import nodes as comfy_nodes
        mappings = comfy_nodes.NODE_CLASS_MAPPINGS
    except Exception:
        return 0

    fills = 0
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        cls = mappings.get(ct)
        if cls is None:
            continue
        try:
            it = cls.INPUT_TYPES().get("required") or {}
        except Exception:
            continue
        inp = node.setdefault("inputs", {})
        for k, spec in it.items():
            if k in inp:
                continue
            # spec is e.g. ("INT", {"default": 24, ...}) or [list of choices]
            if isinstance(spec, (list, tuple)) and len(spec) >= 2 and isinstance(spec[1], dict):
                if "default" in spec[1]:
                    inp[k] = spec[1]["default"]
                    fills += 1
                elif spec[0] == "BOOLEAN":
                    inp[k] = False; fills += 1
                elif spec[0] == "INT":
                    inp[k] = 0; fills += 1
                elif spec[0] == "FLOAT":
                    inp[k] = 0.0; fills += 1
                elif spec[0] == "STRING":
                    inp[k] = ""; fills += 1
            elif isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
                # enumerated choice list — pick first option
                if spec[0]:
                    inp[k] = spec[0][0]
                    fills += 1
    return fills


def _validate_generated(workflow: dict, allowed_classes: set[str]) -> list[str]:
    """Return a list of validation errors (empty if all good).

    Checks: class_type exists, all required inputs are present (either as
    literal value or as a [src, slot] connection), connection targets exist."""
    errs = []
    if not isinstance(workflow, dict):
        return ["workflow must be a dict"]

    # We need INPUT_TYPES to know what's required per class
    try:
        import nodes as comfy_nodes
        mappings = comfy_nodes.NODE_CLASS_MAPPINGS
    except Exception:
        mappings = {}

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errs.append(f"node {node_id} is not a dict")
            continue
        ct = node.get("class_type")
        if not ct:
            errs.append(f"node {node_id} missing class_type")
            continue
        if ct not in allowed_classes:
            errs.append(f"node {node_id}: unknown class_type {ct!r}")
            continue

        inp = node.get("inputs", {})
        if not isinstance(inp, dict):
            errs.append(f"node {node_id}: inputs not a dict")
            continue

        # Check connection targets exist
        for k, v in inp.items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                if v[0] not in workflow:
                    errs.append(f"node {node_id}.{k}: connection to nonexistent node {v[0]!r}")

        # Check required inputs are present
        cls = mappings.get(ct)
        if cls is not None:
            try:
                required = (cls.INPUT_TYPES().get("required") or {}).keys()
                for req_k in required:
                    if req_k not in inp:
                        errs.append(f"node {node_id} ({ct}): missing required input {req_k!r}")
            except Exception:
                pass
    return errs


@PromptServer.instance.routes.post("/conjurer/generate")
async def generate_workflow(request):
    """Generate a ComfyUI workflow from a natural-language description.

    POST body: { description: "...", provider?: "deepseek|vllm|..." }
    Returns: { workflow: {...} | None,
               explanation: "...",
               validation_errors: [...],
               error: None | "<msg>" }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad json"}, status=400)

    description = (body.get("description") or "").strip()
    if not description:
        return web.json_response({"error": "missing description"}, status=400)
    provider = body.get("provider") or "deepseek"

    # 1. Build compact schema
    schema = _digest_object_info(_GEN_ESSENTIAL_NODES)
    schema_str = json.dumps(schema, indent=1)[:6000]  # cap context

    # 2. Compose user prompt with example + schema + description
    user_prompt = f"""SCHEMA (allowed node classes):
{schema_str}

EXAMPLE (basic SD txt2img workflow in API format):
```json
{json.dumps(_GEN_EXAMPLE_TXT2IMG, indent=1)}
```

USER REQUEST:
{description}"""

    # 3. Call LLM
    try:
        from llm_client import LLMClient
        if provider in _VLLM_TIERS:
            base = _VLLM_TIERS[provider]
            os.environ["VLLM_BASE_URL"] = base
            client = LLMClient(provider="vllm", model=_vllm_model_name(base))
        else:
            client = LLMClient(provider="deepseek", model="deepseek-chat")
        r = client.complete(user_prompt, system=_GEN_SYSTEM,
                            max_tokens=2500, temperature=0.2)
        if r.error:
            return web.json_response({"workflow": None, "error": f"LLM: {r.error}"})
    except Exception as e:
        return web.json_response({"workflow": None, "error": str(e)})

    # 4. Extract JSON block
    m = _GEN_JSON_BLOCK.search(r.text)
    if not m:
        return web.json_response({
            "workflow": None,
            "explanation": r.text,
            "error": "LLM didn't produce a JSON block — see explanation",
        })
    try:
        workflow = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return web.json_response({
            "workflow": None,
            "explanation": r.text,
            "error": f"JSON parse: {e}",
        })

    # 5. Auto-fill defaults the LLM forgot, then validate
    autofills = _autofill_defaults(workflow)
    try:
        import nodes as comfy_nodes
        allowed = set(comfy_nodes.NODE_CLASS_MAPPINGS.keys())
    except Exception:
        allowed = set(_GEN_ESSENTIAL_NODES)
    errs = _validate_generated(workflow, allowed)

    explanation = _GEN_JSON_BLOCK.sub("", r.text).strip()
    if autofills:
        explanation = f"_(Auto-filled {autofills} missing default value(s).)_  \n\n" + explanation

    return web.json_response({
        "workflow": workflow,
        "explanation": explanation,
        "validation_errors": errs,
        "autofills": autofills,
        "error": None if not errs else f"{len(errs)} validation error(s) — see validation_errors",
    })


@PromptServer.instance.routes.get("/conjurer/workflow")
async def workflow_file(request):
    """Returns workflow JSON. Pass ?path=<rel> where rel is relative to
    WORKFLOW_DIR (may include subfolders, e.g. sentinel-fast-video/foo.json)."""
    name = request.query.get("path", "")
    if not name or ".." in name or not name.endswith(".json"):
        return web.Response(status=400, text="bad path")
    path = (WORKFLOW_DIR / name).resolve()
    if not str(path).startswith(str(WORKFLOW_DIR.resolve())):
        return web.Response(status=400, text="path traversal")
    if not path.is_file():
        return web.Response(status=404, text=f"no such workflow: {name}")
    return web.Response(text=path.read_text(), content_type="application/json")


print(f"[conjurer] routes registered: /conjurer/{{status,chat,workflow,debug}}")
print(f"[conjurer] catalog: {len(_build_catalog())} workflows discovered")
