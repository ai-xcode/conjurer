#!/usr/bin/env bash
# ~/comfy-assistant/start.sh [single|dual|gpu1]
#
#   single (default) — vLLM + ComfyUI on GPU 0 (:8188)  ← assistant lives INSIDE
#   dual             — same as single + ALSO ComfyUI on GPU 1 (:8189)
#   gpu1             — vLLM + ComfyUI on GPU 1 (:8189)
#
# The assistant is now a ComfyUI extension (a custom_node), so there is no
# separate Flask process. Open http://127.0.0.1:8188 and click ✨ Conjurer.
#
# Idempotent: re-running is safe. Each step skips if already up.
set -euo pipefail

MODE="${1:-single}"
case "$MODE" in
    single|dual|gpu1) ;;
    *) echo "usage: $0 [single|dual|gpu1]" >&2; exit 2;;
esac

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Load .env (DEEPSEEK_API_KEY) — exported so the ComfyUI process inherits it
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

# Ensure the symlink into ComfyUI's custom_nodes exists
LINK="$HOME/ComfyUI/custom_nodes/conjurer"
if [[ ! -L "$LINK" ]]; then
    echo "[setup] linking extension into ~/ComfyUI/custom_nodes/ ..."
    "$PROJECT_DIR/install.sh"
fi

mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/pids"

http_up() { curl -fsS --max-time 1 "$1" >/dev/null 2>&1; }

wait_for() {
    local url="$1" name="$2" max=${3:-60}
    printf "    waiting for %s" "$name"
    for _ in $(seq 1 "$max"); do
        if http_up "$url"; then printf " ✓\n"; return 0; fi
        printf "."
        sleep 1
    done
    printf " ✗ timeout\n"
    return 1
}

start_comfy_on_gpu() {
    local gpu="$1" port="$2"
    local name="ComfyUI GPU$gpu (:$port)"
    if http_up "http://127.0.0.1:$port/system_stats"; then
        echo "       $name already up"
        return 0
    fi
    echo "       starting $name ..."
    cd "$HOME/ComfyUI"
    CUDA_VISIBLE_DEVICES="$gpu" \
        DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" \
        nohup ./venv/bin/python main.py \
            --listen 0.0.0.0 --port "$port" \
            > "$PROJECT_DIR/logs/comfyui-gpu$gpu.log" 2>&1 &
    echo $! > "$PROJECT_DIR/pids/comfyui-gpu$gpu.pid"
    cd "$PROJECT_DIR"
    wait_for "http://127.0.0.1:$port/system_stats" "$name" 90
}

# ─── 1) vLLM (use any existing tier; only spin up Fast if nothing's there) ──
echo "[1/2] vLLM"
if http_up "http://127.0.0.1:8001/v1/models" \
   || http_up "http://127.0.0.1:8002/v1/models" \
   || http_up "http://127.0.0.1:8003/v1/models"; then
    echo "       at least one tier already up — using it"
elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    echo "       no tier up, but DeepSeek key set → cloud fallback (no vLLM boot)"
elif [[ -x "$HOME/vLLM_Servers/start_qwen_awq.sh" ]]; then
    echo "       starting JUST the Fast tier (Qwen3.5-35B AWQ ~22 GB) ..."
    nohup bash "$HOME/vLLM_Servers/start_qwen_awq.sh" \
        > "$PROJECT_DIR/logs/vllm-fast.log" 2>&1 &
    wait_for "http://127.0.0.1:8001/v1/models" "Fast tier" 180 || \
        echo "    ⚠ Fast tier didn't come up — see $PROJECT_DIR/logs/vllm-fast.log"
else
    echo "    ⚠ no vLLM tier up, no DeepSeek key — chat will fail until one is provided"
fi

# ─── 2) ComfyUI instance(s) per mode ──────────────────────────────────
echo "[2/2] ComfyUI ($MODE mode)"
case "$MODE" in
    single) start_comfy_on_gpu 0 8188 ;;
    dual)   start_comfy_on_gpu 0 8188; start_comfy_on_gpu 1 8189 ;;
    gpu1)   start_comfy_on_gpu 1 8189 ;;
esac

PRIMARY_PORT=8188
[[ "$MODE" == "gpu1" ]] && PRIMARY_PORT=8189

echo
echo "✓ all up — mode: $MODE"
echo "    open:    http://127.0.0.1:$PRIMARY_PORT     (ComfyUI + ✨ Conjurer panel)"
[[ "$MODE" == "dual" ]] && echo "    GPU 1:   http://127.0.0.1:8189     (second ComfyUI)"
echo "    logs:    $PROJECT_DIR/logs/"
echo "    stop:    $PROJECT_DIR/stop.sh [all|gpu0|gpu1]"
