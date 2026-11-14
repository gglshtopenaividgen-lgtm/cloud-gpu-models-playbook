#!/usr/bin/env python3
"""
Unit Tests for Web Search Orchestrator:
- WebContentDistiller (Boilerplate removal, cookie banner stripping, clean Markdown extraction)
"""

import sys
import unittest
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from content_distiller import WebContentDistiller, DistillationResult


class TestWebContentDistiller(unittest.TestCase):
    def setUp(self):
        self.distiller = WebContentDistiller()

    def test_distill_strips_boilerplate_and_scripts(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Technical Article</title><style>.banner{color:red}</style></head>
        <body>
            <header><nav><a href="/home">Home</a><a href="/about">About</a></nav></header>
            <div class="cookie-banner">Accept cookies to continue</div>
            <main>
                <article>
                    <h1>Distributed Consensus in Raft</h1>
                    <p>Raft is a consensus algorithm designed as an alternative to Paxos. It was meant to be more understandable.</p>
                    <p>Leader election ensures that at most one candidate can win the election in a given term.</p>
                </article>
            </main>
            <footer><p>Copyright 2026 Company Inc</p></footer>
            <script>console.log("analytics tracking");</script>
        </body>
        </html>
        """
        result = self.distiller.distill(html)
        self.assertEqual(result.title, "Test Technical Article")
        self.assertIn("Distributed Consensus in Raft", result.markdown)
        self.assertIn("Leader election ensures", result.markdown)
        self.assertNotIn("Accept cookies to continue", result.markdown)
        self.assertNotIn("analytics tracking", result.markdown)
        self.assertNotIn("Home", result.markdown)
        self.assertGreater(result.word_count, 15)


if __name__ == "__main__":
    unittest.main()
