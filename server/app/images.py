"""Image processing and storage shared by uploads and generated scene photos."""
from __future__ import annotations

import io
import os

from .common import new_id
from .crypto import read_sealed, write_sealed
from .config import settings
from .db import Database, now_ms


# what a picture may be (other formats are refused: less parser surface) and how big it may be once decoded —
# a small file can declare a huge canvas ("decompression bomb") and take all the memory of the API
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
MAX_PIXELS = 16_000_000  # after JPEG draft scaling: ~64 MB as RGBA


def process_image(raw: bytes, max_side: int = 1280, crop: tuple[int, int] | None = None) -> tuple[bytes, int, int]:
    """Decode, fix orientation, flatten transparency and re-encode as JPEG (strips EXIF/GPS).
    crop=(2, 3) centre-crops to that width:height ratio (portrait avatars)."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw), formats=sorted(ALLOWED_FORMATS))
    if img.format == "JPEG":
        img.draft("RGB", (max_side, max_side))  # decode big photos at a reduced scale (fast, little memory)
    if img.width * img.height > MAX_PIXELS:
        raise ValueError(f"image too large: {img.width}x{img.height}")
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
    if crop:
        cw, ch = crop
        w, h = img.size
        if w * ch > h * cw:  # too wide
            nw = h * cw // ch
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        elif w * ch < h * cw:  # too tall
            nh = w * ch // cw
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue(), img.width, img.height


def read_image(iid: str) -> bytes | None:
    """Bytes of a stored image (JPEG), or None."""
    if not iid or "/" in iid or ".." in iid:
        return None
    try:
        return read_sealed(os.path.join(settings.images_dir, iid + ".jpg"), iid)
    except OSError:
        return None


def save_image(db: Database, owner_id: int | None, data: bytes, w: int, h: int) -> str:
    iid = new_id(16)
    os.makedirs(settings.images_dir, exist_ok=True)
    write_sealed(os.path.join(settings.images_dir, iid + ".jpg"), data, iid)  # encrypted at rest (DATA_KEY)
    db.run("INSERT INTO images(id, owner_id, mime, size, width, height, created_at) VALUES(?,?,?,?,?,?,?)",
           (iid, owner_id, "image/jpeg", len(data), w, h, now_ms()))
    return iid


# every place that points at a picture (see db.SCHEMA and MIGRATIONS)
_IMAGE_REFS = (("stories", "cover_image_id"), ("characters", "avatar_image_id"), ("personas", "avatar_image_id"),
               ("users", "avatar_image_id"), ("messages", "image_id"), ("image_jobs", "image_id"))


def drop_unreferenced(db: Database, ids) -> list[str]:
    """Deletes the rows of those pictures that nothing points at any more; returns their ids, whose files the
    caller removes with delete_image_files after the transaction. Call inside a transaction."""
    gone = []
    for iid in sorted({i for i in ids if i}):
        if any(db.one(f"SELECT 1 FROM {t} WHERE {c}=? LIMIT 1", (iid,)) for t, c in _IMAGE_REFS):
            continue
        db.run("DELETE FROM images WHERE id=?", (iid,))
        gone.append(iid)
    return gone


def delete_image_files(ids) -> None:
    """Removes stored files (rows are deleted by the caller); missing files are fine."""
    for iid in ids:
        if not iid or "/" in iid or ".." in iid:
            continue
        try:
            os.remove(os.path.join(settings.images_dir, iid + ".jpg"))
        except OSError:
            pass
