"""
Demucs RunPod Serverless Worker
Separates audio into stems (vocals, drums, bass, other) using Meta's Demucs model
Uses Supabase Storage for output files

Optimizations:
- Model pre-loading at startup (eliminates cold start)
- Direct Python API instead of subprocess
- Streaming uploads to Supabase
- Automatic mixed precision (autocast) on GPU for faster inference
- Segment-based processing for memory efficiency
"""

import runpod
import requests
import tempfile
import os
import torch
import torchaudio
from pathlib import Path
import uuid
import shutil
from demucs.pretrained import get_model
from demucs.apply import apply_model
from demucs.audio import save_audio

# Detect device and optimize
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")

# Pre-load model at startup
print("Loading Demucs model...")
DEMUCS_MODEL = get_model("htdemucs")
DEMUCS_MODEL.to(DEVICE)
# Note: Keep model in float32 - we'll use autocast for mixed precision instead
# Using .half() directly causes "expected scalar type Float but found Half" errors
DEMUCS_MODEL.eval()
print("Model loaded successfully!")

# Model source names
SOURCES = DEMUCS_MODEL.sources  # ['drums', 'bass', 'other', 'vocals']


def download_audio(url: str, output_path: str) -> None:
    """
    Download audio file from URL using streaming.
    Memory-efficient for large files.
    """
    with requests.get(url, timeout=300, stream=True) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)


def upload_to_supabase_streaming(
    file_path: str,
    bucket: str,
    storage_path: str,
    supabase_url: str,
    service_key: str,
) -> str:
    """Upload file to Supabase Storage using streaming and return public URL"""
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"

    file_size = os.path.getsize(file_path)

    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "audio/mpeg",
        "Content-Length": str(file_size),
        "x-upsert": "true",
    }

    with open(file_path, "rb") as f:
        response = requests.post(upload_url, headers=headers, data=f, timeout=120)
        response.raise_for_status()

    return f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"


def separate_audio(audio_path: str, output_dir: str) -> dict[str, str]:
    """
    Separate audio using pre-loaded Demucs model.
    Returns dict of stem name -> file path.
    """
    # Load audio
    wav, sr = torchaudio.load(audio_path)

    # Resample to model's sample rate if needed
    if sr != DEMUCS_MODEL.samplerate:
        wav = torchaudio.functional.resample(wav, sr, DEMUCS_MODEL.samplerate)
        sr = DEMUCS_MODEL.samplerate

    # Ensure stereo
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    elif wav.shape[0] > 2:
        wav = wav[:2]

    # Add batch dimension and keep as float32
    wav = wav.unsqueeze(0).to(DEVICE)

    # Apply model with optimized settings
    # Use autocast for automatic mixed precision on GPU (safer than manual .half())
    with torch.no_grad():
        if DEVICE == "cuda":
            with torch.amp.autocast(device_type="cuda"):
                sources = apply_model(
                    DEMUCS_MODEL,
                    wav,
                    device=DEVICE,
                    split=True,  # Process in segments for memory efficiency
                    overlap=0.25,
                    progress=False,
                )
        else:
            sources = apply_model(
                DEMUCS_MODEL,
                wav,
                device=DEVICE,
                split=True,
                overlap=0.25,
                progress=False,
            )

    # sources shape: (batch, num_sources, channels, samples)
    sources = sources.squeeze(0)  # Remove batch dimension

    # Ensure float32 for saving
    sources = sources.float()

    # Save each stem as MP3
    output_paths = {}
    for idx, source_name in enumerate(SOURCES):
        stem_path = os.path.join(output_dir, f"{source_name}.mp3")
        save_audio(
            sources[idx].cpu(),
            stem_path,
            samplerate=sr,
            bitrate=192,  # Good quality MP3
            clip="rescale",
        )
        output_paths[source_name] = stem_path

    return output_paths


def handler(event):
    """
    RunPod handler for Demucs source separation

    Input:
        audio_url: URL to audio file
        stems: (optional) Which stems to return, default all ['vocals', 'drums', 'bass', 'other']
        storage_bucket: (optional) Supabase storage bucket, default 'stems'
        storage_prefix: (optional) Storage path prefix, default 'demucs'

    Output:
        vocals: URL to vocals stem
        drums: URL to drums stem
        bass: URL to bass stem
        other: URL to other instruments stem
    """
    audio_path = None
    output_dir = None

    try:
        input_data = event.get("input", {})
        audio_url = input_data.get("audio_url")

        if not audio_url:
            return {"error": "audio_url is required"}

        # Get Supabase credentials from environment
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_service_key:
            return {
                "error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required"
            }

        # Optional parameters
        stems = input_data.get("stems", ["vocals", "drums", "bass", "other"])
        storage_bucket = input_data.get("storage_bucket", "stems")
        storage_prefix = input_data.get("storage_prefix", "demucs")

        # Create temp directory for outputs
        output_dir = tempfile.mkdtemp()

        # Determine file extension from URL
        ext = ".wav"
        url_lower = audio_url.lower()
        if ".mp3" in url_lower:
            ext = ".mp3"
        elif ".flac" in url_lower:
            ext = ".flac"
        elif ".ogg" in url_lower:
            ext = ".ogg"
        elif ".m4a" in url_lower:
            ext = ".m4a"

        audio_path = os.path.join(output_dir, f"input{ext}")

        # Download audio file with streaming
        download_audio(audio_url, audio_path)

        # Run separation
        stem_paths = separate_audio(audio_path, output_dir)

        # Upload requested stems to Supabase Storage
        job_id = str(uuid.uuid4())[:8]
        output_urls = {}

        for stem in stems:
            if stem in stem_paths and os.path.exists(stem_paths[stem]):
                storage_path = f"{storage_prefix}/{job_id}/{stem}.mp3"
                url = upload_to_supabase_streaming(
                    stem_paths[stem],
                    storage_bucket,
                    storage_path,
                    supabase_url,
                    supabase_service_key,
                )
                output_urls[stem] = url
            else:
                output_urls[stem] = None

        return output_urls

    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to download/upload: {str(e)}"}
    except torch.cuda.OutOfMemoryError:
        return {"error": "GPU out of memory. Try a shorter audio file."}
    except Exception as e:
        return {"error": f"Separation failed: {str(e)}"}
    finally:
        # Clean up temporary files
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except Exception:
                pass
        if output_dir and os.path.exists(output_dir):
            try:
                shutil.rmtree(output_dir)
            except Exception:
                pass


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
