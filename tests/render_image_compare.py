"""Measure aligned engine PNGs; metrics are evidence, not a fidelity pass gate.

Requires Pillow. No resizing, registration, or licensed assets are included.
Use --region LEFT TOP RIGHT BOTTOM to exclude animated actors, weapons or GUIs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def compare(native_path, web_path, region=None, difference_path=None):
    with Image.open(native_path) as n, Image.open(web_path) as w:
        if n.size != w.size:
            raise ValueError(f"Capture sizes differ: {n.size} vs {w.size}")
        size = n.size
        region = region or (0, 0, *size)
        left, top, right, bottom = region
        if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
            raise ValueError(f"Region {region} is outside capture {size}")
        native = n.convert("RGB").crop(region)
        web = w.convert("RGB").crop(region)
    difference = ImageChops.difference(native, web)
    error = ImageStat.Stat(difference).mean
    nmean, wmean = ImageStat.Stat(native).mean, ImageStat.Stat(web).mean
    red, green, blue = difference.split()
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    above_ten = sum(maximum.histogram()[11:])
    if difference_path:
        # Fourfold contrast aids inspection; reported metrics use original bytes.
        difference.point(lambda v: min(255, v * 4)).save(difference_path)
    return {
        "native": str(Path(native_path).resolve()),
        "web": str(Path(web_path).resolve()),
        "native_sha256": hashlib.sha256(Path(native_path).read_bytes()).hexdigest(),
        "web_sha256": hashlib.sha256(Path(web_path).read_bytes()).hexdigest(),
        "capture_size": size,
        "region": region,
        "rgb_mean_absolute_error": sum(error) / 3,
        "rgb_signed_mean_web_minus_native": [w - n for n, w in zip(nmean, wmean)],
        "fraction_pixels_max_channel_error_above_10": above_ten / (native.width * native.height),
        "interpretation": "Aligned pixel differences; no pass threshold. Animation, texture quality and camera state must be checked separately.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native")
    parser.add_argument("web")
    parser.add_argument("--region", nargs=4, type=int)
    parser.add_argument("--difference", help="Save a 4x contrast difference PNG")
    args = parser.parse_args()
    try:
        print(json.dumps(compare(args.native, args.web, args.region, args.difference), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Comparison failed: {error}\n")
