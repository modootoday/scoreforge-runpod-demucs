# RunPod Serverless Worker for Demucs
# Optimized for fast inference on GPU/CPU

# Use CUDA runtime for GPU support
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# PyTorch optimizations
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
ENV TORCH_HOME=/app/.cache/torch
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# CPU thread optimization (for CPU-only workers)
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the htdemucs model during build
# This makes the model part of the image, eliminating download time at runtime
RUN python -c "\
from demucs.pretrained import get_model; \
import torch; \
model = get_model('htdemucs'); \
print(f'Model loaded: {type(model).__name__}'); \
print(f'Sources: {model.sources}'); \
"

# Copy handler
COPY handler.py .

# Health check - verify model loads correctly
RUN python -c "from handler import DEMUCS_MODEL, DEVICE; print(f'Handler OK - Device: {DEVICE}')"

# RunPod serverless entrypoint
CMD ["python", "-u", "handler.py"]
