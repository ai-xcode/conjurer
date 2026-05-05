#!/usr/bin/env bash
# ~/comfy-assistant/stop.sh [all|gpu0|gpu1]
#
#   all (default) — kill both ComfyUI instances
#   gpu0          — kill ComfyUI on GPU 0 (port 8188)
#   gpu1          — kill ComfyUI on GPU 1 (port 8189)
#
# vLLM tiers are NEVER touched. Stop them via ~/bin/ai-stop.sh if you want.
set -euo pipefail

MODE="${1:-all}"
case "$MODE" in
    all|gpu0|gpu1) ;;
    *) echo "usage: $0 [all|gpu0|gpu1]" >&2; exit 2;;
esac

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stop_pid() {
    local pidfile="$1" name="$2"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "stopped $name (pid $pid)"
            for _ in 1 2 3; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 1
            done
            kill -9 "$pid" 2>/dev/null || true
        else
            echo "$name was not running"
        fi
        rm -f "$pidfile"
    fi
}

stop_port() {
    local port="$1" label="$2"
    if fuser -s "$port"/tcp 2>/dev/null; then
        fuser -k "$port"/tcp 2>/dev/null && echo "killed $label on port $port"
    fi
}

case "$MODE" in
    all)
        stop_pid "$PROJECT_DIR/pids/comfyui-gpu0.pid"  "ComfyUI GPU 0"
        stop_pid "$PROJECT_DIR/pids/comfyui-gpu1.pid"  "ComfyUI GPU 1"
        stop_port 8188 "ComfyUI GPU 0"
        stop_port 8189 "ComfyUI GPU 1"
        ;;
    gpu0)
        stop_pid "$PROJECT_DIR/pids/comfyui-gpu0.pid" "ComfyUI GPU 0"
        stop_port 8188 "ComfyUI GPU 0"
        ;;
    gpu1)
        stop_pid "$PROJECT_DIR/pids/comfyui-gpu1.pid" "ComfyUI GPU 1"
        stop_port 8189 "ComfyUI GPU 1"
        ;;
esac

echo
echo "(vLLM tiers left running — use ~/bin/ai-stop.sh to stop them too)"
