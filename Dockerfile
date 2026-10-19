# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN useradd --create-home --uid 10001 app

FROM base AS toolchain
ARG WITH_LIBREOFFICE=true
ARG INSTALL_MSFONTS=false
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
        texlive-pictures lmodern fonts-texgyre fontconfig \
        fonts-liberation2 fonts-dejavu-core \
        poppler-utils ghostscript; \
    if [ "$WITH_LIBREOFFICE" = "true" ]; then \
        apt-get install -y --no-install-recommends libreoffice-writer-nogui; \
    fi; \
    if [ "$INSTALL_MSFONTS" = "true" ]; then \
        sed -i 's/Components: main/Components: main contrib/' /etc/apt/sources.list.d/debian.sources; \
        apt-get update; \
        echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections; \
        apt-get install -y --no-install-recommends ttf-mscorefonts-installer; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    fc-cache -f
COPY pdfconv ./pdfconv
COPY toolchain_service ./toolchain_service
ENV HOME=/home/app TEXMFVAR=/tmp/texmf-var
USER app
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=5)"
CMD ["uvicorn", "toolchain_service.app:app", "--host", "0.0.0.0", "--port", "8100"]

FROM base AS web
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-vie; \
    rm -rf /var/lib/apt/lists/*
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    PDFCONV_HOST=0.0.0.0 \
    PDFCONV_PORT=8000 \
    PDFCONV_DATA_DIR=/data
COPY pdfconv ./pdfconv
RUN mkdir -p /data && chown app:app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"
CMD ["python", "-m", "pdfconv", "serve"]

FROM toolchain AS standalone
USER root
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-vie; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /data && chown app:app /data
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    PDFCONV_HOST=0.0.0.0 \
    PDFCONV_PORT=8000 \
    PDFCONV_DATA_DIR=/data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"
CMD ["python", "-m", "pdfconv", "serve"]
