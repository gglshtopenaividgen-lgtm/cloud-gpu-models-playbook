#!/usr/bin/env python3
"""Unit tests for generalized browser-operator CLI, primitives, JS builders, and Mode A driver."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
ARGON_BRIDGE_DIR = SKILL_DIR / "argon_bridge"

for p in (str(SCRIPTS_DIR), str(ARGON_BRIDGE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import browser_operator as bo
import browser_driver as bd


class TestKeyParsingAndProfileNormalization(unittest.TestCase):
    def test_parse_key_combo(self):
        self.assertEqual(bo.parse_key_combo("Enter"), ("Enter", "Enter", 13, 0))
        self.assertEqual(bo.parse_key_combo("Escape"), ("Escape", "Escape", 27, 0))
        self.assertEqual(bo.parse_key_combo("."), (".", "Period", 190, 0))
        self.assertEqual(bo.parse_key_combo("Control+Shift+R"), ("R", "KeyR", ord("R"), 2 | 8))
        self.assertEqual(bo.parse_key_combo("Ctrl+Alt+a"), ("a", "KeyA", ord("A"), 2 | 1))
        self.assertEqual(bo.parse_key_combo("Alt+c"), ("c", "KeyC", ord("C"), 1))
        self.assertEqual(bo.parse_key_combo("Meta+k"), ("k", "KeyK", ord("K"), 4))
        with self.assertRaises(ValueError):
            bo.parse_key_combo("BogusMod+a")

    def test_normalize_profile_name(self):
        self.assertEqual(bo.normalize_profile_name("8"), "Profile 8")
        self.assertEqual(bo.normalize_profile_name("Profile 14"), "Profile 14")
        self.assertEqual(bo.normalize_profile_name("Default"), "Default")
        self.assertEqual(bo.normalize_profile_name("user@example.com"), "user@example.com")
        self.assertIsNone(bo.normalize_profile_name(None))


class TestCLIParserCoverage(unittest.TestCase):
    def test_all_generalized_subcommands_parse(self):
        parser = bo.build_parser()
        cases = [
            ["status"],
            ["tabs", "--profile", "8", "--json"],
            ["new-tab", "https://example.com", "--reuse"],
            ["switch-tab", "--url", "example.com"],
            ["close-tab", "--tab", "42"],
            ["back"],
            ["forward"],
            ["reload", "--bypass-cache"],
            ["goto", "https://example.com", "--wait-until", "settle"],
            ["meta"],
            ["read", "--format", "links", "--selector", "main"],
            ["observe", "--viewport-only", "--filter", "Submit", "--json"],
            ["click", "2", "--button", "right", "--double"],
            ["click", "--role", "button", "--name", "Save"],
            ["hover", "Menu"],
            ["type", "1", "hello world", "--enter"],
            ["fill", "#email", "a@b.com", "--no-clear"],
            ["select", "#country", "US"],
            ["check", "#agree"],
            ["uncheck", "#newsletter"],
            ["wait", "--url", "/dashboard", "--timeout", "5"],
            ["wait", "--gone", ".spinner"],
            ["wait", "--idle"],
            ["scroll", "down", "--amount", "400", "--container", ".a-Cd-oa"],
            ["scroll-find", "--container", ".a-Cd-oa", "--text", "Homework.pdf"],
            ["press", "Control+Shift+R"],
            ["hotkey", "Alt+c"],
            ["accelerator", "drive-upload"],
            ["upload", "file1.pdf", "--intercept", "--trigger", "Upload"],
            ["upload", "file1.pdf", "--direct-cdp"],
            ["xhr-spy", "--install"],
            ["xhr-spy", "--status", "--filter", "submit"],
            ["xhr-spy", "--clear", "--refresh-url", "/curricula/session/refresh"],
            ["type-otp", "123456", "--no-auto-verify"],
            ["type-otp", "--totp-secret", "JBSWY3DPEHPK3PXP", "--selector", ".ant-otp"],
            ["optimize-pdf", "in.pdf", "-o", "out.pdf", "--max-height", "960", "--quality", "28"],
            ["dialog", "--dismiss"],
            ["logs", "--enable"],
            ["storage", "--type", "cookies"],
            ["check-auth"],
            ["screenshot", "--badges", "--full-page", "-o", "out.png"],
            ["run-goal", "Test Goal", "--actions", '[{"action":"wait","idle":true}]'],
            ["eval", "document.title"],
        ]
        for argv in cases:
            ns = parser.parse_args(argv)
            self.assertTrue(callable(ns.func), f"Missing handler for {argv}")


class TestInteractionPrimitives(unittest.TestCase):
    def test_perform_click_viewport_clamping_and_single_cdp_dispatch(self):
        resolve_js = bo.build_resolve_element_js("Submit")
        self.assertNotIn("el.click()", resolve_js)

        # Offscreen element rejected unless js_fallback=True
        with mock.patch.object(bo, "eval_tab_js", return_value={"found": True, "inViewport": False, "x": 100, "y": 1400, "text": "Submit"}):
            res = bo.perform_click("Profile 8", 10, target="Submit")
            self.assertFalse(res["ok"])
            self.assertIn("outside viewport", res["error"])

        # In-viewport element dispatches mouseMoved -> mousePressed -> mouseReleased
        with mock.patch.object(bo, "eval_tab_js", return_value={"found": True, "inViewport": True, "x": 200, "y": 300, "text": "Submit"}):
            with mock.patch.object(bo, "cdp_send") as mock_cdp:
                res = bo.perform_click("Profile 8", 10, target="Submit")
                self.assertTrue(res["ok"])
                methods = [c.args[1]["type"] for c in mock_cdp.call_args_list]
                self.assertEqual(methods, ["mouseMoved", "mousePressed", "mouseReleased"])

    def test_perform_check_idempotent(self):
        with mock.patch.object(bo, "eval_tab_js", return_value={"found": True, "inViewport": True, "x": 50, "y": 60, "checked": True, "text": "Agree"}):
            with mock.patch.object(bo, "perform_click") as mock_click:
                res = bo.perform_check("Profile 8", 10, "#agree", desired_state=True)
                self.assertTrue(res["ok"])
                self.assertFalse(res["changed"])
                mock_click.assert_not_called()

        with mock.patch.object(bo, "eval_tab_js", return_value={"found": True, "inViewport": True, "x": 50, "y": 60, "checked": False, "text": "Agree"}):
            with mock.patch.object(bo, "perform_click", return_value={"ok": True}) as mock_click:
                res = bo.perform_check("Profile 8", 10, "#agree", desired_state=True)
                self.assertTrue(res["ok"])
                self.assertTrue(res["changed"])
                mock_click.assert_called_once()


class TestRunGoalAndCircuitBreaker(unittest.TestCase):
    def test_run_goal_halts_on_auth_circuit_breaker(self):
        parser = bo.build_parser()
        args = parser.parse_args(["run-goal", "Mutate", "--actions", '[{"action":"click","text":"Delete"}]', "--profile", "8"])
        with mock.patch.object(bo, "resolve_profile_connection", return_value="Profile 8"):
            with mock.patch.object(bo, "resolve_tab_id", return_value=123):
                with mock.patch.object(bo, "check_auth_circuit_breaker", return_value={"triggered": True, "reasons": ["2FA prompt"]}):
                    with mock.patch.object(bo, "perform_click") as mock_click:
                        rc = bo.cmd_run_goal(args)
                        self.assertEqual(rc, 2)
                        mock_click.assert_not_called()

    def test_run_goal_executes_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "summary.json"
            actions = json.dumps([
                {"action": "goto", "url": "https://example.com"},
                {"action": "click", "text": "Sign in"},
                {"action": "type", "id": 1, "text": "alice", "enter": True},
                {"action": "press", "keys": "Escape"},
            ])
            parser = bo.build_parser()
            args = parser.parse_args(["run-goal", "Login Flow", "--actions", actions, "--profile", "8", "-o", str(out_file)])
            with mock.patch.object(bo, "resolve_profile_connection", return_value="Profile 8"):
                with mock.patch.object(bo, "resolve_tab_id", return_value=123):
                    with mock.patch.object(bo, "check_auth_circuit_breaker", return_value={"triggered": False, "reasons": []}):
                        with mock.patch.object(bo, "execute_browser_command", return_value={"ok": True}):
                            with mock.patch.object(bo, "perform_click", return_value={"ok": True, "x": 10, "y": 20}):
                                with mock.patch.object(bo, "perform_type", return_value={"ok": True, "length": 5}):
                                    with mock.patch.object(bo, "dispatch_cdp_key"):
                                        rc = bo.cmd_run_goal(args)
            self.assertEqual(rc, 0)
            saved = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertTrue(saved["ok"])
            self.assertEqual(len(saved["steps"]), 4)


class TestGeneratedJavaScriptSyntax(unittest.TestCase):
    def test_generated_js_parses_in_node(self):
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node not installed")
        scripts = [
            bo.build_extraction_js(),
            bo.build_extraction_js(root_selector="#main"),
            bo.build_resolve_element_js("2"),
            bo.build_resolve_element_js("#submit"),
            bo.build_resolve_element_js("Save", role="button", name="Save"),
            bo.build_xhr_spy_install_js(),
        ]
        for idx, js in enumerate(scripts):
            proc = subprocess.run([node_bin, "--input-type=commonjs", "-e", f"new Function({json.dumps(js)})"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"JS syntax failed on snippet {idx}: {proc.stderr}")


class TestBackwardCompatibilityExports(unittest.TestCase):
    def test_argon_bridge_and_mode_a_symbols(self):
        import server
        import stealth_input
        self.assertTrue(hasattr(server, "create_app"))
        self.assertTrue(hasattr(stealth_input, "generate_human_curve"))
        self.assertTrue(hasattr(bd.BrowserAgentDriver, "select_id"))
        self.assertTrue(hasattr(bd.BrowserAgentDriver, "hover_id"))
        self.assertTrue(hasattr(bd.BrowserAgentDriver, "extract_content"))

    def test_server_resolve_live_client_prunes_stale_and_picks_freshest(self):
        import server

        class FakeWS:
            def __init__(self, closed: bool):
                self.closed = closed

        orig_clients = dict(server.CONNECTED_CLIENTS)
        try:
            server.CONNECTED_CLIENTS.clear()
            server.CONNECTED_CLIENTS["dead_1"] = {"ws": FakeWS(True), "dir_name": "Profile 7", "email": "a@b.com", "last_ping": 9999.0}
            server.CONNECTED_CLIENTS["stale_2"] = {"ws": FakeWS(False), "dir_name": "Profile 7", "email": "a@b.com", "last_ping": 100.0}
            server.CONNECTED_CLIENTS["fresh_3"] = {"ws": FakeWS(False), "dir_name": "Profile 7", "email": "a@b.com", "last_ping": 500.0}

            cid, client = server._resolve_live_client("Profile 7")
            self.assertEqual(cid, "fresh_3")
            self.assertEqual(client["last_ping"], 500.0)
            self.assertNotIn("dead_1", server.CONNECTED_CLIENTS)
        finally:
            server.CONNECTED_CLIENTS.clear()
            server.CONNECTED_CLIENTS.update(orig_clients)


class TestV31Primitives(unittest.TestCase):
    def test_generate_totp_code_rfc6238(self):
        code, rem = bo.generate_totp_code("JBSWY3DPEHPK3PXP")
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertGreaterEqual(rem, 1)
        self.assertLessEqual(rem, 30)

    def test_type_otp_busy_guard_skips_in_flight(self):
        with mock.patch.object(bo, "eval_tab_js", return_value={"ok": True, "busy": True, "inputCount": 6}):
            with mock.patch.object(bo, "cdp_send") as mock_cdp:
                res = bo.perform_type_otp("Profile 7", 10, code="123456")
                self.assertTrue(res["ok"])
                self.assertEqual(res["status"], "busy_in_flight")
                mock_cdp.assert_not_called()

    def test_type_otp_dispatches_char_by_char_cdp_events(self):
        side_effects = [
            {"ok": True, "busy": False, "inputCount": 6},
            {"found": True, "busy": True, "disabled": False, "inViewport": True, "x": 100, "y": 200},
        ]
        with mock.patch.object(bo, "eval_tab_js", side_effect=side_effects):
            with mock.patch.object(bo, "cdp_send") as mock_cdp:
                res = bo.perform_type_otp("Profile 7", 10, code="654321", delay_ms=10)
                self.assertTrue(res["ok"])
                self.assertEqual(res["status"], "auto_submitted")
                chars = [c.args[1]["text"] for c in mock_cdp.call_args_list if c.args[0] == "Input.dispatchKeyEvent"]
                self.assertEqual(chars, list("654321"))

    def test_upload_direct_cdp_uses_dom_set_file_input_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sample = Path(tmpdir) / "test.pdf"
            sample.write_bytes(b"%PDF-1.4\n%%EOF\n")
            cdp_responses = [
                {"ok": True},  # DOM.enable
                {"ok": True, "result": {"root": {"nodeId": 1}}},  # DOM.getDocument
                {"ok": True, "result": {"nodeId": 99}},  # DOM.querySelector
                {"ok": True},  # DOM.setFileInputFiles
            ]
            with mock.patch.object(bo, "cdp_send", side_effect=cdp_responses) as mock_cdp:
                res = bo.perform_upload("Profile 7", 10, [str(sample)], direct_cdp=True)
                self.assertTrue(res["ok"])
                self.assertEqual(res["tier"], "direct-cdp")
                self.assertEqual(mock_cdp.call_args_list[-1].args[0], "DOM.setFileInputFiles")


if __name__ == "__main__":
    unittest.main()
