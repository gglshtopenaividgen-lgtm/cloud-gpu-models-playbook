# Modern AI Browser Automation Landscape & Framework Benchmarks (2025–2026)

> **Scope**: Universal Browser Operator Architecture (`v3.1.0` -> `v3.2+`)  
> **Source**: Antigravity Multi-Engine Survey (`Nov 2026`) + Live Production Field Lessons (`ecariculal`)  
> See full deep dive in [`ecariculal/OPEN_SOURCE_BROWSER_AUTOMATION_RESEARCH.md`](file:///./ecariculal/OPEN_SOURCE_BROWSER_AUTOMATION_RESEARCH.md).

---

## 1. Open-Source Browser Agents, CLIs, MCPs & Stealth Comparison Matrix

| Tool / Project | Paradigm | Token Efficiency / Speed | Key Architectural Advantage | Primary Limitation |
|---|---|---|---|---|
| **Browser-Use + `browser-harness`** (`120k+★`, MIT) | Python REPL daemon + CDP | **2.1M tokens** (BU Bench V2.1, \$0.042/run) | Persistent Python REPL (`agent_helpers.py`), `Emulation.setFocusEmulationEnabled` for background tabs, v1.0 screenshot judge | Whole-browser debug approval on Chrome 144+; Python REPL centric |
| **Stagehand v3 / v4** (`20k+★`, MIT) | Hybrid code + `.act()` / `.extract()` / `.observe()` | **44.11% faster** iframes/shadow DOM vs v2 (up to 80% cached) | Dropped Playwright for **raw CDP driver**; `observe()` isolates secrets from LLM; `selfHeal` selector cache | Coding SDK; managed action cache tied to Browserbase |
| **Vercel `agent-browser`** (Apache-2.0) | Native Rust CLI + CDP daemon | **3.3M tokens** (fast CLI loops, no Node) | Compact `@e1` AX refs; fail-loud `elementFromPoint` occlusion check; AES-256-GCM auth vault; domain allowlists; `network route`; WebMCP | Chromium-only; requires CLI runtime |
| **Midscene.js** (`15k+★`, MIT) | VLM GUI Agent (Web/Mobile/Desktop) | Medium–High (vision), cut 45%+ via cache | `Instant Actions` (`aiTap`); `deepThink` coarse-to-crop zoom; 2-tier `.cache.yaml` with non-poisoning fallback | VLM latency on cache misses; XPaths fragile on layout changes |
| **Skyvern & Skyvern MCP** (`21k+★`) | Vision LLM + Playwright (35 MCP tools) | High token/latency on repeat runs | Immune to obfuscated DOM; **native TOTP/2FA**, CAPTCHA & file hooks | Expensive for repetitive high-throughput workflows |
| **Magnitude (`browser-agent`)** (`4.1k★`, Apache-2.0) | Dual-agent Vision (`Planner + Executor`) | Fast visual execution via Moondream/Qwen-VL | **94% WebVoyager**; separates frontier planner from lightweight VLM executor | Visual-only (no text-DOM frugality) |
| **Alibaba PageAgent** (MIT) | In-page JS copilot (`FlatDomTree`) | Near-zero infra overhead | **DOM Dehydration (`FlatDomTree`)** runs text models inside live authenticated web UIs | Multi-origin control needs companion extension |
| **Nanobrowser** (`14k★`, Apache-2.0) | Chrome MV3 Extension (BYOK) | Multi-model cost routing | **Planner / Navigator / Validator** split; preflight dispatch; human-handover guard | Interactive extension side-panel focused |
| **`playwright-cli` vs `playwright-mcp`** | CLI+SKILLs vs MCP AX Server | **4–10x fewer tokens** on CLI (`4.4M` MCP) | Microsoft officially favors CLI+SKILLs over streaming stale MCP AX trees | Stock Playwright leaks `Runtime.enable` without stealth patches |
| **Chrome DevTools MCP** (`32.9k★`) | Puppeteer MCP + CLI | **6.7M tokens** (highest) | Source-mapped stacks, CrUX/perf traces, full HAR network inspection | Built for debugging; no stealth; telemetry flags needed |
| **Steel Browser** (`7.9k★`) | Docker browser sandbox API | Server-managed sessions | Persistent storage/cookies, proxy rotation, live replay viewer, fingerprint stealth | Heavy Docker footprint vs local CLI |
| **Patchright / Rebrowser / Camoufox** | Stealth CDP / C++ Firefox forks | Low overhead | Eliminates `Runtime.enable` & `Console.enable` leaks (`isolatedWorlds` / `alwaysIsolated` / C++ Web API patches) | Patch churn vs upstream; Chrome-specific (Patchright) or Firefox aging checks (Camoufox) |
| **`browser-operator v3.1.0`** (This Skill) | Real Multi-Profile MV3 + Raw CDP CLI + Playwright | **Sub-second**, 0–few hundred tokens | Authentic user Chrome profiles (`Profile 7/8/9/13/14/16`); Shadow DOM/iframe `[id]`; opt-in telemetry; `xhr-spy`; `type-otp`; `upload --direct-cdp`; `optimize-pdf`; `run-goal` | Windows/Local CDP bridge + Playwright Mode A (moving Mode A to Patchright/Rebrowser next) |

---

## 2. Production Patterns Codified in `v3.1.0`

1. **Accessibility Tree & `[id]` Indexing + Viewport Clamping**: Always reject candidate clicks outside `[0..innerWidth, 0..innerHeight]` and prefer ARIA `role`/`name` and numeric `[id]` over brittle generated CSS classes.
2. **Stale Modal Reset Before `DOM.setFileInputFiles`**: Close (`Cancel`) any errored `<Upload maxCount={1}>` modal and reopen fresh before calling `upload --direct-cdp` (`DOM.setFileInputFiles` prioritizing modal file inputs); fall back automatically from `UPLOAD_FILES` timeouts caused by missing `userGesture: true`.
3. **Pre-Upload Session Refresh & Live XHR Spy (`xhr-spy`)**: On reverse proxies that buffer slow uploads (`~1 KB/s` `nginx`) for 5–10+ minutes, call `xhr-spy --install --refresh-url <path>` right before submitting so JWT tokens don't expire mid-transfer with silent Axios `401` restarts from `0%`, and monitor `loaded/total/pct` live.
4. **Sequential CDP `Input.dispatchKeyEvent` + Busy Guard (`type-otp`)**: Never fill 6-box React/Ant Design `<Input.OTP>` inputs with a synchronous JS `for` loop. Check `.ant-btn-loading` / `disabled`, clear partial inputs, focus box `0`, and dispatch char-by-char `Input.dispatchKeyEvent` (`60ms` delay) with 12s cooldowns.
5. **In-Place OCR-Preserving PDF Compression (`optimize-pdf`)**: Replace embedded scan images via PyMuPDF `page.replace_image` + grayscale paper-shadow levels (`65..195`, `max-height 960`, `quality 28`) to cut portal upload times 3x while retaining 100% of OCR text layers.

---

## 3. High-ROI Improvement Roadmap (`v3.2+`)

1. **Persistent Python REPL (`exec <<'PY'`) + `domain_helpers/<host>.py`** *(from `browser-harness`)* — multi-step logic in one process call with reusable per-site helpers.
2. **Background Tab Focus Emulation** *(from `browser-harness`)* — `Emulation.setFocusEmulationEnabled(true)` in `try/finally` so background `--tab` workflows satisfy focus-gated SPAs without stealing desktop focus.
3. **Fail-Loud Occlusion Check** *(from `vercel/agent-browser`)* — run `document.elementFromPoint(x, y)` before clicking and fail explicitly with the blocking modal/overlay selector.
4. **Two-Tier Selector Cache (`selfHeal`) & Non-Poisoning Fallback** *(from `Stagehand v4` + `Midscene.js`)* — cache `(host, path, intent) -> selector`, self-heal on drift, never cache assertions, and drop failed cached flows cleanly.
5. **Compact AX Diffing (`observe --diff`)** *(from `agent-browser` + `PageAgent` `FlatDomTree`)* — stream only incremental UI changes after actions.
6. **Local Encrypted Auth Vault (`--vault`) + Domain Allowlist + Policy Broker** *(from `agent-browser` + `Nanobrowser`)* — keep passwords out of LLM prompts and halt before untrusted redirects or destructive actions.
7. **Patchright / Rebrowser Mode A Stealth Upgrade** — swap vanilla Playwright in `browser_driver.py` for isolated execution-context drivers without default `Runtime.enable`.
8. **WebMCP Discovery, CDP `Fetch.enable` Route Blocking & `--deep-think` Canvas Crop** — block noisy analytics (`route --abort`), invoke WebMCP page tools natively when exposed, and crop canvas regions for sparse icon UIs.
