#!/usr/bin/env python3
"""
Unit Tests for Hermes Agent Core:
- HybridMemoryEngine (FTS5 BM25 + Subword TF-IDF + Reciprocal Rank Fusion)
- ContextEngine (AST pruning, token auditing, invariant locking)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from hybrid_memory_engine import ZeroCostHybridMemory, MemoryRecord, CharNGramTFIDF
from context_engine import ContextEngine


class TestCharNGramTFIDF(unittest.TestCase):
    def test_vectorizer_similarity(self):
        vectorizer = CharNGramTFIDF(n_range=(3, 4))
        docs = [
            ("doc1", "The quick brown fox jumps over the lazy dog"),
            ("doc2", "A fast brown fox leaped over a sleepy hound"),
            ("doc3", "PostgreSQL database configuration for Azure Flexible Server"),
        ]
        vectorizer.fit_and_index(docs)
        
        # Searching for fox should rank doc1 and doc2 highest
        results = vectorizer.search("brown fox jumps", top_k=2)
        self.assertGreater(len(results), 0)
        top_id, top_sim = results[0]
        self.assertEqual(top_id, "doc1")
        self.assertGreater(top_sim, 0.2)


class TestHybridMemoryEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.db"
        self.engine = ZeroCostHybridMemory(str(self.db_path))

    def tearDown(self):
        if hasattr(self, 'engine') and self.engine.conn:
            self.engine.conn.close()
        self.temp_dir.cleanup()

    def test_insert_and_hybrid_search(self):
        record1 = MemoryRecord(
            id="rec-001",
            title="Azure PostgreSQL Architecture",
            content="Standard_B1ms 32GB free tier configuration with pgvector enabled.",
            tags="azure, postgres, database",
            metadata={"tier": 2}
        )
        record2 = MemoryRecord(
            id="rec-002",
            title="Cloudflare R2 Object Storage",
            content="Zero egress fees 10GB free tier for storing PDFs and ASTs.",
            tags="cloudflare, r2, storage",
            metadata={"tier": 3}
        )
        self.engine.insert(record1)
        self.engine.insert(record2)
        self.engine.build_vector_index()

        # Query lexical + semantic
        results = self.engine.search("Azure postgres pgvector", limit=2)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].id, "rec-001")
        self.assertIn("rec-001", [r.id for r in results])


class TestContextEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ContextEngine(token_budget=1000)

    def test_audit_tokens(self):
        messages = [
            {"role": "user", "content": "Hello, world!"},
            {"role": "assistant", "content": "This is a test response from the assistant."},
        ]
        tokens = self.engine.audit_tokens(messages)
        self.assertGreater(tokens, 5)

    def test_extract_and_lock_invariants(self):
        sys_prompt = "Never use DeepCoder or DeepInvestigator. Must strictly enforce 44px mobile touch targets."
        user_inst = "port = 7860. Do not overwrite central brain files."
        self.engine.extract_and_lock_invariants(sys_prompt, user_inst)
        self.assertGreater(len(self.engine.hard_invariants), 0)

    def test_prune_python_ast(self):
        code = '''
def complex_function(a: int, b: str) -> bool:
    """Docstring explaining the function."""
    x = 10
    y = 20
    for i in range(x):
        print(i)
    return True
'''
        pruned = self.engine.prune_python_ast(code)
        self.assertIn("def complex_function", pruned)
        self.assertIn("Docstring explaining", pruned)
        self.assertNotIn("for i in range(x):", pruned)


if __name__ == "__main__":
    unittest.main()
