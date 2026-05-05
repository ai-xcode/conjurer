// Conjurer — chat panel injected into ComfyUI itself.
// Loaded automatically by ComfyUI because the parent __init__.py declares
// WEB_DIRECTORY = "./web". Lives at /extensions/conjurer/...

import { app } from "../../scripts/app.js";

const RENDER_BLOCK = /```render\s*(\{[\s\S]*?\})\s*```/;

// ── small DOM helpers (no innerHTML for dynamic data) ─────────────
function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
}
function span(cls, text) { return el("span", cls, text); }

// ── styles for the panel ──────────────────────────────────────────
const STYLE = `
.conjurer-panel {
    position: fixed; top: 60px; right: 16px; width: 380px; max-height: calc(100vh - 100px);
    background: rgba(20, 20, 28, 0.96); color: #eee; border: 1px solid #444;
    border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); z-index: 9999;
    display: flex; flex-direction: column; font: 13px/1.4 system-ui, sans-serif;
}
.conjurer-panel.hidden { display: none; }
.conjurer-header {
    padding: 10px 12px; background: linear-gradient(90deg, #7c3aed, #ec4899);
    border-radius: 10px 10px 0 0; display: flex; justify-content: space-between;
    align-items: center; cursor: move; user-select: none;
}
.conjurer-header h3 { margin: 0; font-size: 13px; font-weight: 600; }
.conjurer-controls { display: flex; gap: 6px; align-items: center; font-size: 11px; }
.conjurer-controls select {
    background: rgba(255,255,255,0.15); color: #fff; border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px; padding: 2px 4px; font-size: 11px;
}
.conjurer-status { padding: 6px 12px; font-size: 11px; color: #aaa; border-bottom: 1px solid #333; }
.conjurer-status.ok { color: #6ee7b7; }
.conjurer-status.bad { color: #fca5a5; }
.conjurer-chat {
    flex: 1; overflow-y: auto; padding: 10px 12px;
    display: flex; flex-direction: column; gap: 8px; min-height: 200px; max-height: 50vh;
}
.conjurer-bubble { padding: 8px 10px; border-radius: 8px; max-width: 95%; word-wrap: break-word; }
.conjurer-bubble.user   { align-self: flex-end; background: #2563eb; color: #fff; }
.conjurer-bubble.assist { align-self: flex-start; background: #2a2a35; color: #eee; }
.conjurer-bubble.system { align-self: flex-start; background: #1e293b; color: #94a3b8; font-style: italic; }
.conjurer-bubble.error  { align-self: flex-start; background: #4c1d1d; color: #fca5a5; }
.conjurer-plan {
    background: #1a1a25; border: 1px solid #444; border-radius: 6px;
    padding: 10px; margin-top: 6px; font-size: 12px;
}
.conjurer-plan h4 { margin: 0 0 6px 0; font-size: 11px; color: #ec4899; text-transform: uppercase; letter-spacing: 0.5px; }
.conjurer-plan dt { font-weight: 600; color: #aaa; margin-top: 4px; }
.conjurer-plan dd { margin: 2px 0 0 0; color: #ddd; font-family: monospace; font-size: 11px; }
.conjurer-plan-actions { display: flex; gap: 6px; margin-top: 10px; }
.conjurer-plan-actions button {
    flex: 1; padding: 6px 10px; border-radius: 5px; border: none; cursor: pointer;
    font-size: 12px; font-weight: 600;
}
.conjurer-btn-load { background: #7c3aed; color: #fff; }
.conjurer-btn-loadqueue { background: #ec4899; color: #fff; }
.conjurer-btn-cancel { background: #444; color: #ccc; }
.conjurer-composer { padding: 10px; border-top: 1px solid #333; display: flex; gap: 6px; }
.conjurer-composer textarea {
    flex: 1; min-height: 50px; max-height: 120px; resize: vertical;
    background: #1a1a25; color: #eee; border: 1px solid #444; border-radius: 5px;
    padding: 6px 8px; font: 13px system-ui, sans-serif;
}
.conjurer-composer button {
    padding: 0 14px; background: #7c3aed; color: #fff; border: none; border-radius: 5px;
    cursor: pointer; font-weight: 600;
}
.conjurer-composer button:disabled { opacity: 0.5; cursor: wait; }
.conjurer-toggle {
    position: fixed; top: 12px; right: 16px; z-index: 9998;
    background: linear-gradient(90deg, #7c3aed, #ec4899); color: #fff;
    border: none; border-radius: 18px; padding: 6px 14px; cursor: pointer;
    font: 600 12px system-ui, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
`;

function injectStyles() {
    if (document.getElementById("conjurer-style")) return;
    const s = document.createElement("style");
    s.id = "conjurer-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
}

// ── panel state ───────────────────────────────────────────────────
let panel, chat, input, sendBtn, providerSel, statusEl;

function buildPanel() {
    panel = el("div", "conjurer-panel hidden");

    // Header (draggable)
    const header = el("div", "conjurer-header");
    header.appendChild(el("h3", null, "✨ Conjurer Assistant"));
    const controls = el("div", "conjurer-controls");
    providerSel = el("select");
    [
        { v: "vllm",          t: "vLLM Fast" },
        { v: "vllm-medium",   t: "vLLM Med" },
        { v: "vllm-creative", t: "vLLM Crea" },
        { v: "deepseek",      t: "DeepSeek" },
    ].forEach(o => {
        const opt = document.createElement("option");
        opt.value = o.v; opt.textContent = o.t;
        providerSel.appendChild(opt);
    });
    controls.appendChild(providerSel);
    const helpBtn = el("button", null, "?");
    helpBtn.title = "How to use Conjurer";
    helpBtn.style.cssText = "background: transparent; color: #fff; border: 1px solid rgba(255,255,255,0.4); border-radius: 50%; width: 22px; height: 22px; font-size: 12px; cursor: pointer; padding: 0; line-height: 1;";
    helpBtn.onclick = showHelp;
    controls.appendChild(helpBtn);
    const closeBtn = el("button", null, "×");
    closeBtn.style.cssText = "background: transparent; color: #fff; border: none; font-size: 18px; cursor: pointer; padding: 0 4px;";
    closeBtn.onclick = () => panel.classList.add("hidden");
    controls.appendChild(closeBtn);
    header.appendChild(controls);
    panel.appendChild(header);
    makeDraggable(panel, header);

    // Status row
    statusEl = el("div", "conjurer-status", "Loading status…");
    panel.appendChild(statusEl);

    // Chat scroll area
    chat = el("div", "conjurer-chat");
    panel.appendChild(chat);
    addBubble("system",
        "Tell me what you want to render — I'll pick a workflow, write the prompts, " +
        "and load it into the canvas. Examples: \"5-second cinematic family at golden hour\" · " +
        "\"abstract finance editorial, cream and gold\" · \"animate the still I have\"."
    );

    // Composer
    const comp = el("div", "conjurer-composer");
    input = el("textarea");
    input.placeholder = "Describe a render…  (Enter to send, Shift+Enter for newline)";
    input.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });
    sendBtn = el("button", null, "Send");
    sendBtn.onclick = send;
    const genBtn = el("button", null, "✨");
    genBtn.title = "Generate a NEW workflow from scratch — describes intent, builds graph";
    genBtn.style.background = "#10b981";
    genBtn.onclick = generateFromScratch;
    const debugBtn = el("button", null, "🔧");
    debugBtn.title = "Debug current canvas (analyze graph + last error)";
    debugBtn.style.background = "#dc2626";
    debugBtn.onclick = debugCurrent;
    comp.appendChild(input);
    comp.appendChild(sendBtn);
    comp.appendChild(genBtn);
    comp.appendChild(debugBtn);
    panel.appendChild(comp);

    document.body.appendChild(panel);
}

function buildToggle() {
    const btn = el("button", "conjurer-toggle", "✨ Conjurer");
    btn.onclick = () => panel.classList.toggle("hidden");
    document.body.appendChild(btn);
}

function makeDraggable(target, handle) {
    let dx = 0, dy = 0, sx = 0, sy = 0;
    handle.addEventListener("mousedown", e => {
        if (e.target.tagName === "BUTTON" || e.target.tagName === "SELECT") return;
        sx = e.clientX; sy = e.clientY;
        const rect = target.getBoundingClientRect();
        dx = rect.left; dy = rect.top;
        const mv = ev => {
            target.style.left = (dx + ev.clientX - sx) + "px";
            target.style.top  = (dy + ev.clientY - sy) + "px";
            target.style.right = "auto";
        };
        const up = () => {
            document.removeEventListener("mousemove", mv);
            document.removeEventListener("mouseup", up);
        };
        document.addEventListener("mousemove", mv);
        document.addEventListener("mouseup", up);
    });
}

function addBubble(kind, text) {
    const b = el("div", `conjurer-bubble ${kind}`, text);
    chat.appendChild(b);
    chat.scrollTop = chat.scrollHeight;
    return b;
}

function addPlanBubble(plan, replyText) {
    const wrap = el("div", "conjurer-bubble assist");
    if (replyText) {
        const t = el("div");
        t.textContent = replyText;
        wrap.appendChild(t);
    }
    const card = el("div", "conjurer-plan");
    card.appendChild(el("h4", null, "PROPOSED RENDER"));
    const dl = el("dl");
    dl.style.margin = "0";
    [
        ["workflow",  plan.workflow],
        ["positive",  plan.positive_prompt],
        ["negative",  plan.negative_prompt],
        ["why",       plan.rationale],
    ].forEach(([k, v]) => {
        if (!v) return;
        dl.appendChild(el("dt", null, k));
        dl.appendChild(el("dd", null, String(v)));
    });
    card.appendChild(dl);

    const actions = el("div", "conjurer-plan-actions");
    const loadBtn = el("button", "conjurer-btn-load", "Load to canvas");
    loadBtn.onclick = () => loadWorkflow(plan, false);
    const queueBtn = el("button", "conjurer-btn-loadqueue", "Load + Queue");
    queueBtn.onclick = () => loadWorkflow(plan, true);
    const downloadBtn = el("button", "conjurer-btn-download", "↓ JSON");
    downloadBtn.title = "Download this workflow's JSON file";
    downloadBtn.style.background = "#475569";
    downloadBtn.onclick = () => downloadWorkflow(plan);
    const cancelBtn = el("button", "conjurer-btn-cancel", "Skip");
    cancelBtn.onclick = () => actions.remove();
    actions.appendChild(loadBtn);
    actions.appendChild(queueBtn);
    actions.appendChild(downloadBtn);
    actions.appendChild(cancelBtn);
    card.appendChild(actions);

    wrap.appendChild(card);
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
}

// ── refresh status banner ─────────────────────────────────────────
async function refreshStatus() {
    try {
        const r = await fetch("/conjurer/status");
        const j = await r.json();
        const tiers = j.vllm_tiers || {};
        const upTiers = Object.keys(tiers).filter(k => tiers[k]);
        const allTiers = Object.keys(tiers);
        let llmStr;
        if (upTiers.length === allTiers.length) llmStr = "✓ all vLLM tiers up";
        else if (upTiers.length > 0) llmStr = `✓ vLLM ${upTiers.length}/${allTiers.length}`;
        else if (j.deepseek_key) llmStr = "⚠ vLLM offline · DeepSeek fallback";
        else llmStr = "✗ no LLM";
        const wfCount = (j.workflows || []).length;
        statusEl.textContent = `${wfCount} workflows · ${llmStr}`;
        statusEl.className = "conjurer-status " + (upTiers.length || j.deepseek_key ? "ok" : "bad");

        // disable offline tiers in dropdown
        Array.from(providerSel.options).forEach(opt => {
            if (opt.value.startsWith("vllm") && tiers[opt.value] === false) {
                if (!opt.textContent.endsWith("[off]")) opt.textContent += " [off]";
                opt.disabled = true;
            }
            if (opt.value === "deepseek" && !j.deepseek_key) {
                if (!opt.textContent.endsWith("[off]")) opt.textContent += " [off]";
                opt.disabled = true;
            }
        });
        const firstUp = Array.from(providerSel.options).find(o => !o.disabled);
        if (firstUp) providerSel.value = firstUp.value;
    } catch (e) {
        statusEl.textContent = "(status unavailable)";
        statusEl.className = "conjurer-status bad";
    }
}

// ── send chat ─────────────────────────────────────────────────────
async function send() {
    const text = input.value.trim();
    if (!text) return;
    addBubble("user", text);
    input.value = "";
    sendBtn.disabled = true;
    sendBtn.textContent = "…";
    const thinking = addBubble("system", "thinking…");
    try {
        const r = await fetch("/conjurer/chat", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ text, provider: providerSel.value }),
        });
        const j = await r.json();
        thinking.remove();
        if (j.error) {
            addBubble("error", "Error: " + j.error);
        } else if (j.plan) {
            addPlanBubble(j.plan, j.reply);
            if (j.fallback) addBubble("system", `(used ${j.fallback} fallback)`);
        } else {
            addBubble("assist", j.reply || "(empty)");
        }
    } catch (e) {
        thinking.remove();
        addBubble("error", "Network error: " + e.message);
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = "Send";
        input.focus();
    }
}

// ── Help / first-run guide ────────────────────────────────────────
function showHelp() {
    const help = el("div", "conjurer-bubble system");
    help.style.maxWidth = "100%";
    const lines = [
        "✨ Conjurer — quick guide",
        "",
        "• Send (purple)  — picks an EXISTING workflow from your library, fills prompts, loads to canvas.",
        "• ✨ (green)     — generates a NEW workflow from scratch (advanced — uses LLM + node schema).",
        "• 🔧 (red)       — debugs the CURRENT canvas: captures the graph + last error, suggests fixes.",
        "• ? (header)     — this guide.",
        "",
        "What to type:",
        "  \"5 second cinematic family at golden hour\"        → picks Wan video",
        "  \"a photo of a sunset over mountains\"              → picks SD/Qwen txt2img",
        "  \"upscale this image 2x\"                           → picks RealESRGAN",
        "  \"30 second video of a city, night, neon lights\"   → picks chained FLF (long video)",
        "  \"what does CLIPTextEncode do?\"                    → answers from ComfyUI knowledge",
        "  \"find me a workflow for face swap\"                → searches your 293-workflow catalog",
        "",
        "After a plan appears:",
        "  Load to canvas — drops the workflow on the canvas, fills the prompts.",
        "  Load + Queue   — loads + fires Queue Prompt automatically.",
        "  ↓ JSON         — downloads the workflow JSON to your computer (for sharing/backup).",
        "  Skip           — dismiss this plan, keep chatting.",
        "",
        "Provider dropdown (top): pick which LLM writes your prompts.",
        "  Local vLLM tiers (free, private) or DeepSeek cloud ($0.004/request, fallback if vLLM is down).",
    ];
    for (const ln of lines) {
        const p = document.createElement("div");
        p.textContent = ln;
        p.style.fontFamily = ln.startsWith("  ") ? "monospace" : "inherit";
        p.style.fontSize = "12px";
        help.appendChild(p);
    }
    chat.appendChild(help);
    chat.scrollTop = chat.scrollHeight;
}


// ── Download a workflow's JSON ────────────────────────────────────
async function downloadWorkflow(plan) {
    try {
        const r = await fetch(`/conjurer/workflow?path=${encodeURIComponent(plan.workflow)}`);
        if (!r.ok) {
            addBubble("error", `Couldn't fetch ${plan.workflow}: HTTP ${r.status}`);
            return;
        }
        const text = await r.text();
        const blob = new Blob([text], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = plan.workflow.split("/").pop();
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        addBubble("system", `Downloaded ${a.download}`);
    } catch (e) {
        addBubble("error", "Download failed: " + e.message);
    }
}


// ── Generate a new workflow from scratch ──────────────────────────
// Asks /conjurer/generate to compose API-format JSON for the user's intent,
// validates server-side, then loads onto the canvas via app.loadApiJson()
// which is ComfyUI's built-in API-JSON → graph converter.
async function generateFromScratch() {
    const desc = input.value.trim();
    if (!desc) {
        addBubble("system", "Type a description first, e.g. \"a basic SD txt2img workflow at 768×768 with 25 steps\"");
        input.focus();
        return;
    }
    addBubble("user", "✨ Generate: " + desc);
    input.value = "";
    sendBtn.disabled = true;
    const thinking = addBubble("system", "composing graph (this is harder than picking — may take 20s)…");
    try {
        const r = await fetch("/conjurer/generate", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ description: desc, provider: providerSel.value }),
        });
        const j = await r.json();
        thinking.remove();

        if (j.error && !j.workflow) {
            addBubble("error", "Generation failed: " + j.error);
            if (j.explanation) addBubble("assist", j.explanation);
            return;
        }

        if (j.workflow) {
            // Show the explanation
            if (j.explanation) addBubble("assist", j.explanation);

            // Validation issues — warn but still attempt to load
            if (j.validation_errors && j.validation_errors.length) {
                addBubble("error",
                    "⚠ " + j.validation_errors.length +
                    " validation issue(s):\n" + j.validation_errors.slice(0, 5).join("\n"));
            }

            // Load onto the canvas. ComfyUI's app.loadApiJson() converts
            // API format → graph; if not available, fall back to loadGraphData.
            try {
                if (typeof app.loadApiJson === "function") {
                    await app.loadApiJson(j.workflow);
                } else {
                    // Older ComfyUI — best-effort: just load it
                    await app.loadGraphData(j.workflow);
                }
                addBubble("system",
                    `✓ Loaded ${Object.keys(j.workflow).length}-node workflow onto canvas. ` +
                    `Replace any "<USER_PROVIDED>" / "<USER_POSITIVE>" placeholders in the prompt nodes, ` +
                    `then click ComfyUI's Queue Prompt.`);
            } catch (e) {
                addBubble("error", "Loaded JSON but couldn't render graph: " + e.message +
                    ". You can copy the JSON from the explanation above.");
            }
        }
    } catch (e) {
        thinking.remove();
        addBubble("error", "Generate failed: " + e.message);
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}


// ── Debug current canvas: capture graph + last error, ask LLM ─────
async function debugCurrent() {
    addBubble("user", "🔧 Debug current canvas");
    const thinking = addBubble("system", "analyzing graph + recent errors…");
    try {
        // 1. Capture current graph via ComfyUI's serialize API
        const graph = app.graph.serialize();

        // 2. Try to fetch the most recent error from /history
        let errorText = "";
        try {
            const h = await fetch("/history?max_items=5");
            const hist = await h.json();
            const items = Object.values(hist).reverse();
            for (const item of items) {
                const status = item.status || {};
                if (status.status_str === "error" || status.completed === false) {
                    const msgs = (status.messages || []).flat();
                    errorText = msgs.filter(m => typeof m === "string").join("\n").slice(0, 1500);
                    if (errorText) break;
                }
            }
        } catch {}

        const r = await fetch("/conjurer/debug-graph", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                graph,
                error: errorText,
                provider: providerSel.value,
            }),
        });
        const j = await r.json();
        thinking.remove();
        if (j.error) {
            addBubble("error", "Debug failed: " + j.error);
        } else {
            addBubble("assist", j.reply || "(empty analysis)");
        }
    } catch (e) {
        thinking.remove();
        addBubble("error", "Debug error: " + e.message);
    }
}


// ── load workflow into the canvas (UI→API conversion is FREE here) ─
async function loadWorkflow(plan, autoQueue) {
    try {
        const r = await fetch(`/conjurer/workflow?path=${encodeURIComponent(plan.workflow)}`);
        if (!r.ok) {
            addBubble("error", `Couldn't load ${plan.workflow}: HTTP ${r.status}`);
            return;
        }
        const wfJson = await r.json();
        await app.loadGraphData(wfJson);
        addBubble("system", `Loaded "${plan.workflow}" into canvas.`);

        // Auto-fill positive/negative on CLIPTextEncode nodes
        // Convention: first CLIPTextEncode = positive, second = negative
        const clipNodes = app.graph._nodes.filter(n => n.type === "CLIPTextEncode");
        if (clipNodes.length >= 1 && plan.positive_prompt) {
            clipNodes[0].widgets[0].value = plan.positive_prompt;
            clipNodes[0].setDirtyCanvas(true, true);
        }
        if (clipNodes.length >= 2 && plan.negative_prompt) {
            clipNodes[1].widgets[0].value = plan.negative_prompt;
            clipNodes[1].setDirtyCanvas(true, true);
        }
        if (clipNodes.length > 0) {
            addBubble("system",
                `Filled ${Math.min(clipNodes.length, 2)} prompt node(s). ` +
                `Review the canvas, edit if needed.`);
        }
        if (autoQueue) {
            try {
                await app.queuePrompt(0, 1);
                addBubble("system", "Queued. Watch ComfyUI's queue/output area.");
            } catch (e) {
                addBubble("error", "Queue failed: " + e.message);
            }
        }
    } catch (e) {
        addBubble("error", "Load failed: " + e.message);
    }
}

// ── boot ──────────────────────────────────────────────────────────
app.registerExtension({
    name: "Conjurer",
    async setup() {
        injectStyles();
        buildPanel();
        buildToggle();
        await refreshStatus();
        setInterval(refreshStatus, 30_000);
        console.log("[Conjurer] panel ready — click ✨ Conjurer in top-right");
    },
});
