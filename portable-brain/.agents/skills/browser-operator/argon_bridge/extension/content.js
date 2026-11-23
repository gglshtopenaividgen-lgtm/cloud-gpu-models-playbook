// content.js - Universal DOM Helper & Google AI Surface Sentinel

(function () {
  const host = (window.location && window.location.hostname) || "";
  const isGoogleAISurface = /^(?:.*\.)?(gemini\.google\.com|aistudio\.google\.com|labs\.google)$/i.test(host);

  if (isGoogleAISurface) {
    console.log("[ArgonBridge] Content script active on:", window.location.href);
  }

  // 1. Detect Active Google Account Email from Top-Right Avatar (Google AI surfaces only)
  function detectAccountEmail() {
    if (!isGoogleAISurface) return null;
    const avatarEl = document.querySelector(
      'a[aria-label*="Google Account:"], a[aria-label*="Google-Konto:"], img[alt*="@"], [data-email]'
    );
    if (avatarEl) {
      const aria = avatarEl.getAttribute("aria-label") || avatarEl.getAttribute("alt") || avatarEl.getAttribute("data-email") || "";
      const match = aria.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
      if (match) {
        chrome.runtime.sendMessage({ type: "DETECTED_EMAIL", email: match[0] });
        return match[0];
      }
    }
    return null;
  }

  // 2. Quota / Rate-Limit Sentinel (MutationObserver - scoped to Google AI surfaces only)
  const quotaPatterns = [
    /you'?ve reached your limit/i,
    /daily limit reached/i,
    /try again later/i,
    /quota exceeded/i,
    /resource has been exhausted/i,
    /rate limit exceeded/i,
  ];

  let quotaReported = false;
  const observer = new MutationObserver(() => {
    if (!isGoogleAISurface || quotaReported) return;
    const bodyText = document.body ? document.body.innerText : "";
    for (const pattern of quotaPatterns) {
      if (pattern.test(bodyText)) {
        quotaReported = true;
        console.warn("[ArgonBridge] Rate limit / quota banner detected!");
        chrome.runtime.sendMessage({
          type: "QUOTA_EXHAUSTED",
          payload: { url: window.location.href, pattern: pattern.toString() },
        });
        break;
      }
    }
  });

  if (isGoogleAISurface) {
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
      detectAccountEmail();
    } else {
      window.addEventListener("DOMContentLoaded", () => {
        if (document.body) observer.observe(document.body, { childList: true, subtree: true });
        detectAccountEmail();
      });
    }
  }

  // 3. Jev-Ultrafast DOM Indexer Exposed on window
  window.__agyIndexDOM = function () {
    const interactiveSelectors = [
      "button",
      "a[href]",
      'input:not([type="hidden"])',
      "textarea",
      '[role="button"]',
      '[role="textbox"]',
      '[role="combobox"]',
      '[role="option"]',
      "mat-select",
      "[contenteditable='true']",
    ];

    const elements = document.querySelectorAll(interactiveSelectors.join(", "));
    const indexed = [];
    let id = 1;

    elements.forEach((el) => {
      // Check visibility
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(el).visibility === "hidden") {
        return;
      }

      el.setAttribute("data-agy-id", id);
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute("role") || "";
      const aria = el.getAttribute("aria-label") || "";
      const text = (el.innerText || el.value || "").trim().slice(0, 80);

      indexed.push({
        id: id,
        tag: tag,
        role: role,
        aria: aria,
        text: text,
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
      });
      id++;
    });

    return indexed;
  };

  // 4. Stream Completion Observer
  window.__agyWaitStream = function (timeoutSec = 180) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      let lastLength = 0;
      let stableCount = 0;

      const checkInterval = setInterval(() => {
        if (Date.now() - startTime > timeoutSec * 1000) {
          clearInterval(checkInterval);
          reject(new Error("Timeout awaiting stream completion"));
          return;
        }

        // Check if Stop button is still visible
        const stopBtn = document.querySelector('button[aria-label*="Stop" i], button[data-testid*="stop" i]');
        if (stopBtn && stopBtn.offsetParent !== null) {
          // Still generating
          stableCount = 0;
          return;
        }

        // Read response text container
        const responses = document.querySelectorAll('.model-response-text, .response-container, [data-testid="model-response"]');
        const currentText = responses.length > 0 ? responses[responses.length - 1].innerText : "";

        if (currentText.length > 0 && currentText.length === lastLength) {
          stableCount++;
          if (stableCount >= 4) {
            // Text stable for >= 2.0s and no stop button
            clearInterval(checkInterval);
            resolve({ ok: true, text: currentText, length: currentText.length });
          }
        } else {
          lastLength = currentText.length;
          stableCount = 0;
        }
      }, 500);
    });
  };

  // 5. Safe Text Injector
  window.__agyInjectText = function (selector, text) {
    const el = document.querySelector(selector);
    if (!el) return { ok: false, error: "Element not found" };

    el.focus();
    if (el.isContentEditable) {
      el.innerText = text;
    } else {
      el.value = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return { ok: true };
  };
})();
