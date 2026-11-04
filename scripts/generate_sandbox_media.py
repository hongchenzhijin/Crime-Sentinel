"""Create the images attached to sandbox posts.

With MODEL_API_KEY set, images are generated with Meta's muse-image-1.0 ($0.01 per image).
Without a key, simple labelled placeholder PNGs are drawn locally (requires Pillow).
All imagery is fictional, abstract and non-violent: no weapons, no real people.

Usage: python scripts/generate_sandbox_media.py [--placeholder]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.muse import MuseClient, MuseError  # noqa: E402

OUT = ROOT / "frontend" / "public" / "sandbox"
IMAGES = {
    "fan_edit.png": (
        "Moody stylised digital fan-edit collage: a faceless hooded silhouette seen from behind with a glowing halo, "
        "black ribbons, the word LEGEND in gothic lettering, dark purple and black palette, grainy aesthetic. "
        "No weapons, no blood, no real person.",
        ("#1d1428", "#6250d6", "LEGEND"),
    ),
    "shrine.png": (
        "Small bedroom desk shrine at night: lit candles, black roses, and a framed printed faceless silhouette with "
        "a hand-drawn halo, warm dim light, phone-camera photo look. No weapons, no blood, no real person.",
        ("#2a1d12", "#eda100", "candles until friday"),
    ),
}


def placeholder(path: Path, bg: str, accent: str, label: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (800, 800), bg)
    d = ImageDraw.Draw(img)
    d.ellipse((300, 140, 500, 200), outline=accent, width=6)                     # halo
    d.ellipse((330, 210, 470, 350), fill="#0b0b0b")                              # head silhouette
    d.polygon([(250, 640), (400, 330), (550, 640)], fill="#0b0b0b")              # hooded body
    try:
        font = ImageFont.truetype("georgia.ttf", 64)
        small = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = small = ImageFont.load_default()
    d.text((400, 700), label, fill=accent, font=font, anchor="mm")
    d.text((400, 770), "SYNTHETIC SANDBOX IMAGE", fill="#9a978e", font=small, anchor="mm")
    img.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placeholder", action="store_true", help="draw placeholders even if Muse is configured")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    muse = MuseClient(force_offline=args.placeholder)
    for name, (prompt, (bg, accent, label)) in IMAGES.items():
        path = OUT / name
        if muse.enabled:
            try:
                path.write_bytes(muse.generate_image(prompt))
                print(f"muse-image-1.0 -> {path}")
                continue
            except MuseError as exc:
                print(f"Muse image generation failed for {name} ({exc}); drawing placeholder")
        placeholder(path, bg, accent, label)
        print(f"placeholder -> {path}")


if __name__ == "__main__":
    main()
