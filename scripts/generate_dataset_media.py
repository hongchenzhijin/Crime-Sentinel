"""Create the synthetic images attached to dataset posts, the simulated hash list, and the multimodal eval set.

1. Base images: with MODEL_API_KEY set, scene images are generated with Meta's muse-image-1.0 (~$0.01 each);
   otherwise simple placeholders are drawn. Graphics with text (news card, chart, helpline) are always drawn
   locally, because image models garble text. All imagery is fictional, abstract and non-violent.
2. Two "known" images (a fan edit and a shrine) play the role of imagery already on an industry hash-sharing
   list. Only their PDQ hashes (all 8 rotations/flips) go into data/synthetic/hashlist.json. The originals stay
   in media/originals/ and are never served; the dataset only contains *re-uploads*: cropped, recoloured,
   shrunk, re-compressed, captioned and mirrored variants, plus one heavy crop that PDQ is not expected to match.
3. data/synthetic/media_manifest.json attaches images to posts by their text; load_demo_data.py merges it.
4. data/synthetic/labelled_multimodal_set.json: hand-labelled items where the image changes the meaning.

Usage: python scripts/generate_dataset_media.py [--placeholder]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.agent.muse import MuseClient, MuseError  # noqa: E402

MEDIA = config.MEDIA_DIR
ORIGINALS = MEDIA / "originals"
SAFE = " Fictional, no weapons, no blood, no real people, no text."

SCENES = {  # name -> (muse prompt, placeholder colours)
    "fan_edit": ("Moody stylised digital fan-edit collage: a faceless hooded silhouette seen from behind with a "
                 "glowing halo, black ribbons, dark purple and black palette, grainy aesthetic." + SAFE,
                 ("#1d1428", "#8a7cf0")),
    "shrine": ("Small bedroom desk shrine at night: lit candles, black roses and a framed faceless silhouette with "
               "a hand-drawn halo, warm dim light, phone-camera photo look." + SAFE, ("#2a1d12", "#eda100")),
    "countdown": ("Dark grainy poster background: a faceless silhouette with a halo, black ribbons and a large "
                  "empty space in the middle for a number, edgy aesthetic." + SAFE, ("#120d18", "#d04a6a")),
    "memorial": ("Public memorial at dusk: many candles, white flowers and hand-written cards laid by a fence, "
                 "soft respectful light, community vigil." + SAFE, ("#20283a", "#f2e6c8")),
    "documentary": ("Cinematic documentary poster background: an empty train station platform at night in fog, "
                    "muted blue tones, investigative mood." + SAFE, ("#0e1a24", "#7fb4d6")),
}


def font(size: int, bold: bool = False):
    from PIL import ImageFont

    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def placeholder(bg: str, accent: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 1024), bg)
    d = ImageDraw.Draw(img)
    for i in range(0, 1024, 32):  # texture so PDQ has gradients to work with
        d.line((i, 0, 1024 - i, 1024), fill=accent, width=1)
    d.ellipse((392, 170, 632, 240), outline=accent, width=8)
    d.ellipse((430, 250, 594, 414), fill="#0b0b0b")
    d.polygon([(320, 820), (512, 400), (704, 820)], fill="#0b0b0b")
    return img


def scene(name: str, muse: MuseClient):
    from PIL import Image
    import io

    prompt, (bg, accent) = SCENES[name]
    if muse.enabled:
        try:
            img = Image.open(io.BytesIO(muse.generate_image(prompt))).convert("RGB")
            print(f"  muse-image-1.0 -> {name}")
            return img
        except MuseError as exc:
            print(f"  Muse image generation failed for {name} ({exc}); drawing placeholder")
    print(f"  placeholder -> {name}")
    return placeholder(bg, accent)


def overlay(img, lines: list[tuple[str, int]], box: str = "#000000", y: float = 0.72):
    """Draw caption lines on a translucent band (the text a vision model should read)."""
    from PIL import Image, ImageDraw

    img = img.copy().convert("RGBA")
    band = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    h = sum(s + 16 for _, s in lines) + 40
    top = int(img.height * y)
    d.rectangle((0, top, img.width, top + h), fill=box + "b0")
    cy = top + 20
    for text, size in lines:
        d.text((img.width // 2, cy), text, fill="#ffffff", font=font(size, bold=True), anchor="ma")
        cy += size + 16
    return Image.alpha_composite(img, band).convert("RGB")


def card(title: str, lines: list[str], bg: str, accent: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 1024), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1024, 150), fill=accent)
    d.text((60, 75), title, fill="#ffffff", font=font(64, bold=True), anchor="lm")
    y = 240
    for line in lines:
        d.text((60, y), line, fill="#1b1b1b", font=font(46), anchor="lm")
        y += 80
    d.text((60, 960), "SYNTHETIC DEMO IMAGE", fill="#8a877e", font=font(26), anchor="lm")
    return img


def chart():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 1024), "#ffffff")
    d = ImageDraw.Draw(img)
    d.text((60, 60), "Posts in fandom hashtag communities", fill="#1b1b1b", font=font(44, bold=True))
    d.text((60, 120), "per quarter, 2024-2026 (synthetic study data)", fill="#55534e", font=font(30))
    d.line((100, 860, 960, 860), fill="#1b1b1b", width=3)
    d.line((100, 860, 100, 220), fill="#1b1b1b", width=3)
    for i, v in enumerate([120, 180, 260, 240, 380, 470, 430, 560]):
        x = 140 + i * 102
        d.rectangle((x, 860 - v, x + 70, 860), fill="#2a78d6")
        d.text((x + 35, 880), f"Q{i % 4 + 1}", fill="#55534e", font=font(24), anchor="ma")
    d.text((60, 960), "Figure 2. Source: synthetic research dataset", fill="#8a877e", font=font(26))
    return img


def variants(img, stem: str) -> dict[str, object]:
    """Re-upload transformations of a known image."""
    from PIL import Image, ImageEnhance, ImageOps

    w, h = img.size
    m = int(w * 0.06)
    out = {
        f"{stem}_crop.png": img.crop((m, m, w - m, h - m)).resize((w, h)),
        f"{stem}_recolor.png": ImageEnhance.Brightness(ImageEnhance.Color(img).enhance(0.35)).enhance(1.2),
        f"{stem}_small.png": img.resize((w // 2, h // 2), Image.LANCZOS),
        f"{stem}_caption.png": overlay(img, [("never forget", 72)], y=0.8),
        f"{stem}_mirror.png": ImageOps.mirror(img),
        f"{stem}_heavycrop.png": img.crop((int(w * 0.3), int(h * 0.05), int(w * 0.8), int(h * 0.55))).resize((w, h)),
    }
    return out


def hashlist_entries(path: Path, entry_id: str, label: str) -> list[dict]:
    import numpy as np
    import pdqhash
    from PIL import Image

    hashes, quality = pdqhash.compute_dihedral(np.asarray(Image.open(path).convert("RGB")))
    return [{"id": entry_id, "variant": f"dihedral-{i}",
             "pdq": f"{int(''.join(str(int(b)) for b in h), 2):064x}", "quality": int(quality), "label": label,
             "category": "GLORIFICATION_OR_PRAISE",
             "source": "Simulated industry hash-sharing list (ThreatExchange-style). SYNTHETIC."}
            for i, h in enumerate(hashes)]


# post text prefix -> (image files to cycle through, how many posts get one)
ASSIGN = [
    ("New fan edit of him dropped", ["fan_edit_crop.png", "fan_edit_recolor.png", "fan_edit_small.png",
                                     "fan_edit_jpeg.jpg", "fan_edit_caption.png", "fan_edit_mirror.png",
                                     "fan_edit_heavycrop.png"], 13),
    ("Made a little shrine for him", ["shrine_crop.png", "shrine_recolor.png", "shrine_small.png",
                                      "shrine_jpeg.jpg", "shrine_caption.png"], 8),
    ("lol the Ridgeview shooter memes", ["fan_edit_caption.png", "fan_edit_small.png"], 3),
    ("13 days until the anniversary", ["countdown_13.png"], 1),
    ("Check in on your friends this week", ["helpline.png"], 4),
    ("Don't share fan edits of the perpetrator", ["memorial.png"], 3),
    ("Breaking: authorities confirmed a memorial", ["news_card.png"], 3),
    ("Researchers found hashtag communities", ["research_chart.png"], 2),
    ("New peer-reviewed study", ["research_chart.png"], 1),
    ("Just watched the new documentary", ["documentary.png"], 3),
]

ALT = {
    "fan_edit": "Dark stylised fan edit: a hooded silhouette with a glowing halo and black ribbons.",
    "shrine": "Desk shrine with candles, black roses and a framed silhouette with a halo drawing.",
    "countdown_13.png": "Dark poster of a haloed silhouette with a large number 13 and the words 'days until his day'.",
    "helpline.png": "Graphic: 'Struggling after the news? You are not alone' with crisis line details.",
    "memorial.png": "Candles and flowers at a vigil with the caption 'Remember the victims'.",
    "news_card.png": "News graphic: 'Harlow Station inquiry update' with bullet points.",
    "research_chart.png": "Bar chart of posts in fandom hashtag communities per quarter.",
    "documentary.png": "Documentary poster of a foggy station platform titled 'The Ridgeview Files'.",
}

MULTIMODAL = [
    ("mm_01", "new edit, thoughts?", "mm_fan_edit_crop2.png", "GLORIFICATION_OR_PRAISE",
     "Text is neutral; the image is a fan edit (and a re-upload of a hash-listed image)."),
    ("mm_02", "he looks so peaceful here", "mm_fan_edit_recolor2.png", "GLORIFICATION_OR_PRAISE",
     "Admiring caption on a haloed fan edit of the attacker."),
    ("mm_03", "lighting a candle tonight", "mm_shrine_small2.png", "GLORIFICATION_OR_PRAISE",
     "Same caption as mm_04; the image is a shrine to the attacker."),
    ("mm_04", "lighting a candle tonight", "memorial.png", "PREVENTION_OR_SUPPORT",
     "Same caption as mm_03; the image is a vigil for the victims."),
    ("mm_05", "tick tock", "countdown_13.png", "GLORIFICATION_OR_PRAISE",
     "Celebratory countdown poster; the meaning is only in the image text."),
    ("mm_06", "if this is hitting hard, read this", "helpline.png", "PREVENTION_OR_SUPPORT",
     "Helpline graphic."),
    ("mm_07", "update from the inquiry", "news_card.png", "NEWS_REPORTING", "News graphic."),
    ("mm_08", "figure 2 from our paper", "research_chart.png", "ACADEMIC_OR_RESEARCH", "Research chart."),
    ("mm_09", "watching this tonight", "documentary.png", "NEUTRAL_DISCUSSION", "Documentary poster."),
    ("mm_10", "saw this going around, it's grim", "mm_fan_edit_caption2.png", "NEUTRAL_DISCUSSION",
     "Critical caption sharing a hash-listed image: the image alone must not make it harmful."),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placeholder", action="store_true", help="draw placeholders even if Muse is configured")
    args = parser.parse_args()
    muse = MuseClient(force_offline=args.placeholder)
    MEDIA.mkdir(parents=True, exist_ok=True)
    ORIGINALS.mkdir(parents=True, exist_ok=True)

    print("Base images:")
    base = {name: scene(name, muse) for name in SCENES}
    for name in ("fan_edit", "shrine"):
        base[name].save(ORIGINALS / f"{name}.png")
    files: dict[str, object] = {}
    for stem in ("fan_edit", "shrine"):
        files.update(variants(base[stem], stem))
    for stem in ("fan_edit", "shrine"):
        base[stem].save(MEDIA / f"{stem}_jpeg.jpg", quality=35)
    # Extra re-uploads used only by the multimodal eval set.
    files["mm_fan_edit_crop2.png"] = variants(base["fan_edit"], "x")["x_crop.png"]
    files["mm_fan_edit_recolor2.png"] = variants(base["fan_edit"], "x")["x_recolor.png"]
    files["mm_shrine_small2.png"] = variants(base["shrine"], "x")["x_small.png"]
    files["mm_fan_edit_caption2.png"] = overlay(base["fan_edit"], [("legend", 72)], y=0.8)
    files["countdown_13.png"] = overlay(base["countdown"], [("13", 220), ("DAYS UNTIL HIS DAY", 56)], y=0.45)
    files["memorial.png"] = overlay(base["memorial"], [("Remember the victims", 64)], y=0.8)
    files["documentary.png"] = overlay(base["documentary"], [("THE RIDGEVIEW FILES", 80), ("a documentary", 40)], y=0.7)
    files["helpline.png"] = card("You are not alone", ["Struggling after the news?", "Talk to someone today.",
                                 "Crisis line volunteers are", "available 24/7.", "Check in on your friends."],
                                 "#eef6f0", "#2f8f5b")
    files["news_card.png"] = card("NEWS  |  Harlow Station", ["Inquiry update:", "- No further suspects",
                                  "- Memorial planned for victims", "- Report due next month"], "#f4f4f2", "#b3261e")
    files["research_chart.png"] = chart()
    for name, img in files.items():
        img.save(MEDIA / name)
    print(f"Wrote {len(files) + 2} dataset images to {MEDIA}")

    entries = (hashlist_entries(ORIGINALS / "fan_edit.png", "HL-0001", "Known glorification fan edit (synthetic)")
               + hashlist_entries(ORIGINALS / "shrine.png", "HL-0002", "Known glorification shrine image (synthetic)"))
    config.HASHLIST_PATH.write_text(json.dumps({
        "_note": "SYNTHETIC simulated hash-sharing list. Holds PDQ hashes only (8 rotations/flips per image); "
                 "the images themselves are not distributed.",
        "entries": entries}, indent=1), encoding="utf-8")
    print(f"Wrote {len(entries)} hash-list entries to {config.HASHLIST_PATH}")

    # Keep the sandbox's posted images identical to the hash-listed originals, so the agent observes them too.
    for name in ("fan_edit", "shrine"):
        shutil.copy(ORIGINALS / f"{name}.png", ROOT / "frontend" / "public" / "sandbox" / f"{name}.png")

    posts = json.loads(config.DEMO_POSTS_PATH.read_text(encoding="utf-8"))
    manifest: dict[str, list[dict]] = {}
    for prefix, images, limit in ASSIGN:
        matching = [p for p in posts if p["text"].startswith(prefix) and p["id"] not in manifest][:limit]
        for i, p in enumerate(matching):
            file = images[i % len(images)]
            alt = ALT.get(file) or ALT[file.split("_")[0] if not file.startswith("fan_edit") else "fan_edit"]
            manifest[p["id"]] = [{"file": file, "alt_text": alt}]
    config.MEDIA_MANIFEST_PATH.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"Attached images to {len(manifest)} posts in {config.MEDIA_MANIFEST_PATH}")

    config.MULTIMODAL_EVAL_PATH.write_text(json.dumps([
        {"id": i, "text": t, "language": "en", "media": [f], "label": label, "note": note}
        for i, t, f, label, note in MULTIMODAL], indent=1), encoding="utf-8")
    print(f"Wrote {len(MULTIMODAL)} multimodal eval items to {config.MULTIMODAL_EVAL_PATH}")
    if muse.enabled:
        print(f"Muse usage: {muse.ledger.as_dict()}")


if __name__ == "__main__":
    main()
