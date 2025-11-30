"""
Demucs RunPod Serverless Worker
Separates audio into stems (vocals, drums, bass, other) using Meta's Demucs model
Uses Supabase Storage for output files
"""

import runpod
import requests
import tempfile
import os
import subprocess
from pathlib import Path
import uuid


def download_audio(url: str) -> str:
    """Download audio file from URL to temporary file"""
    response = requests.get(url, timeout=300)
    response.raise_for_status()

    # Determine file extension from URL or content type
    ext = ".wav"
    if ".mp3" in url.lower():
        ext = ".mp3"
    elif ".flac" in url.lower():
        ext = ".flac"
    elif ".ogg" in url.lower():
        ext = ".ogg"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(response.content)
        return f.name


def upload_to_supabase(file_path: str, bucket: str, storage_path: str, supabase_url: str, service_key: str) -> str:
    """Upload file to Supabase Storage and return public URL"""
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"

    with open(file_path, "rb") as f:
        file_data = f.read()

    headers = {
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "audio/mpeg",
        "x-upsert": "true",
    }

    response = requests.post(upload_url, headers=headers, data=file_data, timeout=120)
    response.raise_for_status()

    # Return public URL
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"


def handler(event):
    """
    RunPod handler for Demucs source separation

    Input:
        audio_url: URL to audio file
        model: (optional) Demucs model name, default 'htdemucs'
        stems: (optional) Which stems to return, default all ['vocals', 'drums', 'bass', 'other']
        storage_bucket: (optional) Supabase storage bucket, default 'stems'
        storage_prefix: (optional) Storage path prefix, default 'demucs'

    Output:
        vocals: URL to vocals stem
        drums: URL to drums stem
        bass: URL to bass stem
        other: URL to other instruments stem
    """
    try:
        input_data = event.get("input", {})
        audio_url = input_data.get("audio_url")

        if not audio_url:
            return {"error": "audio_url is required"}

        # Get Supabase credentials from environment
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_service_key:
            return {"error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required"}

        # Optional parameters
        model = input_data.get("model", "htdemucs")
        stems = input_data.get("stems", ["vocals", "drums", "bass", "other"])
        storage_bucket = input_data.get("storage_bucket", "stems")
        storage_prefix = input_data.get("storage_prefix", "demucs")

        # Download audio file
        audio_path = download_audio(audio_url)
        output_dir = tempfile.mkdtemp()

        try:
            # Run Demucs separation
            cmd = [
                "python",
                "-m",
                "demucs.separate",
                "-n",
                model,
                "-o",
                output_dir,
                "--mp3",  # Output as MP3 for smaller file sizes
                audio_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                return {"error": f"Demucs failed: {result.stderr}"}

            # Find output directory
            audio_name = Path(audio_path).stem
            stems_dir = Path(output_dir) / model / audio_name

            if not stems_dir.exists():
                return {"error": f"Output directory not found: {stems_dir}"}

            # Upload stems to Supabase Storage
            job_id = str(uuid.uuid4())[:8]
            output_urls = {}

            for stem in stems:
                stem_file = stems_dir / f"{stem}.mp3"
                if stem_file.exists():
                    storage_path = f"{storage_prefix}/{job_id}/{stem}.mp3"
                    url = upload_to_supabase(
                        str(stem_file),
                        storage_bucket,
                        storage_path,
                        supabase_url,
                        supabase_service_key
                    )
                    output_urls[stem] = url
                else:
                    output_urls[stem] = None

            return output_urls

        finally:
            # Clean up temporary files
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            # Clean up output directory
            import shutil

            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)

    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to download audio: {str(e)}"}
    except subprocess.TimeoutExpired:
        return {"error": "Demucs processing timed out (>10 minutes)"}
    except Exception as e:
        return {"error": f"Separation failed: {str(e)}"}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
