# Video Generation (Veo 3) - Implementation Guide

## Tổng quan

Tool hỗ trợ tạo video từ ảnh (Image-to-Video / I2V) sử dụng Google Veo 3 API thông qua proxy nanoai.pics.

## Flow hoạt động

```
1. Tạo ảnh (Image) → Lấy mediaId
2. Tạo video từ ảnh (I2V) → Lấy operations array
3. Poll Google API trực tiếp → Lấy video URL
4. Download video
```

## API Endpoints

### 1. Proxy API (nanoai.pics) - Bypass captcha

```
POST https://flow-api.nanoai.pics/api/fix/create-image-veo3   # Tạo ảnh
POST https://flow-api.nanoai.pics/api/fix/create-video-veo3   # Tạo video
GET  https://flow-api.nanoai.pics/api/fix/task-status?taskId=xxx  # Check status
```

### 2. Google API (Direct)

```
POST https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages  # I2V
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText             # T2V
POST https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus    # Poll
```

## Video Models

| Model | Type | Description |
|-------|------|-------------|
| `veo_3_0_r2v_fast_ultra` | I2V | Image-to-Video (reference image) |
| `veo_3_1_t2v_fast` | T2V | Text-to-Video (landscape) |
| `veo_3_1_t2v_fast_portrait` | T2V | Text-to-Video (portrait) |
| `veo_3_1_i2v_s_fast_fl` | I2V | Start/End frame video |

## Request Formats

### Tạo ảnh (để lấy mediaId)

```python
body_json = {
    "clientContext": {
        "sessionId": ";1234567890",
        "projectId": PROJECT_ID,
        "tool": "PINHOLE"
    },
    "requests": [{
        "clientContext": {
            "sessionId": ";1234567890",
            "projectId": PROJECT_ID,
            "tool": "PINHOLE"
        },
        "seed": 123456,
        "imageModelName": "GEM_PIX_2",
        "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
        "prompt": "A cute cat",
        "imageInputs": []
    }]
}

# Gửi qua proxy
payload = {
    "body_json": body_json,
    "flow_auth_token": BEARER_TOKEN,
    "flow_url": f"https://aisandbox-pa.googleapis.com/v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages"
}
```

### Tạo video từ ảnh (I2V)

```python
body_json = {
    "clientContext": {
        "projectId": PROJECT_ID,
        "recaptchaToken": "",  # Proxy xử lý
        "sessionId": ";1234567890",
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_TWO"
    },
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
        "metadata": {
            "sceneId": "scene-uuid-here"
        },
        "referenceImages": [{
            "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
            "mediaId": "CAMSJDc2NzdkOThmLWY4MzgtNGE..."  # Từ bước tạo ảnh
        }],
        "seed": 8465,
        "textInput": {
            "prompt": "The cat walks slowly, cinematic"
        },
        "videoModelKey": "veo_3_0_r2v_fast_ultra"
    }]
}

payload = {
    "body_json": body_json,
    "flow_auth_token": BEARER_TOKEN,
    "flow_url": "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages"
}
```

### Poll Video Status (QUAN TRỌNG!)

**Format đúng** - Gửi nguyên `operations` array từ response tạo video:

```python
# Response từ tạo video chứa:
# {"operations": [{"operation": {"name": "abc123"}, "sceneId": "scene-xxx", "status": "PENDING"}]}

# Lưu lại operations array
operations = result.get("operations", [])

# Poll Google API trực tiếp
url = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"
headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

payload = {
    "operations": operations  # Gửi NGUYÊN array, không chỉ operation name
}

response = requests.post(url, headers=headers, json=payload)
```

## Video Status Values

| Status | Meaning |
|--------|---------|
| `MEDIA_GENERATION_STATUS_PENDING` | Đang chờ |
| `MEDIA_GENERATION_STATUS_ACTIVE` | Đang xử lý |
| `MEDIA_GENERATION_STATUS_SUCCESSFUL` | Hoàn thành |
| `MEDIA_GENERATION_STATUS_ERROR_*` | Lỗi |

## Extract Video URL

Khi status = `SUCCESSFUL`, video URL nằm ở:

```python
video_url = result["operations"][0]["operation"]["metadata"]["video"]["fifeUrl"]
```

## Code mẫu hoàn chỉnh

```python
import json
import time
import requests

PROJECT_ID = "your-project-id"
BEARER_TOKEN = "ya29.xxx"
PROXY_TOKEN = "eyJhbG..."

PROXY_BASE = "https://flow-api.nanoai.pics/api/fix"
GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"


def proxy_headers():
    return {"Authorization": f"Bearer {PROXY_TOKEN}", "Content-Type": "application/json"}


def google_headers():
    return {"Authorization": f"Bearer {BEARER_TOKEN}", "Content-Type": "application/json"}


def create_image(prompt):
    """Tạo ảnh và trả về mediaId."""
    session_id = f";{int(time.time() * 1000)}"

    body_json = {
        "clientContext": {"sessionId": session_id, "projectId": PROJECT_ID, "tool": "PINHOLE"},
        "requests": [{
            "clientContext": {"sessionId": session_id, "projectId": PROJECT_ID, "tool": "PINHOLE"},
            "seed": 123456,
            "imageModelName": "GEM_PIX_2",
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "prompt": prompt,
            "imageInputs": []
        }]
    }

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages"
    }

    r = requests.post(f"{PROXY_BASE}/create-image-veo3", headers=proxy_headers(), json=payload, timeout=30)
    task_id = r.json()["taskId"]

    # Poll for result
    for _ in range(60):
        r = requests.get(f"{PROXY_BASE}/task-status?taskId={task_id}", headers=proxy_headers())
        result = r.json().get("result", {})
        if "media" in result:
            return result["media"][0].get("name")  # mediaId
        time.sleep(2)

    return None


def create_video(media_id, prompt):
    """Tạo video từ ảnh."""
    session_id = f";{int(time.time() * 1000)}"

    body_json = {
        "clientContext": {
            "projectId": PROJECT_ID,
            "recaptchaToken": "",
            "sessionId": session_id,
            "tool": "PINHOLE",
            "userPaygateTier": "PAYGATE_TIER_TWO"
        },
        "requests": [{
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "metadata": {"sceneId": f"scene-{int(time.time())}"},
            "referenceImages": [{"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": media_id}],
            "seed": 8465,
            "textInput": {"prompt": prompt},
            "videoModelKey": "veo_3_0_r2v_fast_ultra"
        }]
    }

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"
    }

    r = requests.post(f"{PROXY_BASE}/create-video-veo3", headers=proxy_headers(), json=payload, timeout=30)
    task_id = r.json()["taskId"]

    # Poll proxy để lấy operations array
    operations = None
    for _ in range(30):
        r = requests.get(f"{PROXY_BASE}/task-status?taskId={task_id}", headers=proxy_headers())
        result = r.json().get("result", {})
        if "operations" in result:
            operations = result["operations"]
            break
        time.sleep(3)

    if not operations:
        return None

    # Poll Google trực tiếp
    url = f"{GOOGLE_BASE}/v1/video:batchCheckAsyncVideoGenerationStatus"

    for _ in range(60):
        r = requests.post(url, headers=google_headers(), json={"operations": operations}, timeout=30)
        if r.status_code == 200:
            result = r.json()
            op = result.get("operations", [{}])[0]
            status = op.get("status", "")

            if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                return op["operation"]["metadata"]["video"]["fifeUrl"]

            if "ERROR" in status or "FAILED" in status:
                return None

        time.sleep(5)

    return None


# Usage
media_id = create_image("A cute orange cat, 8K photo")
video_url = create_video(media_id, "The cat walks slowly, cinematic")
print(f"Video URL: {video_url}")
```

## Tokens cần thiết

1. **BEARER_TOKEN** (`ya29.xxx`): Lấy từ Chrome DevTools khi tạo ảnh trên https://labs.google/fx/tools/flow
2. **PROXY_TOKEN**: Token từ nanoai.pics
3. **PROJECT_ID**: UUID project, có thể tạo mới hoặc lấy từ Chrome

## Lưu ý

- Bearer token hết hạn sau ~1 giờ, cần refresh
- Video generation mất 1-3 phút
- Proxy chỉ cache response ban đầu, cần poll Google trực tiếp để lấy video URL
- Format poll đúng: `{"operations": operations_array}` - gửi nguyên array, không chỉ operation name
