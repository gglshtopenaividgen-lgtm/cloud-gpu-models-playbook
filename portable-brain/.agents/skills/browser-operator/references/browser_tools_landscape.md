# Modern AI Browser Automation Landscape & Framework Benchmarks

> **Scope**: Universal Browser Operator Architecture  
> **Source**: Antigravity Research 2026

See full comprehensive analysis in [`ecariculal/OPEN_SOURCE_BROWSER_AUTOMATION_RESEARCH.md`](file:///<BRAIN_ROOT>/ecariculal/OPEN_SOURCE_BROWSER_AUTOMATION_RESEARCH.md).

## Key Takeaways for Agents
1. **Never rely on fragile deep CSS selectors**: Prefer Accessibility Tree roles (`role="button"`, `aria-label`) and numbered action space (`[id]`).
2. **Prioritize Keyboard Accelerators**: Complex SPAs like Google Drive, Gmail, Jira, and GitHub have robust keyboard shortcuts (`Alt+C then U`, `Ctrl+Alt+A`, `.` quick actions, `Escape` to close modals) that eliminate coordinate calculation failures.
3. **Viewport Clamping**: Always reject DOM elements with `rect.y > window.innerHeight` or `rect.y < 0` to prevent clicking offscreen menu containers.
4. **Virtualized Scroll Stepping**: For lists rendered via `react-window` or Google Drive `.a-Cd-oa`, increment `.scrollTop` programmatically to bring target rows into the DOM before querying elements.
5. **3-Tier File Upload Matrix**:
   - Tier 1: CDP `DOM.setFileInputFiles` when a static `<input type="file">` exists.
   - Tier 2: Stub `window.showOpenFilePicker = undefined` to force standard file input fallback.
   - Tier 3: Hook `HTMLInputElement.prototype.click` with `DataTransfer` injection + trigger native upload accelerator.
6. **2FA / Auth Circuit Breaker**: When an authenticator popup or CAPTCHA appears, halt mutating actions immediately. Never loop or refresh. Pivot to offline work and prompt the user cleanly.
