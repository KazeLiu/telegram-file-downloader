"""Local-only image features and standard SSIM for manual duplicate review."""
from __future__ import annotations

import hashlib
import warnings
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImageOps

from .storage import file_version

ALGORITHM = "dct64-white-exif-ssim1600-v1"
MAX_EDGE = 1600
_DCT = np.cos(np.pi / 32 * (np.arange(32) + .5) * np.arange(8)[:, None])
_GAUSSIAN = np.exp(-np.arange(-5, 6, dtype=np.float64) ** 2 / (2 * 1.5 ** 2))
_GAUSSIAN /= _GAUSSIAN.sum()


def verify_file(file, version):
    if not file.is_file() or file_version(file.stat()) != version:
        raise ValueError("图片已变化或移走，请重新扫描")


@contextmanager
def opened_image(file):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(file) as original:
            # Multi-frame images use their first frame; transparency is composited on white.
            ImageOps.exif_transpose(original, in_place=True)
            if "A" in original.getbands() or "transparency" in original.info:
                with original.convert("RGBA") as rgba, Image.new("RGBA", original.size, "white") as background:
                    background.alpha_composite(rgba)
                    rgb = background.convert("RGB")
            else:
                rgb = original.convert("RGB")
            try:
                yield rgb
            finally:
                rgb.close()


def features(file, version, thumbnail):
    verify_file(file, version)
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with opened_image(file) as image:
        width, height = image.size
        sample = np.asarray(image.resize((32, 32), Image.Resampling.LANCZOS).convert("L"), dtype=np.float64)
        coefficients = (_DCT @ sample @ _DCT.T).ravel()
        median = np.median(coefficients[1:])
        bits = coefficients > median
        bits[0] = False
        phash = sum(int(bit) << index for index, bit in enumerate(bits))
        image.thumbnail((480, 480), Image.Resampling.LANCZOS)
        temporary = thumbnail.with_suffix(".tmp")
        image.save(temporary, format="JPEG", quality=85)
        verify_file(file, version)
        temporary.replace(thumbnail)
    return dict(width=width, height=height, digest=digest, phash=f"{phash:016x}")


def _blur(values):
    result = values
    for axis in (1, 0):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (5, 5)
        padded = np.pad(result, pad, mode="reflect" if result.shape[axis] > 1 else "edge")
        output = np.zeros_like(result)
        for offset, weight in enumerate(_GAUSSIAN):
            section = [slice(None), slice(None)]
            section[axis] = slice(offset, offset + result.shape[axis])
            output += weight * padded[tuple(section)]
        result = output
    return result


def similarity(left_file, left, right_file, right):
    verify_file(left_file, left["version"])
    verify_file(right_file, right["version"])
    if left["digest"] == right["digest"]:
        return 1.0
    aspect_a = left["width"] / left["height"]
    aspect_b = right["width"] / right["height"]
    if abs(aspect_a - aspect_b) / max(aspect_a, aspect_b) > .005:
        raise ValueError("宽高比不同，未计算 SSIM")
    target = min(((left["width"], left["height"]), (right["width"], right["height"])),
                 key=lambda size: (size[0] * size[1], *size))
    scale = min(1, MAX_EDGE / max(target))
    target = tuple(max(1, round(value * scale)) for value in target)
    arrays = []
    for file in (left_file, right_file):
        with opened_image(file) as image:
            arrays.append(np.asarray(image.resize(target, Image.Resampling.LANCZOS).convert("L"), dtype=np.float64))
    a, b = arrays
    mean_a, mean_b = _blur(a), _blur(b)
    variance_a = np.maximum(0, _blur(a * a) - mean_a * mean_a)
    variance_b = np.maximum(0, _blur(b * b) - mean_b * mean_b)
    covariance = _blur(a * b) - mean_a * mean_b
    score = ((2 * mean_a * mean_b + 6.5025) * (2 * covariance + 58.5225)
             / ((mean_a * mean_a + mean_b * mean_b + 6.5025) * (variance_a + variance_b + 58.5225)))
    verify_file(left_file, left["version"])
    verify_file(right_file, right["version"])
    return float(score.mean())


def group_images(records, distance, cancelled):
    """Union exact matches and BK-tree neighbours without enumerating every image pair."""
    parents = {record["id"]: record["id"] for record in records}

    def find(item):
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def join(left, right):
        parents[find(right)] = find(left)

    tree, hashes = None, {}
    for record in records:
        if cancelled.is_set():
            return None
        item, value = record["id"], int(record["phash"], 16)
        if record["digest"] in hashes:
            join(item, hashes[record["digest"]])
        hashes[record["digest"]] = item
        pending = [tree] if tree else []
        while pending:
            node = pending.pop()
            delta = (value ^ node[0]).bit_count()
            if delta <= distance:
                join(item, node[1])
            pending.extend(child for edge, child in node[2].items() if delta - distance <= edge <= delta + distance)
        if tree is None:
            tree = (value, item, {})
        else:
            node = tree
            while True:
                delta = (value ^ node[0]).bit_count()
                if delta == 0:
                    break
                if delta not in node[2]:
                    node[2][delta] = (value, item, {})
                    break
                node = node[2][delta]
    groups = {}
    for item in parents:
        groups.setdefault(find(item), []).append(item)
    return [members for members in groups.values() if len(members) > 1]
