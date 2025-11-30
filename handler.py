"""
Demucs RunPod Serverless Worker
Separates audio into stems (vocals, drums, bass, other) using Meta's Demucs model
"""

import runpod
import requests
import tempfile
import os
import subprocess
import boto3
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


def upload_to_s3(file_path: str, bucket: str, key: str, s3_client) -> str:
    """Upload file to S3 and return public URL"""
    s3_client.upload_file(
        file_path,
        bucket,
        key,
        ExtraArgs={"ContentType": "audio/wav", "ACL": "public-read"},
    )
    return f"https://{bucket}.s3.amazonaws.com/{key}"


def handler(event):
    """
    RunPod handler for Demucs source separation

    Input:
        audio_url: URL to audio file
        model: (optional) Demucs model name, default 'htdemucs'
        stems: (optional) Which stems to return, default all ['vocals', 'drums', 'bass', 'other']
        s3_bucket: S3 bucket for uploading results
        s3_prefix: (optional) S3 key prefix, default 'demucs-outputs'

    Output:
        vocals: URL to vocals stem
        drums: URL to drums stem
        bass: URL to bass stem
        other: URL to other instruments stem
    """
    try:
        input_data = event.get("input", {})
        audio_url = input_data.get("audio_url")
        s3_bucket = input_data.get("s3_bucket")

        if not audio_url:
            return {"error": "audio_url is required"}

        if not s3_bucket:
            return {"error": "s3_bucket is required for storing output stems"}

        # Optional parameters
        model = input_data.get("model", "htdemucs")
        stems = input_data.get("stems", ["vocals", "drums", "bass", "other"])
        s3_prefix = input_data.get("s3_prefix", "demucs-outputs")

        # Get AWS credentials from environment
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

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

            # Upload stems to S3
            job_id = str(uuid.uuid4())[:8]
            output_urls = {}

            for stem in stems:
                stem_file = stems_dir / f"{stem}.mp3"
                if stem_file.exists():
                    s3_key = f"{s3_prefix}/{job_id}/{stem}.mp3"
                    url = upload_to_s3(str(stem_file), s3_bucket, s3_key, s3_client)
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
