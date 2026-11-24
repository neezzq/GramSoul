"""Image processing and storage shared by uploads and generated scene photos."""
from __future__ import annotations

import io
import os

from .common import new_id
from .config import settings
from .db import Database, now_ms


def process_image(raw: bytes, max_side: int = 1280) -> tuple[bytes, int, int]:
    """Decode, fix orientation, flatten transparency and re-encode as JPEG (strips EXIF/GPS)."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        bg = Image.new("RGB", img.size, (12, 10, 14))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue(), img.width, img.height


def save_image(db: Database, owner_id: int | None, data: bytes, w: int, h: int) -> str:
    iid = new_id(16)
    os.makedirs(settings.images_dir, exist_ok=True)
    with open(os.path.join(settings.images_dir, iid + ".jpg"), "wb") as f:
        f.write(data)
    db.run("INSERT INTO images(id, owner_id, mime, size, width, height, created_at) VALUES(?,?,?,?,?,?,?)",
           (iid, owner_id, "image/jpeg", len(data), w, h, now_ms()))
    return iid
