# Playwright base image ships chromium + all OS deps and handles proxy
# tunneling correctly — needed for the GLP scraper (godlikeproductions.com sits
# behind Cloudflare, so plain headless Playwright on a slim image fails). Same
# image family the playwright_worker uses.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# patchright needs its own chromium build; install it into the shared cache.
RUN python -m patchright install chromium

COPY . .

# Entrypoint that brings up Xvfb before running the command — required for the
# GLP scraper's headful Chromium. uvicorn/celery commands pass through unchanged
# when an X display isn't needed (Xvfb just runs idle alongside).
RUN chmod +x /app/docker-entrypoint-xvfb.sh

ENV PYTHONPATH=/app

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
# Make the browser cache readable by the runtime user.
RUN if [ -d /root/.cache/ms-playwright ]; then \
        cp -r /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright 2>/dev/null || true; \
        chown -R appuser:appuser /home/appuser/.cache; \
    fi
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
