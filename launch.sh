#!/usr/bin/env bash
# launch.sh [start MODE | stop TARGET]
#   Wrapper used by the desktop icons. Calls start.sh / stop.sh,
#   waits for service health, then opens the ComfyUI URL (where the
#   Conjurer panel now lives) / sends a notification.
set -u

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-start}"
TARGET="${2:-single}"

mkdir -p "$PROJECT/logs"

notify() {
    local urgency="$1" title="$2" body="$3"
    notify-send -t 5000 -u "$urgency" "$title" "$body" 2>/dev/null || true
}

case "$ACTION" in
    start)
        notify normal "Comfy Assistant" "Starting ($TARGET) …"
        "$PROJECT/start.sh" "$TARGET" >> "$PROJECT/logs/launch.log" 2>&1 &
        # Primary URL = ComfyUI port (assistant lives inside it now)
        primary_port=8188
        [[ "$TARGET" == "gpu1" ]] && primary_port=8189
        for _ in $(seq 1 180); do
            if curl -fsS --max-time 1 "http://127.0.0.1:$primary_port/system_stats" >/dev/null 2>&1; then
                notify normal "Comfy Assistant" "Ready — opening browser"
                xdg-open "http://127.0.0.1:$primary_port" 2>/dev/null &
                exit 0
            fi
            sleep 1
        done
        notify critical "Comfy Assistant" "Startup timed out — check $PROJECT/logs/"
        exit 1
        ;;
    stop)
        "$PROJECT/stop.sh" "$TARGET" 2>&1 | tee -a "$PROJECT/logs/launch.log"
        case "$TARGET" in
            all)  notify normal "Comfy Assistant" "Stopped ComfyUI";;
            gpu0) notify normal "Comfy Assistant" "Stopped GPU 0 (:8188)";;
            gpu1) notify normal "Comfy Assistant" "Stopped GPU 1 (:8189)";;
        esac
        ;;
    *)
        echo "usage: $0 start [single|dual|gpu1]" >&2
        echo "       $0 stop  [all|gpu0|gpu1]" >&2
        exit 2
        ;;
esac
