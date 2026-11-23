# Browser Operator: CLI Reference & Bridge Internals Guide

This guide contains the extended CLI command matrix, profile discovery mechanisms, NotebookLM integration workflows, and extension bridge internals for `browser-operator`.

---

## 1. Full CLI Command Reference

Execute via:
`python .agents/skills/browser-operator/scripts/browser_operator.py <command> [args]`

### Tab & Window Management
- `status`: Check extension connection state, active Chrome profile, and system bridge health (`127.0.0.1:9229`).
- `tabs [--profile <name>]`: List all open tabs across browser profiles.
- `new-tab <url> [--reuse] [--profile <name>]`: Open a new tab (or reuse an existing blank tab if `--reuse` is set).
- `switch-tab <tabId>`: Bring the specified tab to active focus.
- `close-tab <tabId>`: Close the target tab. **Safety guard**: Refuses to close user-owned tabs unless `--force` is specified.
- `back [--tab <tabId>]`: Navigate back in tab history.
- `forward [--tab <tabId>]`: Navigate forward in tab history.
- `reload [--tab <tabId>] [--bypass-cache]`: Reload the target tab.

### DOM Observation & Extraction
- `observe [--tab <tabId>] [--interactive-only]`: Generates numeric interactive element IDs (`[1]`, `[2]`, ...) across main document, Shadow DOM, and iframes.
- `read [--tab <tabId>] [--format markdown|tables|forms|meta|all] [--selector <css>]`: Extracts clean structured content.
- `screenshot [--tab <tabId>] [--out <path>] [--badge-ids]`: Takes a screenshot, optionally rendering numeric element badges for multimodal visual inspection.
- `meta [--tab <tabId>]`: Extracts page title, URL, OpenGraph metadata, and viewport sizing.
- `logs [--tab <tabId>] [--enable|--disable|--clear]`: Streams console errors, uncaught exceptions, and failed network calls.

### Interactions & Input
- `click <id|selector> [--tab <tabId>]`: Dispatches trusted mouse events (`isTrusted: true`) to the target coordinate.
- `type <id|selector> <text> [--tab <tabId>] [--clear]`: Types text into an input field or contenteditable element with simulated keystrokes.
- `select <id|selector> <value> [--tab <tabId>]`: Selects option from dropdown.
- `scroll <up|down|top|bottom|selector> [--amount <px>]`: Scrolls the viewport or target container.
- `upload <id|selector> <filepath>`: Attaches file to input file element via CDP `DOM.setFileInputFiles`.
- `download <url> [--out <dir>]`: Triggers CDP managed download.

---

## 2. Profile Management & Resource Caps

- **Concurrency Ceiling**: Max 3 active Chrome profiles and Max 6 total agent tabs.
- **Priority Tiering**:
  1. Tier-1 Alt Profiles (rotated across rolling quota windows).
  2. Tier-2 Daily Driver Profiles (strictly last resort).
- **User Tab Protection**: Agent commands MUST NOT close or manipulate tabs that were opened by the user.

---

## 3. Bridge Architecture & Server Internals

- Bridge daemon runs on `127.0.0.1:9229` (HTTP/WebSocket server).
- MV3 extension (`Browser operator`) connects via loopback WebSocket.
- Auto-boot logic spawns `argon_bridge/server.py` if no listener is detected on port 9229.
