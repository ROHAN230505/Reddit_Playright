#!/bin/sh
# Start a virtual X server and run the given command under it.
#
# The GLP scraper drives Chromium *headful* (GLP_HEADLESS=0) to clear
# Cloudflare; headful Chromium needs a real X display. `xvfb-run` proved
# unreliable here because celery's prefork pool didn't inherit its DISPLAY,
# so we start Xvfb ourselves, export DISPLAY into the environment, then exec
# the command — every forked pool worker then inherits DISPLAY through exec.
set -e

XVFB_DISPLAY="${XVFB_DISPLAY:-:99}"
XVFB_WHD="${XVFB_WHD:-1280x1024x24}"

# Start Xvfb in the background and remember its pid for cleanup.
Xvfb "$XVFB_DISPLAY" -screen 0 "$XVFB_WHD" -nolisten tcp &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT INT TERM

# Wait briefly for the server socket to come up so the first browser launch
# doesn't race Xvfb startup.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if [ -e "/tmp/.X11-unix/X${XVFB_DISPLAY#:}" ]; then
        break
    fi
    sleep 0.3
done

export DISPLAY="$XVFB_DISPLAY"
exec "$@"
