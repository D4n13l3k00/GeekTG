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

# uv-managed venv. ``uv sync`` reads pyproject.toml + uv.lock, installs the
# exact pinned versions, and pre-creates ``/home/ftg/.venv``. Putting it
# first on PATH makes ``gtg`` and ``python`` resolve into the venv without
# any activation step.
ENV VIRTUAL_ENV=/home/ftg/.venv \
    UV_PROJECT_ENVIRONMENT=/home/ftg/.venv \
    PATH="/home/ftg/.venv/bin:${PATH}"

RUN uv sync --frozen --no-dev \
 && uv pip install Pillow pydub ffmpeg-python wand moviepy numpy

# Pre-create the data tree owned by ``ftg`` so a named volume mounted on top
# inherits its ownership on first use. Without this, Docker creates the
# mount point as root and the bot can't write loaded_modules / sessions.
RUN mkdir -p /home/ftg/.local/share/friendly-telegram/loaded_modules \
             /home/ftg/.local/share/friendly-telegram/assets

EXPOSE 8888

ENTRYPOINT ["gtg", "--port", "8888"]
