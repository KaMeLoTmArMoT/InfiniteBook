from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

IMG_ROOT = Path("data/images")


@dataclass(frozen=True)
class StoredImage:
    job_id: str
    index: int
    path: Path
    url: str


def image_path(job_id: str, index: int, ext: str = "png") -> Path:
    return IMG_ROOT / job_id / f"{index}.{ext}"


def image_url(job_id: str, index: int) -> str:
    return f"/api/imggen/image/{job_id}/{index}"


def save_image_bytes(job_id: str, index: int, data: bytes, ext: str = "png") -> StoredImage:
    p = image_path(job_id, index, ext=ext)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return StoredImage(job_id=job_id, index=index, path=p, url=image_url(job_id, index))


def delete_job_dir(job_id: str) -> bool:
    p = IMG_ROOT / job_id
    if not p.exists():
        return False
    shutil.rmtree(p, ignore_errors=True)
    return True
