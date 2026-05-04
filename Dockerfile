FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    IS_DOCKER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

# System packages required by core + media-processing third-party modules
# (Pillow, pydub, wand/imagemagick, moviepy, zbar, tesseract OCR, etc.).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        wget curl ca-certificates gnupg \
        git build-essential \
        ffmpeg imagemagick \
        tesseract-ocr tesseract-ocr-rus \
        libzbar-dev zbar-tools \
        libwebp-dev libz-dev libjpeg-dev libopenjp2-7 libtiff6 \
        libffi-dev libcairo2 \
        dialog tree zsh iputils-ping \
 && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Pull a static uv binary from Astral's distroless image — keeps the build
# stage minimal, no compilation, always the latest stable release.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd -m -s /bin/bash ftg
WORKDIR /home/ftg
COPY --chown=ftg:ftg . /home/ftg
USER ftg

# Two venv locations:
#   /opt/gtg-venv  — immutable seed baked into the image
#   /home/ftg/.venv — runtime venv (a Docker volume, persists across rebuilds)
#
# Building only the seed and copying it into the volume on first start lets
# packages installed at runtime (e.g. by .loadmod's "# requires:" auto-
# installer) survive ``docker compose up --build``.
ENV VIRTUAL_ENV=/home/ftg/.venv \
    UV_PROJECT_ENVIRONMENT=/home/ftg/.venv \
    PATH="/home/ftg/.venv/bin:${PATH}"

USER root
RUN install -d -o ftg -g ftg /opt/gtg-venv
USER ftg

RUN UV_PROJECT_ENVIRONMENT=/opt/gtg-venv uv sync --frozen --no-dev \
 && uv pip install --python /opt/gtg-venv/bin/python \
        Pillow pydub ffmpeg-python wand moviepy numpy

# Pre-create the data tree owned by ``ftg`` so a named volume mounted on top
# inherits its ownership on first use. Without this, Docker creates the
# mount point as root and the bot can't write loaded_modules / sessions.
RUN mkdir -p /home/ftg/.local/share/friendly-telegram/loaded_modules \
             /home/ftg/.local/share/friendly-telegram/assets \
             /home/ftg/.venv

COPY --chown=ftg:ftg docker/entrypoint.sh /usr/local/bin/gtg-entrypoint
USER root
RUN chmod +x /usr/local/bin/gtg-entrypoint
USER ftg

EXPOSE 8888

ENTRYPOINT ["gtg-entrypoint"]
CMD ["gtg", "--port", "8888"]
