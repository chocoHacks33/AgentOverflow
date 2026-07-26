from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter


REGIONS = {
    "logo": [
        (360, 315, 930, 500),  # Agent word
        (20, 390, 380, 690),  # stack mark
    ],
    "mark": [
        (10, 305, 315, 512),  # stack mark
    ],
}


def build_region_mask(width: int, height: int, regions: list[tuple[int, int, int, int]]) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    for left, top, right, bottom in regions:
        mask[max(0, top) : min(height, bottom), max(0, left) : min(width, right)] = True
    return mask


def convert_to_white(source: Path, destination: Path, variant: str, style: str) -> None:
    image = Image.open(source).convert("RGBA")
    pixels = np.array(image, dtype=np.uint8)
    height, width = pixels.shape[:2]
    rgb = pixels[:, :, :3].astype(np.int16)
    alpha = pixels[:, :, 3]
    region = build_region_mask(width, height, REGIONS[variant])

    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    neutral = maximum - minimum < 70
    dark_core = region & (alpha > 8) & neutral & (maximum < 125)
    dark_fill = region & (alpha > 0) & neutral & (maximum < 195)

    if style == "solid":
        # Preserve original antialiasing while changing charcoal strokes to white.
        pixels[dark_fill, :3] = np.array([255, 255, 255], dtype=np.uint8)
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(pixels, mode="RGBA").save(destination, optimize=True)
        return

    # Outline mode removes charcoal interiors while retaining white antialiasing.
    pixels[dark_fill] = np.array([0, 0, 0, 0], dtype=np.uint8)

    core_mask = Image.fromarray((dark_core * 255).astype(np.uint8), mode="L")
    dilated = core_mask.filter(ImageFilter.MaxFilter(9))
    eroded = core_mask.filter(ImageFilter.MinFilter(9))
    outline = ImageChops.subtract(dilated, eroded).filter(
        ImageFilter.GaussianBlur(radius=0.55)
    )

    # Never paint over the orange circuitry or Overflow lettering.
    orange = (
        region
        & (alpha > 8)
        & (rgb[:, :, 0] > 150)
        & (rgb[:, :, 0] > rgb[:, :, 1] * 1.45)
        & (rgb[:, :, 1] < 175)
    )
    outline_values = np.array(outline, dtype=np.uint8)
    outline_values[~region | orange] = 0

    result = pixels.astype(np.float32)
    blend = outline_values.astype(np.float32)[:, :, None] / 255.0
    white = np.full_like(result, 255.0)
    result = white * blend + result * (1.0 - blend)

    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGBA").save(
        destination,
        optimize=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--variant", choices=sorted(REGIONS), required=True)
    parser.add_argument("--style", choices=["outline", "solid"], default="outline")
    args = parser.parse_args()
    convert_to_white(args.source, args.destination, args.variant, args.style)


if __name__ == "__main__":
    main()
