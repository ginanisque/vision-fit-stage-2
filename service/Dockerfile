FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libegl1 libgles2 libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Match the locally verified MediaPipe setup without allowing it to replace the
# project's pinned OpenCV 5 package with an OpenCV 4 wheel.
RUN python -m pip install --no-cache-dir --no-deps mediapipe==1.1.0 \
    && python -m pip install --no-cache-dir absl-py certifi flatbuffers sounddevice matplotlib protobuf

COPY app ./app

# The pose task is intentionally not committed to the repository. Fetch the
# official MediaPipe model during the image build so a clean checkout can build
# and the slow-turn demo does not silently fall back to "model unavailable".
ARG MEDIAPIPE_POSE_MODEL_URL=https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
ENV MEDIAPIPE_POSE_MODEL_URL=${MEDIAPIPE_POSE_MODEL_URL}
RUN mkdir -p models \
    && python -c "import os, urllib.request; urllib.request.urlretrieve(os.environ['MEDIAPIPE_POSE_MODEL_URL'], 'models/pose_landmarker_full.task')"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
