"""Image preprocessing + perceptual hashing for the recognition pipeline.

Pure-CV stage that runs BEFORE any AI/TMDB call:
- preprocess(): crop letterbox bars, resize/upscale, boost contrast, sharpen.
- phash(): 64-bit DCT perceptual hash (signed BIGINT) for the dedup cache.
- blur_score() / select_best_frames(): pick usable, diverse frames from video.

Uses OpenCV (already a project dependency). No network, no state.
"""

import cv2
import numpy as np

_MAX_SIDE = 1280  # cap longest side -> bounds vision token cost
_MIN_SIDE = 512   # upscale anything smaller -> helps low-res screenshots
_HASH_BITS = 64
_HASH_MASK = (1 << _HASH_BITS) - 1


def _decode(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes")
    return img


def blur_score(image_bytes: bytes) -> float:
    """Variance of the Laplacian. Higher = sharper; < ~60 tends to be blurry."""
    gray = cv2.cvtColor(_decode(image_bytes), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _crop_letterbox(img: np.ndarray, thresh: int = 18) -> np.ndarray:
    """Remove near-black bars (letterbox/pillarbox) so the subject fills the frame."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = gray > thresh
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return img
    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    return img[r0 : r1 + 1, c0 : c1 + 1]


def preprocess(image_bytes: bytes) -> bytes:
    """Crop bars -> resize/upscale -> CLAHE contrast -> unsharp mask -> JPEG q90."""
    img = _crop_letterbox(_decode(image_bytes))

    short = min(img.shape[:2])
    if short < _MIN_SIDE:
        s = _MIN_SIDE / short
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)

    long = max(img.shape[:2])
    if long > _MAX_SIDE:
        s = _MAX_SIDE / long
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)  # contrast on luminance only
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    blurred = cv2.GaussianBlur(img, (0, 0), 3)  # unsharp mask
    img = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else image_bytes


def safe_preprocess(image_bytes: bytes) -> bytes:
    """preprocess() that never raises -> returns original bytes on any failure."""
    try:
        return preprocess(image_bytes)
    except Exception:
        return image_bytes


def phash(image_bytes: bytes) -> int:
    """64-bit DCT perceptual hash, returned as a SIGNED 64-bit int (Postgres BIGINT)."""
    gray = cv2.cvtColor(_decode(image_bytes), cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)[:8, :8]
    med = np.median(dct.flatten()[1:])  # skip DC term
    h = 0
    for bit in (dct > med).flatten():
        h = (h << 1) | int(bit)
    return h - (1 << (_HASH_BITS - 1))  # unsigned -> signed BIGINT range


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & _HASH_MASK).count("1")


def select_best_frames(frames: list[bytes], k: int = 4) -> list[bytes]:
    """Drop blurry/black frames, keep the K sharpest that are visually diverse."""
    scored = [(f, blur_score(f)) for f in frames]
    usable = [(f, s) for f, s in scored if s > 60.0] or scored
    usable.sort(key=lambda x: x[1], reverse=True)

    chosen: list[bytes] = []
    hashes: list[int] = []
    for f, _ in usable:
        ph = phash(f)
        if all(hamming(ph, h) > 10 for h in hashes):
            chosen.append(f)
            hashes.append(ph)
        if len(chosen) == k:
            break
    return chosen or [f for f, _ in usable[:k]]
