# Lip-sync microservice (SyncNet + Hugging Face)

Phát hiện **lip-sync bất thường** (Wav2Lip / deepfake môi) bằng [syncnet-python](https://pypi.org/project/syncnet-python/).

## Weights — tự tải lúc build Docker

**Không cần** copy file `.pth` thủ công. Image tự tải từ Hugging Face:

| File | Repo |
|------|------|
| `syncnet_v2.model` | [lithiumice/syncnet](https://huggingface.co/lithiumice/syncnet) |
| `sfd_face.pth` | [lithiumice/syncnet](https://huggingface.co/lithiumice/syncnet) |

> **Lưu ý:** `lipsync_expert.pth` (repo `Nekochu/Wav2Lip`) là weights **Wav2Lip expert**, **không** tương thích với `SyncNetPipeline` (architecture khác). Dùng `syncnet_v2.model` như trên.

## Production / web

| Cách | Khuyến nghị |
|------|-------------|
| Tải HF **lúc build image** | ✅ Ổn — đã cấu hình sẵn |
| Tải HF **lúc container start** | ⚠️ Chậm cold start, phụ thuộc mạng |
| Tải HF **mỗi request user** | ❌ Không dùng |

Pickle weights từ repo tin cậy trên HF là phổ biến với PyTorch; pin repo `lithiumice/syncnet`.

## Chạy

```bash
cd code
docker compose -f compose.ai.yml up --build lipsync-deepfake ai-modules
```

## API

`POST /api/lip-sync` — field `video_file` (video có mặt + giọng, ~2–3 giây trở lên).

Response tương thích client eKYC: `verdict`, `manipulation_probability`, `confidence`, …

## Env tuỳ chọn

```bash
DEVICE=cpu                    # hoặc cuda nếu có GPU
SYNCNET_MIN_TRACK=30          # frame tối thiểu track mặt (video eKYC ngắn)
SYNCNET_MIN_DIST_REAL_MAX=7.0
SYNCNET_CONFIDENCE_REAL_MIN=3.5
```
