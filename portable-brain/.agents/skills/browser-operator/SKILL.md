---
name: browser-operator
description: "Generalized browser automation suite uniting Playwright numeric DOM indexing, multi-profile Chrome CDP, and MV3 extension daemon for stealth web navigation with trusted hardware events (isTrusted true), Shadow DOM traversal, virtualized scroll scanning, and 2FA circuit breaking."
---

# Browser Operator — Generalized Browser Automation Suite

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/browser-operator.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill browser-operator`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. Playwright scripts require Windows Python (`/mnt/c/Python314/python.exe < /dev/null`) when run from WSL.

---

## 1. Control Plane Decision Matrix

| Mode | Entry Script | Best For | Invariant / Advantage |
|:---|:---|:---|:---|
| **Mode A: Headless Playwright** | `scripts/browser_driver.py`<br>`scripts/dom_indexer.py` | Public sites, fast unauthenticated scraping, E2E tests | Zero profile side-effects, stealth WebGL spoofing, numeric badge screenshots |
| **Mode B: Multi-Profile Real Chrome** | `scripts/browser_operator.py`<br>`argon_bridge/server.py` | Authenticated portals, cloud consoles, SPAs, local dev | Authentic user Chrome profiles, cookies preserved, trusted CDP events (`127.0.0.1:9229`) |
| **Mode C: Frontier AI Bridges** | `argon_bridge/gemini_brain_driver.py`<br>`argon_bridge/consult_argon.py` | AI Studio Playground (`gemini-4-argon`/`gemini-4-neon`), Gemini Web | Surface-scoped leases, quota-aware profile rotation, Task mode verification |

> **ANTI-GUEST RULE**: Never fall back to ephemeral guest browsers when a task targets logged-in accounts. Always use Mode B (`browser_operator.py --profile "..."`).

---

## 2. Resource Caps & Safety Invariants

- **Resource Ceilings**: Strict maximum of **3 concurrent open browser profiles** and **6 total agent tabs** system-wide.
- **Priority Tiering**: Always drain **Tier-1 Alt Profiles** first across rolling quota windows. **Tier-2 Daily Drivers** are strictly last resort.
- **User Tab Protection**: Agent processes must NEVER close, modify, or steal focus from tabs opened by the human user.
- **Port 9229 Daemon**: Bridge server on `127.0.0.1:9229` auto-boots if not running.

---

## 3. Core CLI Commands

```bash
# 1. Check extension connection and active profiles
python .agents/skills/browser-operator/scripts/browser_operator.py status

# 2. Open new tab with URL reuse
python .agents/skills/browser-operator/scripts/browser_operator.py new-tab "https://example.com" --reuse

# 3. Observe interactive elements (numeric action space [1], [2], ...)
python .agents/skills/browser-operator/scripts/browser_operator.py observe

# 4. Click element by numeric index with trusted hardware event
python .agents/skills/browser-operator/scripts/browser_operator.py click 3

# 5. Extract structured content (markdown, tables, forms)
python .agents/skills/browser-operator/scripts/browser_operator.py read --format markdown
```

---

## 4. References & Extended Guides

- [CLI Reference & Bridge Internals Guide](references/cli_and_bridge_guide.md) — Comprehensive command parameters, CDP event details, and bridge architecture.
- [Browser Tools Landscape](references/browser_tools_landscape.md) — Architectural comparison of browser automation engines.
- [NotebookLM Playbook](references/notebook_playbook.md) — Automated NotebookLM artifact harvesting workflows.