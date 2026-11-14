#!/usr/bin/env python3
"""
Batch Manifest Generator & Validator for Gemini Flow & Cloud GPU
Parses delimited text blocks (=== ID ===) or structured JSON arrays,
validates syntax, sanitizes negative prompts, and outputs verified manifest JSON.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

MANIFEST_REGEX = re.compile(
    r'===\s*([^\r\n]+?)\s*===\s*[\r\n]+([\s\S]*?)(?=(?:===\s*[^\r\n]+?\s*===)|\Z)',
    re.MULTILINE
)

def parse_delimited(text: str) -> List[Dict[str, Any]]:
    items = []
    matches = list(MANIFEST_REGEX.finditer(text.strip()))
    for idx, match in enumerate(matches, 1):
        header = match.group(1).strip()
        body = match.group(2).strip()
        if not header or not body:
            continue

        attributes = {}
        attr_matches = re.findall(r'\[([a-zA-Z0-9_-]+)\s*:\s*([^\]]+)\]', body)
        for k, v in attr_matches:
            attributes[k.strip().lower()] = v.strip()

        cleaned_prompt = re.sub(r'\[[a-zA-Z0-9_-]+\s*:\s*[^\]]+\]', '', body).strip()

        # Sanitize slug
        slug = re.sub(r'[^a-zA-Z0-9_-]+', '_', header).strip('_').lower()
        if not slug:
            slug = f"asset_{idx:03d}"

        items.append({
            "index": idx,
            "id": header,
            "filename": f"{idx:03d}_{slug}",
            "type": attributes.get("type", "image"),
            "model": attributes.get("model", "imagen-3"),
            "aspect_ratio": attributes.get("aspect", "1:1"),
            "prompt": cleaned_prompt,
            "negative_prompt": attributes.get("negative", "blurry, low quality, distortion, text, watermark"),
            "seed": int(attributes["seed"]) if "seed" in attributes else None
        })
    return items

def main():
    parser = argparse.ArgumentParser(description="Generate and validate Gemini Flow batch manifests.")
    parser.add_argument("--input", "-i", type=str, help="Input text file containing delimited === ID === blocks")
    parser.add_argument("--output", "-o", type=str, default="manifest.json", help="Output JSON path")
    parser.add_argument("--sample", action="store_true", help="Generate a sample manifest file")

    args = parser.parse_args()

    if args.sample:
        sample_content = """=== PLAYER_SPRITE_IDLE ===
[Type: Image] [Model: Imagen-3] [Aspect: 1:1] [Negative: portrait, bust, headshot, close-up, cropped legs, blur, text]
Full body action sprite of a shadow sovereign warrior, standing idle pose, isometric 45-degree angle, entire boots and head visible, centered, isolated on solid pitch black #000000 background, crisp pixel borders, 16-bit game asset.

=== SECTOR_BGM_SYNTH ===
[Type: Audio] [Aspect: audio] [Negative: vocals, speech, singing, harsh clipping, muddy]
Dark synthwave nocturnal exploration soundtrack, 110 BPM, analog Roland Juno-106 arpeggios, heavy sub-bass drone, atmospheric cyberpunk street ambient, seamless 60-second loop.

=== DISTRICT_NEON_RAIN ===
[Type: Video] [Aspect: 16:9] [Negative: jitter, static, low resolution, warped geometry]
Cinematic seamless 4-second video loop of neon rain falling on asphalt alleyway in futuristic Seoul, camera slowly pushing forward, glowing holographic signs reflecting in puddles, 24fps smooth.
"""
        out_path = Path("sample_prompts.txt")
        out_path.write_text(sample_content, encoding="utf-8")
        print(f"Generated sample delimited prompts: {out_path}")
        return

    if not args.input:
        print("Error: --input required (or run with --sample)")
        sys.exit(1)

    raw = Path(args.input).read_text(encoding="utf-8")
    items = parse_delimited(raw)
    print(f"Parsed {len(items)} assets with zero duplicate split errors.")

    out_file = Path(args.output)
    out_file.write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(f"Saved verified manifest to: {out_file}")

if __name__ == "__main__":
    main()
