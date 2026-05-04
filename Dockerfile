FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    IS_DOCKER=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# System packages required by core + media-processing third-party modules
# (Pillow, pydub, wand/imagemagick, moviepy, zbar, tesseract OCR, etc.).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        software-properties-common wget curl ca-certificates gnupg \
        git build-essential \
        ffmpeg imagemagick \
        tesseract-ocr tesseract-ocr-rus \
        libzbar-dev zbar-tools \
        libwebp-dev libz-dev libjpeg-dev libopenjp2-7 libtiff6 \
        libffi-dev libcairo2 \
        dialog neofetch tree zsh iputils-ping \
 && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash ftg
WORKDIR /home/ftg
COPY --chown=ftg:ftg . /home/ftg
USER ftg

ENV PATH="/home/ftg/.local/bin:${PATH}"

RUN python3 -m pip install --user --upgrade pip \
 && python3 -m pip install --user . \
 && python3 -m pip install --user \
        Pillow pydub ffmpeg-python wand moviepy numpy \
 && python3 -m pip cache purge

EXPOSE 8888

ENTRYPOINT ["gtg", "--port", "8888"]
