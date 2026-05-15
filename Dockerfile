# Vibe Engine — production Docker image for Fly.io deploy.
#
# Builds the Python FastAPI server defined in run_agentic_application.py.
# Customer traffic from Vibe (Vercel) hits this container via HTTPS;
# the engine runs the planner/architect/composer/rater/try-on pipeline
# and returns outfit recommendations.
#
# Image base: python:3.11-slim (Debian — keeps pillow-heif / pillow-avif
# wheels installable; Alpine would force source builds for libheif).

FROM python:3.11-slim

# System libs needed by Pillow's HEIF/AVIF plugins. Listed explicitly
# so a future libpng/libjpeg version bump in Debian doesn't break the
# wardrobe upload path silently.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libheif1 \
      libjpeg62-turbo \
      libpng16-16 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first for Docker layer caching — rebuilding code shouldn't
# reinstall the full Python stack.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Runtime files. Tests, data dumps, vibe-app/, scripts/, ops/, supabase/
# are excluded by .dockerignore — engine doesn't need them.
COPY modules/ ./modules/
COPY knowledge/ ./knowledge/
COPY run_agentic_application.py ./

# Flush stdout so structured logs reach Fly's log collector promptly.
ENV PYTHONUNBUFFERED=1

# Default bind; Fly's HTTP proxy maps external 443 → internal 8010.
EXPOSE 8010

CMD ["python", "run_agentic_application.py", "--host", "0.0.0.0", "--port", "8010"]
