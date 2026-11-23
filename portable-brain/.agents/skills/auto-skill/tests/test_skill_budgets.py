import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

CANONICAL_SKILLS = [
    "auto-skill",
    "browser-operator",
    "deep-thinking",
    "document-forge",
    "exhaustive-audit-and-repair",
    "external-resource",
    "full-sync",
    "hermes-agent-core",
    "internal-tools",
    "offload",
    "rea",
    "ui-design-engine",
    "web-search-orchestrator",
]

SKILLS_DIR = Path(__file__).resolve().parents[2]


class SkillBudgetAndQualityTests(unittest.TestCase):
    def test_all_13_canonical_skills_exist(self):
        """Verify all 13 canonical skills exist in Central Brain."""
        for skill_name in CANONICAL_SKILLS:
            skill_path = SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(skill_path.exists(), f"Missing SKILL.md for {skill_name} at {skill_path}")

    def test_skill_byte_budgets(self):
        """Verify every canonical SKILL.md is strictly <= 7,200 bytes (target <= 7,000 bytes)."""
        for skill_name in CANONICAL_SKILLS:
            skill_path = SKILLS_DIR / skill_name / "SKILL.md"
            size = skill_path.stat().st_size
            self.assertLessEqual(
                size,
                7200,
                f"Skill '{skill_name}' exceeds 7,200 bytes budget: {size} bytes"
            )

    def test_yaml_frontmatter(self):
        """Verify valid YAML frontmatter with 'name' and 'description'."""
        for skill_name in CANONICAL_SKILLS:
            skill_path = SKILLS_DIR / skill_name / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---"), f"{skill_name} missing leading YAML '---'")
            
            # Extract frontmatter block
            parts = text.split("---", 2)
            self.assertGreaterEqual(len(parts), 3, f"{skill_name} has invalid YAML fence structure")
            fm = parts[1]
            
            # Check name
            name_match = re.search(r"^name:\s*([^\r\n]+)", fm, re.MULTILINE)
            self.assertIsNotNone(name_match, f"{skill_name} missing 'name' in frontmatter")
            self.assertEqual(name_match.group(1).strip().strip("\"'"), skill_name)
            
            # Check description
            desc_match = re.search(r"^description:\s*([^\r\n]+)", fm, re.MULTILINE)
            self.assertIsNotNone(desc_match, f"{skill_name} missing 'description' in frontmatter")
            self.assertTrue(len(desc_match.group(1).strip()) > 10, f"{skill_name} description too short")

    def test_step_0_overlay_reference(self):
        """Verify every SKILL.md has Step-0 overlay reference."""
        for skill_name in CANONICAL_SKILLS:
            skill_path = SKILLS_DIR / skill_name / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            has_overlay = ("resolve_skill_overlay.py" in text) or ("skill_overlays/" in text)
            self.assertTrue(has_overlay, f"{skill_name} missing Step-0 overlay reference")

    def test_no_stale_leaks(self):
        """Verify zero stale leaks ('6 Google One AI Premium', '6 profiles', 'PJCT/hi', 'char_minjun_neutral', 'Solo Leveling')."""
        forbidden_patterns = [
            (r"6\s+Google\s+One\s+AI\s+Premium", "Stale '6 Google One AI Premium' leak"),
            (r"6\s+profiles", "Stale '6 profiles' leak"),
            (r"PJCT[\\/]hi", "Hardcoded project leak 'PJCT/hi'"),
            (r"char_minjun_neutral", "Hardcoded asset leak 'char_minjun_neutral'"),
            (r"Solo\s+Leveling", "Trademarked brand leak 'Solo Leveling'"),
        ]
        for skill_name in CANONICAL_SKILLS:
            skill_path = SKILLS_DIR / skill_name / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            for pattern, desc in forbidden_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                self.assertEqual(len(matches), 0, f"{skill_name} contains {desc}: {matches}")

    def test_relative_reference_links_exist(self):
        """Verify every relative references/ link points to an actual file on disk."""
        link_pattern = re.compile(r"\[([^\]]+)\]\((references/[^)]+)\)")
        for skill_name in CANONICAL_SKILLS:
            skill_dir = SKILLS_DIR / skill_name
            skill_path = skill_dir / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            links = link_pattern.findall(text)
            for label, rel_link in links:
                target_file = (skill_dir / rel_link).resolve()
                self.assertTrue(
                    target_file.exists(),
                    f"Broken link in {skill_name}/SKILL.md: '{rel_link}' does not exist on disk at {target_file}"
                )

    def test_sync_catalog_does_not_inject_into_auto_skill(self):
        """Verify sync_catalog.py does NOT re-inject the 51-row catalog into auto-skill/SKILL.md."""
        auto_skill_md = SKILLS_DIR / "auto-skill" / "SKILL.md"
        size_before = auto_skill_md.stat().st_size
        
        # Run sync_catalog.py
        sync_script = SKILLS_DIR / "auto-skill" / "scripts" / "sync_catalog.py"
        res = subprocess.run([sys.executable, str(sync_script)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"sync_catalog.py failed: {res.stderr}")
        
        size_after = auto_skill_md.stat().st_size
        self.assertEqual(size_before, size_after, f"auto-skill/SKILL.md was modified by sync_catalog.py! (size: {size_before} -> {size_after})")
        self.assertLessEqual(size_after, 7200, "auto-skill/SKILL.md exceeds 7200 bytes after catalog sync")
        
        # Verify references/catalog.md and skill_registry.json were updated
        catalog_ref = SKILLS_DIR / "auto-skill" / "references" / "catalog.md"
        self.assertTrue(catalog_ref.exists())
        self.assertIn("Complete Agent Skills Catalog", catalog_ref.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
