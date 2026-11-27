# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
# Retain downloaded wheels between builds without storing them in the image.
RUN --mount=type=cache,id=fantasy-football-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install --only-binary=:all: -r requirements.txt

# CUDA 12.6 retains Pascal support, including the Quadro P1000 (sm_61).
ARG TORCH_VERSION=2.14.1
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
RUN --mount=type=cache,id=fantasy-football-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}" \
    && python -m pip check

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/cache /app/data /app/secrets /app/models/pytorch \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser main.py ./main.py

USER appuser
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
