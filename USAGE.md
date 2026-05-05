# Using Conjurer

A complete walkthrough — opening the panel, every button, real-world scenarios, troubleshooting.

> **Quick install reminder:** see [README.md](./README.md) for cross-platform install. After install + ComfyUI restart, open `http://127.0.0.1:8188` and look for the gradient **✨ Conjurer** button at top-right.

---

## 1. First time — opening the panel

```
ComfyUI's web UI                              ✨ Conjurer  ←  click this
┌───────────────────────────────────────────────────────┐
│  File  Edit  Workflow  Settings        [✨ Conjurer]  │
├───────────────────────────────────────────────────────┤
│                                                       │
│           the canvas where workflows live             │
│                                                       │
└───────────────────────────────────────────────────────┘
```

Click it → a draggable panel slides in from the top-right:

```
┌─ ✨ Conjurer Assistant ──────  [vLLM Fast ▼]  [?] [×] ─┐
│  20 workflows · ✓ all vLLM tiers up                    │
├────────────────────────────────────────────────────────┤
│                                                        │
│    Hi. Tell me what you want to render — I'll pick     │
│    the right workflow, write the prompts, load it      │
│    onto your canvas, and (optionally) queue it.        │
│                                                        │
│                                                        │
├────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────┐                │
│  │ Describe a render…                 │  Send  ✨  🔧  │
│  └────────────────────────────────────┘                │
└────────────────────────────────────────────────────────┘
```

Top to bottom: header (model + help + close), status banner, chat scroll, composer.

---

## 2. The three action buttons

| Button | Color | When you click it | What happens |
|---|---|---|---|
| **Send** | purple | After typing a description | Picks an existing workflow from your library, writes prompts, shows a plan card |
| **✨** | green | After typing a description | Generates a NEW workflow from scratch using node schema + LLM |
| **🔧** | red | (no typing needed) | Captures the current canvas + last error, returns a debug analysis |

The header has two extras:

| Button | What |
|---|---|
| **provider dropdown** | Pick which LLM writes your prompts (vLLM Fast/Med/Crea, DeepSeek, etc.) |
| **?** | Show this guide inline |
| **×** | Hide the panel (button stays at top-right to bring it back) |

---

## 3. The plan card — what to do with it

When you press **Send** and the LLM picks a workflow, you get a card like this:

```
┌─ PROPOSED RENDER ────────────────────────────────────┐
│ workflow:    t2v_FAST_512p_1s_wan2.2-14B.json        │
│ positive:    A cinematic family at golden hour…      │
│ negative:    low quality, blurry, distorted          │
│ why:         Realistic humans, hero snippet          │
├──────────────────────────────────────────────────────┤
│  [Load to canvas]  [Load + Queue]  [↓ JSON]  [Skip]  │
└──────────────────────────────────────────────────────┘
```

| Action | What it does |
|---|---|
| **Load to canvas** | Drops the workflow on the canvas. Auto-fills positive/negative prompts. You hit ComfyUI's own "Queue Prompt" when ready. Best for review-first. |
| **Load + Queue** | Loads + queues immediately. One-click render. |
| **↓ JSON** | Downloads the workflow's JSON to your computer. Useful for sharing, backup, or feeding into another tool. |
| **Skip** | Dismisses the card. Keep chatting. |

---

## 4. Real scenarios — what to type

Each scenario shows the prompt + which workflow gets picked.

### 4.1 — Photo from text (text-to-image)

| You type | Conjurer picks |
|---|---|
| `"a photo of a sunset over mountains, cinematic"` | `01_text-to-image_qwen_FAST` |
| `"professional headshot of a CEO, studio lighting"` | `27_PORTRAIT-STUDIO-allinone_qwen_FAST` |
| `"FLUX text-to-image, anime style, 1024x1024"` | (will pick a FLUX-based workflow) |

### 4.2 — Animate an image (image-to-video)

> Tip: load your input image first via ComfyUI's "Load Image" node OR mention it in the request.

| You type | Conjurer picks |
|---|---|
| `"animate this still photo of a beach"` | `i2v_MED_512p_2s_wan2.1-14B` |
| `"5 second video from this portrait, slow zoom"` | `i2v_FAST_640p_3s_wan2.2-14B-lightning` |
| `"morph from frame A to frame B"` | `flf_MED_512p_1s_wan2.2-14B` (first-last-frame) |

### 4.3 — Pure text-to-video

| You type | Conjurer picks |
|---|---|
| `"5 second cinematic family at golden hour"` | `t2v_FAST_512p_1s_wan2.2-14B` |
| `"abstract finance editorial, cream and gold"` | `t2v_FAST_768p_5s_ltx-video-2b` |
| `"30 second video of a city at night, neon"` | `06_long-video-chain_wan22-flf_MED` (long via chained FLF) |

### 4.4 — Editing photos

| You type | Workflow |
|---|---|
| `"color grade this like a Nikon Z9 cinematic"` | `13_color-grade-nikon-z9` |
| `"sharpen this photo"` | `14_clarity-and-sharpness` |
| `"remove the person in the background"` | `15_remove-objects` |
| `"extend this image to 16:9 panorama"` | `16_extend-image` |
| `"swap the background to a beach"` | `17_swap-background` |

### 4.5 — Upscaling / interpolation

| You type | Workflow |
|---|---|
| `"upscale this video 2x"` | `08_upscale-video_realesrgan` |
| `"smooth this clip to 60 fps"` | `09_smooth-fps_film` |
| `"upscale this photo 4x"` | `10_upscale-image_realesrgan` |

### 4.6 — Special formats (cinematic / reels / ads)

| You type | Workflow |
|---|---|
| `"vertical reel for Instagram"` | `24_SOCIAL-REEL-vertical` |
| `"cinematic short, film aesthetic"` | `25_CINEMATIC-SHORT-film` |
| `"ad-maker style, glossy product shot"` | `23_AD-MAKER-cinematic` |
| `"product showcase, 360 rotation"` | `26_PRODUCT-SHOWCASE` |

### 4.7 — Audio → video (lipsync)

| You type | Workflow |
|---|---|
| `"lipsync this audio file to a face"` | `05_lipsync-from-audio_wan22-s2v` |

### 4.8 — Q&A (no render, just info)

Conjurer answers in plain English without producing a render plan:

- `"what does CLIPTextEncode do?"` → explains the node
- `"find me a node for face swap"` → searches `/object_info` for face-swap-related node classes
- `"what's the difference between Wan 2.1 and Wan 2.2?"` → answers from LLM knowledge
- `"how do I make a person dance from a reference video?"` → finds the dance / motion-transfer workflows in your catalog

---

## 5. The ✨ Generate button — when picking isn't enough

If no existing workflow fits — or you want a custom architecture — type a description and hit ✨ instead of Send.

Example requests it handles well:

```
✓  "a basic SD txt2img workflow at 768x768 with 25 steps"
✓  "FLUX text-to-image, 1024x1024, 28 steps"
✓  "SD with one LoRA at strength 0.8, output 1024x768"
✓  "upscale an input image 2x using a model"
✓  "Wan 2.2 t2v at 512x512 with 17 frames, animated webp output"
```

Edge of the envelope (sometimes works, sometimes needs you to pick from catalog instead):

```
~  "Wan video then 2x upscale then 60 fps interpolation in one workflow"
~  "ControlNet pose + IPAdapter face + LoRA + SDXL refiner"
~  "AnimateDiff with 4 keyframes and motion module"
```

When ✨ Generate fails (hallucinated nodes, missing connections), Conjurer will say so honestly and suggest the catalog instead — it never returns a broken graph.

---

## 6. The 🔧 Debug button — fixing broken renders

When a render errors out:

1. Don't close the workflow.
2. Open Conjurer (✨ button if hidden).
3. Click 🔧 (red, in the composer row).

Conjurer will:
- Capture the current canvas via `app.graph.serialize()`
- Pull the most recent error from ComfyUI's `/history` endpoint
- Send both to the LLM for analysis
- Reply with **root cause + 1–3 specific fixes**

Example debug response:

```
Root Cause:
The CheckpointLoaderSimple node references "nonexistent.safetensors"
which isn't in your models/checkpoints/ folder.

Fixes:
1. Click the CheckpointLoader node. Replace ckpt_name with one you have
   (try v1-5-pruned-emaonly.safetensors or sd_xl_base_1.0.safetensors).
2. Or: download the model and place it in ~/ComfyUI/models/checkpoints/
3. After fixing, re-queue with the same Conjurer prompt.
```

---

## 7. Provider dropdown — which LLM to use

In the panel header. Lists what's reachable on your machine + cloud fallbacks if you set keys:

| Option | Where it goes | Cost |
|---|---|---|
| **vLLM Fast** | `http://127.0.0.1:8001/v1` | $0 (local) |
| **vLLM Med** | `http://127.0.0.1:8002/v1` | $0 (local) |
| **vLLM Crea** | `http://127.0.0.1:8003/v1` | $0 (local) |
| **DeepSeek** | `https://api.deepseek.com/v1` | ~$0.004/request |

Tiers showing `[off]` aren't running. Conjurer auto-falls-back to DeepSeek if a vLLM tier you picked is offline (when `DEEPSEEK_API_KEY` is set).

To add Ollama, LM Studio, OpenAI, Grok, etc. — just put their key/URL in `.env`. They'll appear in the dropdown automatically.

---

## 8. Why longer videos take much longer (and how to speed them up)

You may notice: a 1-second video renders in ~10 seconds, but a 5-second
video takes 5+ minutes. **This isn't Conjurer being slow — it's how
diffusion video models work.**

### The math

Each video frame is generated by running ~4-30 denoising steps through a
~14 GB UNet. The KSampler runs **all frames per step**, so render time
scales roughly **linearly with frame count** and **quadratically with
resolution**:

| Workflow | Frames | Resolution | Typical time on RTX 6000 Blackwell |
|---|---|---|---|
| `t2v_FAST_512p_1s_wan2.2-14B` (4-step LoRA) | 17 | 512² | **~10 sec** ⚡ |
| `t2v_FAST_512p_1s_wan2.2-14B` longer (81 frames) | 81 | 512² | ~50 sec |
| `t2v_FAST_768p_5s_ltx-video-2b` | ~120 | 768² | ~30 sec |
| `wan2.2_text-to-video_baseline` | 81 | 720² | ~3-5 min |
| `11_text-to-video-long_wan22_SLOW` | 121+ | 720² | ~10-15 min |
| `06_long-video-chain_wan22-flf_MED` (chained 30s) | many | varies | ~30-60 min |

### How to make longer videos faster

In rough order of speedup:

1. **Use the LightX2V LoRA on BOTH stages** — the `wan2.2-14B-lightning`
   workflows include this. It drops sampling steps from 30+ to just 4 with
   minimal quality loss. Already in some starter workflows; ask Conjurer for
   *"Wan 2.2 with Lightning LoRA"*.

2. **Switch to LTX-Video for longer clips** — `t2v_FAST_768p_5s_ltx-video-2b`
   does 5 seconds in ~30 seconds. Wan is better for human realism; LTX is
   ~5× faster for everything else.

3. **Render low-res then upscale** — render at 480p (3-4× faster than
   720p), then run the result through `08_upscale-video_realesrgan_MED`.
   Final quality is often indistinguishable from native 720p.

4. **TorchCompile + TeaCache** — these custom nodes (already installed
   via WanVideoWrapper) compile the UNet on first use (~60 s one-time)
   then run ~1.5-2× faster every render after. TeaCache skips redundant
   attention layers for ~1.4× more. Ask Conjurer for
   *"Wan 2.2 with TorchCompile and TeaCache"* to get a workflow that
   includes them.

5. **Drop frame count** — Wan 2.2 visually peaks at 17 frames @ 16fps
   (~1 sec). Going to 81 frames doesn't make a "5×-better" video; the
   model wasn't trained for that. **For ≥ 5 seconds, use chaining** (next).

6. **Chain short clips with FLF** — `06_long-video-chain_wan22-flf_MED`
   generates clip 1 → uses its last frame as the first frame of clip 2 →
   etc. You can render 30 seconds of seamless video as 6 × 5-second
   passes. Total time: 6× a single 5-sec render, but much higher coherence
   than one slow long-pass.

### What this means for the "long video" prompt

If you ask Conjurer for a 30-second video, it picks
`06_long-video-chain_wan22-flf_MED` (chained FLF). That workflow is
**designed** to take 30-60 minutes — it's running 6 separate diffusion
passes back-to-back. There's no faster way to get coherent 30-second
video from current open-source models.

**Bottom line:** if you need fast iteration, render 1-second @ 512p as
drafts, lock the prompt, then run a single longer render at the end.

## 9. Troubleshooting

### Panel doesn't appear / no ✨ Conjurer button at top-right

```bash
# 1. Did the install actually run?
ls -la ~/ComfyUI/custom_nodes/conjurer       # should be a symlink (Linux/Mac) or junction (Windows)

# 2. Did ComfyUI load it? Check the startup log.
grep -i conjurer ~/ComfyUI/user/comfyui.log
# Should see: [conjurer] routes registered: /conjurer/{status,chat,workflow,debug}

# 3. Hard-refresh your browser
# Ctrl+Shift+R (Linux/Win) or Cmd+Shift+R (Mac)
```

### Status banner says "✗ no LLM"

You haven't set any provider yet. Edit `~/conjurer/.env`, paste your DeepSeek key (or any other provider key/URL), then refresh the browser.

### Panel says "vLLM offline · DeepSeek fallback"

A local vLLM tier you wanted is down. Either:
- Start it (`~/bin/ai-start.sh` if you have JARVIS), or
- Just use DeepSeek (the dropdown will switch automatically).

### "Load to canvas" doesn't fill the prompt nodes

The auto-fill looks for `CLIPTextEncode` nodes (SD/SDXL/FLUX standard). For Qwen image workflows it uses different node classes — your prompts will arrive in chat but you'll paste them manually into the visible text area. Future versions will handle Qwen prompt nodes too.

### The Generate (✨) button returns "validation errors"

LLM produced a graph with missing required inputs. Conjurer's auto-fill rescues most of these by reading INPUT_TYPES defaults; what's left is shown as errors. **Look at the loaded canvas** — the missing fields will be empty in their nodes. Fill them and queue.

### "JSON parse error" in Generate

The LLM's response wasn't well-formed JSON. Click ✨ again — for a slightly different phrasing of your request, the model usually gets it right on the second try. If it keeps failing, switch the dropdown to **DeepSeek** (best at structured JSON) and retry.

---

## 9. Privacy & costs

| What | Where it runs | What leaves your machine |
|---|---|---|
| The chat panel UI | your browser | nothing |
| Conjurer's HTTP routes | inside ComfyUI's process | nothing |
| Workflow execution | ComfyUI on your hardware | nothing |
| LLM call (vLLM/Ollama/LM Studio) | your machine | nothing |
| LLM call (DeepSeek/OpenAI/etc.) | your machine → provider's API over HTTPS | the prompt + workflow catalog list |

There is no Conjurer-operated server. Every request goes directly from your machine to the LLM provider you chose. Your DeepSeek key never leaves `.env`.

**Today: nothing hosted by us.** A future opt-in *Conjurer Cloud* tier (50-call free trial → BYO key) is on the [roadmap](./README.md#roadmap), not active yet.

---

## 10. Contributing workflows back

If you build a great workflow you'd like bundled with future Conjurer installs:

1. Drop the JSON into `workflows/starter/<NN_kebab-case-name>.json` (use the next number).
2. Strip your local model paths — replace with `<replace-with-your-checkpoint.safetensors>` placeholders.
3. Open a PR at <https://github.com/ai-xcode/conjurer>.

Workflows accepted into the starter pack ship with the next release and reach every new install via ComfyUI Manager.
