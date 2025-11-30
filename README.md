# scoreforge-runpod-demucs

Meta의 Demucs 모델을 사용한 오디오 소스 분리 RunPod Serverless 워커

## 배포 방법

### RunPod GitHub 연동 (권장)

1. [RunPod Console](https://www.runpod.io/console/serverless) 접속
2. "New Endpoint" → "GitHub Repo" 선택
3. `modootoday/scoreforge-runpod-demucs` 레포 연결
4. GPU 타입: **RTX 3090** 이상 선택
5. Environment Variables 설정:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
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
    "storage_bucket": "stems",
    "storage_prefix": "demucs",
    "model": "htdemucs",
    "stems": ["vocals", "drums", "bass", "other"]
  }
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `audio_url` | string | (필수) | 오디오 파일 URL |
| `storage_bucket` | string | "stems" | Supabase Storage 버킷 |
| `storage_prefix` | string | "demucs" | 스토리지 경로 프리픽스 |
| `model` | string | "htdemucs" | Demucs 모델 이름 |
| `stems` | array | ["vocals", "drums", "bass", "other"] | 분리할 스템 |

### 응답

```json
{
  "vocals": "https://xxx.supabase.co/storage/v1/object/public/stems/demucs/abc123/vocals.mp3",
  "drums": "https://xxx.supabase.co/storage/v1/object/public/stems/demucs/abc123/drums.mp3",
  "bass": "https://xxx.supabase.co/storage/v1/object/public/stems/demucs/abc123/bass.mp3",
  "other": "https://xxx.supabase.co/storage/v1/object/public/stems/demucs/abc123/other.mp3"
}
```

## 환경 변수

RunPod Endpoint에서 설정 필요:

| 변수 | 설명 |
|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase 서비스 롤 키 |

## Supabase Storage 설정

1. Supabase Dashboard에서 `stems` 버킷 생성
2. 버킷을 **public**으로 설정 (또는 적절한 RLS 정책 설정)

## 로컬 테스트

```bash
pip install -r requirements.txt
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
python handler.py
```

## 라이선스

MIT License
