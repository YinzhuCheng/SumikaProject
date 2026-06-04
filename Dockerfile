FROM python:3.12-slim

ARG APT_DEBIAN_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG PIP_INDEX_URL=http://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    TZ=Asia/Shanghai

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i \
        -e "s#http://deb.debian.org/debian-security#${APT_SECURITY_MIRROR}#g" \
        -e "s#http://deb.debian.org/debian#${APT_DEBIAN_MIRROR}#g" \
        /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY config ./config
COPY assets ./assets
COPY roles ./roles

EXPOSE 8787
CMD ["uvicorn", "sumika_agent.app:app", "--host", "0.0.0.0", "--port", "8787"]
