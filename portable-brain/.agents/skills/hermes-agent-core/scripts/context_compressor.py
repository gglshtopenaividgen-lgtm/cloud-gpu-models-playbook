"""
Hermes Context Compressor (ContextEngine)
Maintains compact, high-signal context digests for complex, multi-turn projects.
Prevents context window bloat while preserving critical operational constraints.
"""

import argparse
import datetime
import os
import re
from pathlib import Path
from typing import Dict, List


def extract_headings_and_invariants(content: str) -> List[str]:
    lines = content.splitlines()
    key_points = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            key_points.append(stripped)
        elif any(k in stripped.lower() for k in ["invariant", "never", "always", "strict", "limit", "port", "rule"]):
            if len(stripped) < 150:
                key_points.append(f"  • {stripped.lstrip('-* ')}")
    return key_points


def compress_context(context_dir: Path, output_file: Path) -> str:
    if not context_dir.exists():
        print(f"[ContextCompressor] Directory not found: {context_dir}")
        return ""

    md_files = list(context_dir.glob("*.md")) + list(context_dir.glob("*.txt"))
    digest_sections = []

    header = f"# Active Context Digest (Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"
    digest_sections.append(header)

    total_orig_bytes = 0
    for file_path in sorted(md_files):
        if file_path.name == output_file.name:
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            total_orig_bytes += len(content)
            points = extract_headings_and_invariants(content)
            if points:
                digest_sections.append(f"### File: `{file_path.name}`")
                digest_sections.append("\n".join(points[:15]))
                digest_sections.append("")
        except Exception as e:
            continue

    digest_content = "\n".join(digest_sections)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(digest_content)

    comp_bytes = len(digest_content)
    ratio = (comp_bytes / total_orig_bytes * 100) if total_orig_bytes > 0 else 100
    print(f"[ContextCompressor] Compressed {total_orig_bytes} bytes down to {comp_bytes} bytes ({ratio:.1f}%) -> {output_file}")
    return digest_content


def main():
    parser = argparse.ArgumentParser(description="Hermes Context Compressor")
    parser.add_argument("--context-dir", default="context", help="Directory containing project context files")
    parser.add_argument("--output", default="context/active_context.md", help="Destination digest file")

    args = parser.parse_args()
    compress_context(Path(args.context_dir), Path(args.output))


if __name__ == "__main__":
    main()
