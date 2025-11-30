# scoreforge-runpod-demucs

Meta의 Demucs 모델을 사용한 오디오 소스 분리 RunPod Serverless 워커

## 배포 방법

### RunPod GitHub 연동 (권장)

1. [RunPod Console](https://www.runpod.io/console/serverless) 접속
2. "New Endpoint" → "GitHub Repo" 선택
3. `modootoday/scoreforge-runpod-demucs` 레포 연결
4. GPU 타입: **RTX 3090** 이상 선택
5. Environment Variables 설정:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` (기본값: us-east-1)
6. 배포 완료 후 Endpoint URL 복사

### Docker Hub 사용

```bash
docker build -t your-username/scoreforge-runpod-demucs:latest .
docker push your-username/scoreforge-runpod-demucs:latest
```

## API

### 요청

```json
{
  "input": {
    "audio_url": "https://example.com/audio.mp3",
    "s3_bucket": "your-bucket-name",
    "s3_prefix": "demucs-outputs",
    "model": "htdemucs",
    "stems": ["vocals", "drums", "bass", "other"]
  }
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `audio_url` | string | (필수) | 오디오 파일 URL |
| `s3_bucket` | string | (필수) | S3 버킷 이름 |
| `s3_prefix` | string | "demucs-outputs" | S3 키 프리픽스 |
| `model` | string | "htdemucs" | Demucs 모델 이름 |
| `stems` | array | ["vocals", "drums", "bass", "other"] | 분리할 스템 |

### 응답

```json
{
  "vocals": "https://bucket.s3.amazonaws.com/demucs-outputs/abc123/vocals.mp3",
  "drums": "https://bucket.s3.amazonaws.com/demucs-outputs/abc123/drums.mp3",
  "bass": "https://bucket.s3.amazonaws.com/demucs-outputs/abc123/bass.mp3",
  "other": "https://bucket.s3.amazonaws.com/demucs-outputs/abc123/other.mp3"
}
```

## 환경 변수

RunPod Endpoint에서 설정 필요:

| 변수 | 설명 |
|------|------|
| `AWS_ACCESS_KEY_ID` | AWS 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | AWS 시크릿 키 |
| `AWS_REGION` | AWS 리전 (기본값: us-east-1) |

## 로컬 테스트

```bash
pip install -r requirements.txt
python handler.py
```

## 라이선스

MIT License
