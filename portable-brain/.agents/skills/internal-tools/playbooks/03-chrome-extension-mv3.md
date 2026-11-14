# Playbook 03: Chrome Manifest V3 Extension & Bridge Engineering

> **Authority on Chrome MV3 Architecture, Ephemeral Service Workers, Offscreen Documents, and Agent-to-Browser Bridges.**

---

## 1. Manifest V3 Core Architectural Guardrails

### A. Manifest Declaration (`manifest.json`)
```json
{
  "manifest_version": 3,
  "name": "Argon Agent Bridge",
  "version": "1.0.0",
  "description": "Bi-directional bridge connecting local AI agents to Chrome browser tabs.",
  "permissions": [
    "tabs",
    "debugger",
    "storage",
    "offscreen"
  ],
  "host_permissions": [
    "https://gemini.google.com/*",
    "https://aistudio.google.com/*"
  ],
  "background": {
    "service_worker": "background.js",
    "type": "module"
  }
}
```

---

## 2. Crucial MV3 Patterns & Lessons Learned

### A. Ephemeral Service Worker State Persistence
- Service workers terminate after ~30 seconds of inactivity.
- **Rule**: NEVER store session state, authentication tokens, or tab maps in top-level memory variables (`let state = {}`).
- **Fix**: Persist state to `chrome.storage.session` (in-memory, lives until browser close) or `chrome.storage.local`.

### B. Overcoming Background Tab Timer Throttling
- **The Defect**: Chrome aggressively throttles `setTimeout` and `setInterval` in background or occluded tabs (from 1ms up to 1,000ms - 60,000ms), causing DOM evaluation and polling loops to hang.
- **The Invariant**: Always bring the target tab to the front before initiating multi-step asynchronous evaluations:
  ```python
  driver._call_api("/command", {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "Page.bringToFront"}})
  ```

### C. Offscreen Documents for DOM, Audio & WebSockets
- In MV3, service workers lack access to DOM APIs (`document`, `window`, `AudioContext`, `DOMParser`).
- **Rule**: When parsing raw HTML strings, synthesizing audio, or maintaining persistent WebSocket connections that outlive the 30s service worker lifecycle, spawn an **Offscreen Document**:
  ```javascript
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['DOM_PARSER', 'AUDIO_PLAYBACK', 'WEB_RTC'],
    justification: 'Agent WebSocket relay and audio synthesis'
  });
  ```

### D. Content Scripts & Isolated Worlds
- Content scripts run in an isolated JavaScript execution context. They can access the page DOM but NOT page-level global variables (e.g. Angular/React internal states).
- **Rule**: To bypass CSP or access page globals directly, inject snippets via CDP `Runtime.evaluate` or dispatch trusted CDP events with `isTrusted: true`.
