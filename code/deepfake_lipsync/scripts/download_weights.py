"""Download SyncNet weights from Hugging Face into /app/weights (Docker build step)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = os.getenv("HF_WEIGHTS_REPO", "lithiumice/syncnet")
OUT_DIR = Path(os.getenv("WEIGHTS_DIR", "/app/weights"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    syncnet_src = hf_hub_download(repo_id=REPO_ID, filename="syncnet_v2.model")
    s3fd_src = hf_hub_download(repo_id=REPO_ID, filename="sfd_face.pth")

    syncnet_dst = OUT_DIR / "syncnet_v2.model"
    s3fd_dst = OUT_DIR / "sfd_face.pth"
    shutil.copy2(syncnet_src, syncnet_dst)
    shutil.copy2(s3fd_src, s3fd_dst)

    print(f"Saved {syncnet_dst} ({syncnet_dst.stat().st_size} bytes)")
    print(f"Saved {s3fd_dst} ({s3fd_dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
