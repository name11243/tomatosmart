FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
ENV YOLO_CONFIG_DIR=/tmp/ultralytics MPLCONFIGDIR=/tmp/matplotlib YOLO_DEVICE=cpu
ARG DEBIAN_MIRROR=https://deb.debian.org
RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-vision.txt backend/requirements-vision.txt
ARG VISION_PIP_INDEX=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${VISION_PIP_INDEX}" -r backend/requirements-vision.txt
COPY backend ./backend
RUN mkdir -p /tmp/ultralytics
EXPOSE 8016
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8016"]
