# Playwright posting worker — production image.
#
# Uses the official Playwright Python image, which ships Chromium + every
# system library Chromium needs (we deliberately don't try to bake those
# manually — the maintainers do this better than we ever could).
#
# Sessions are persisted via a bind-mount on /home/pwuser/.reddit-worker-profile,
# so a one-time `python -m playwright_worker login` performed on a server
# is reused across container restarts.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USER_DATA_DIR=/home/pwuser/.reddit-worker-profile \
    SCREENSHOT_DIR=/app/worker-screenshots \
    BROWSER_CHANNEL=

WORKDIR /app

COPY requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/worker-requirements.txt

# Patchright is a hardened-stealth Playwright fork. It reuses the base
# image's Chromium binary; this command only registers the patched runtime.
RUN patchright install chromium || true

# Copy the worker package into the image. We deliberately keep it scoped
# to /app/playwright_worker so the existing repo layout maps cleanly into
# the container without dragging the backend along.
COPY . /app/playwright_worker

# Mountable, default-empty so a fresh container starts with a clean profile;
# the operator should bind-mount a host directory here for persistent login.
VOLUME ["/home/pwuser/.reddit-worker-profile", "/app/worker-screenshots"]

# Default = continuous loop. Override at `docker run` time with e.g.
# `... run --once` or `... login`.
ENTRYPOINT ["python", "-m", "playwright_worker"]
CMD ["run"]
