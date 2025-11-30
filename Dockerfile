# RunPod Serverless Worker for Demucs
# Meta's audio source separation model

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Prevent interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the htdemucs model
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

# Copy handler
COPY handler.py .

# RunPod serverless entrypoint
CMD ["python", "-u", "handler.py"]
