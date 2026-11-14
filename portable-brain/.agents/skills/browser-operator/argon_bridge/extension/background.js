// background.js - Browser operator MV3 Service Worker
// Maintains persistent local WebSocket connection to ws://127.0.0.1:9229/ws

const WS_URL = "ws://127.0.0.1:9229/ws";
let ws = null;
let isConnecting = false;
let registeredEmail = null;

// Setup periodic keepalive alarm to prevent MV3 service worker premature sleep
chrome.alarms.create("argon_keepalive", { periodInMinutes: 0.33 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "argon_keepalive") {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    } else {
      ws.send(JSON.stringify({ type: "PING", timestamp: Date.now() }));
    }
  }
});

async function getProfileIdentity() {
  return new Promise((resolve) => {
    chrome.identity.getProfileUserInfo({ accountStatus: "ANY" }, (info) => {
      if (chrome.runtime.lastError || !info || !info.email) {
        // Fallback: check stored or avatar email
        chrome.storage.local.get(["profile_email"], (res) => {
          resolve(res.profile_email || "anonymous_profile");
        });
      } else {
        registeredEmail = info.email;
        chrome.storage.local.set({ profile_email: info.email });
        resolve(info.email);
      }
    });
  });
}

async function getOpenTabsSummary() {
  return new Promise((resolve) => {
    chrome.tabs.query({}, (tabs) => {
      const summary = (tabs || []).map((t) => ({
        id: t.id,
        url: t.url || "",
        title: t.title || "",
        active: t.active,
        windowId: t.windowId,
      }));
      resolve(summary);
    });
  });
}

function connectWebSocket() {
  if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) return;
  isConnecting = true;

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = async () => {
      isConnecting = false;
      const email = await getProfileIdentity();
      const tabs = await getOpenTabsSummary();

      ws.send(
        JSON.stringify({
          type: "REGISTER",
          email: email,
          userAgent: navigator.userAgent,
          tabs: tabs,
          timestamp: Date.now(),
        })
      );
      console.log(`[ArgonBridge] Connected to daemon as ${email}`);
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleDaemonMessage(msg);
      } catch (err) {
        console.error("[ArgonBridge] Error parsing daemon message:", err);
      }
    };

    ws.onclose = () => {
      isConnecting = false;
      ws = null;
      setTimeout(connectWebSocket, 4000);
    };

    ws.onerror = (err) => {
      isConnecting = false;
      console.warn("[ArgonBridge] WebSocket connection error (daemon might be starting)");
    };
  } catch (e) {
    isConnecting = false;
    setTimeout(connectWebSocket, 5000);
  }
}

const attachedTabs = new Set();
const tabTelemetry = new Map(); // tabId -> { enabled: boolean, console: [], networkErrors: [] }
const MAX_TELEMETRY_ENTRIES = 100;

function ensureTelemetryBucket(tabId) {
  if (!tabTelemetry.has(tabId)) {
    tabTelemetry.set(tabId, { enabled: false, console: [], networkErrors: [] });
  }
  return tabTelemetry.get(tabId);
}

function pushTelemetry(arr, item) {
  arr.push(item);
  if (arr.length > MAX_TELEMETRY_ENTRIES) {
    arr.splice(0, arr.length - MAX_TELEMETRY_ENTRIES);
  }
}

chrome.debugger.onDetach.addListener((source) => {
  if (source.tabId) {
    attachedTabs.delete(source.tabId);
    const bucket = tabTelemetry.get(source.tabId);
    if (bucket) bucket.enabled = false;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  attachedTabs.delete(tabId);
  tabTelemetry.delete(tabId);
});

chrome.debugger.onEvent.addListener((source, method, params) => {
  const tabId = source && source.tabId;
  if (!tabId) return;
  const bucket = tabTelemetry.get(tabId);
  if (!bucket || !bucket.enabled) return;

  const ts = Date.now();
  if (method === "Log.entryAdded" && params && params.entry) {
    pushTelemetry(bucket.console, {
      ts,
      source: params.entry.source || "log",
      level: params.entry.level || "info",
      text: (params.entry.text || "").slice(0, 500),
      url: params.entry.url || "",
    });
  } else if (method === "Runtime.consoleAPICalled" && params) {
    const argsText = (params.args || [])
      .map((a) => (a.value !== undefined ? String(a.value) : a.description || a.type || ""))
      .join(" ");
    pushTelemetry(bucket.console, {
      ts,
      source: "console",
      level: params.type || "log",
      text: argsText.slice(0, 500),
      url: "",
    });
  } else if (method === "Runtime.exceptionThrown" && params && params.exceptionDetails) {
    const det = params.exceptionDetails;
    const msg = (det.exception && (det.exception.description || det.exception.value)) || det.text || "Uncaught exception";
    pushTelemetry(bucket.console, {
      ts,
      source: "exception",
      level: "error",
      text: String(msg).slice(0, 500),
      url: det.url || "",
    });
  } else if (method === "Network.responseReceived" && params && params.response) {
    const status = params.response.status;
    if (status >= 400) {
      pushTelemetry(bucket.networkErrors, {
        ts,
        type: params.type || "XHR",
        status,
        statusText: params.response.statusText || "",
        url: (params.response.url || "").slice(0, 300),
      });
    }
  } else if (method === "Network.loadingFailed" && params) {
    pushTelemetry(bucket.networkErrors, {
      ts,
      type: params.type || "Request",
      status: 0,
      errorText: params.errorText || "Loading failed",
      canceled: Boolean(params.canceled),
      requestId: params.requestId || "",
    });
  }
});

function ensureAttached(tabId, callback) {
  const target = { tabId };
  if (attachedTabs.has(tabId)) {
    callback(null);
    return;
  }
  chrome.debugger.attach(target, "1.3", () => {
    if (chrome.runtime.lastError) {
      const err = chrome.runtime.lastError.message || "";
      if (err.includes("already attached")) {
        attachedTabs.add(tabId);
        callback(null);
        return;
      }
      callback(err);
      return;
    }
    attachedTabs.add(tabId);
    callback(null);
  });
}

async function handleDaemonMessage(msg) {
  const reqId = msg.id;
  const action = msg.action;

  if (action === "PING" || msg.type === "PING") {
    ws.send(JSON.stringify({ id: reqId, type: "PONG" }));
    return;
  }

  if (msg.type === "PONG") {
    return;
  }

  // 0. RELOAD_EXTENSION
  if (action === "RELOAD_EXTENSION") {
    ws.send(JSON.stringify({ id: reqId, ok: true }));
    setTimeout(() => chrome.runtime.reload(), 100);
    return;
  }

  // 1. OPEN_TAB
  if (action === "OPEN_TAB") {
    const url = msg.url || "https://aistudio.google.com/prompts/new_chat";
    chrome.tabs.create({ url, active: msg.active !== false }, (tab) => {
      ws.send(JSON.stringify({ id: reqId, ok: true, tabId: tab.id, url: tab.url }));
    });
    return;
  }

  // 1.5. CLOSE_TAB
  if (action === "CLOSE_TAB") {
    const tabId = msg.tabId;
    if (tabId) {
      attachedTabs.delete(tabId);
      tabTelemetry.delete(tabId);
      chrome.tabs.remove(tabId, () => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true }));
        }
      });
    } else {
      ws.send(JSON.stringify({ id: reqId, ok: false, error: "Missing tabId" }));
    }
    return;
  }

  // 1.6. SWITCH_TAB (focus tab by tabId, urlContains, or titleContains)
  if (action === "SWITCH_TAB") {
    chrome.tabs.query({}, (tabs) => {
      let targetTab = null;
      if (msg.tabId) {
        targetTab = (tabs || []).find((t) => t.id === Number(msg.tabId));
      } else if (msg.urlContains) {
        const q = String(msg.urlContains).toLowerCase();
        targetTab = (tabs || []).find((t) => (t.url || "").toLowerCase().includes(q));
      } else if (msg.titleContains) {
        const q = String(msg.titleContains).toLowerCase();
        targetTab = (tabs || []).find((t) => (t.title || "").toLowerCase().includes(q));
      }
      if (!targetTab) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: "Matching tab not found" }));
        return;
      }
      chrome.tabs.update(targetTab.id, { active: true }, (updated) => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
          return;
        }
        if (updated && updated.windowId) {
          chrome.windows.update(updated.windowId, { focused: true }, () => {
            ws.send(JSON.stringify({ id: reqId, ok: true, tabId: updated.id, url: updated.url || "", title: updated.title || "" }));
          });
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true, tabId: targetTab.id, url: targetTab.url || "", title: targetTab.title || "" }));
        }
      });
    });
    return;
  }

  // 1.7. RELOAD_TAB / GO_BACK / GO_FORWARD
  if (action === "RELOAD_TAB") {
    const tabId = msg.tabId;
    chrome.tabs.reload(tabId, { bypassCache: Boolean(msg.bypassCache) }, () => {
      if (chrome.runtime.lastError) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
      } else {
        ws.send(JSON.stringify({ id: reqId, ok: true, tabId }));
      }
    });
    return;
  }

  if (action === "GO_BACK") {
    const tabId = msg.tabId;
    chrome.tabs.goBack(tabId, () => {
      if (chrome.runtime.lastError) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
      } else {
        ws.send(JSON.stringify({ id: reqId, ok: true, tabId }));
      }
    });
    return;
  }

  if (action === "GO_FORWARD") {
    const tabId = msg.tabId;
    chrome.tabs.goForward(tabId, () => {
      if (chrome.runtime.lastError) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
      } else {
        ws.send(JSON.stringify({ id: reqId, ok: true, tabId }));
      }
    });
    return;
  }

  // 2. LIST_TABS
  if (action === "LIST_TABS") {
    const tabs = await getOpenTabsSummary();
    ws.send(JSON.stringify({ id: reqId, ok: true, tabs }));
    return;
  }

  // 3. ATTACH_TAB (CDP)
  if (action === "ATTACH_TAB") {
    ensureAttached(msg.tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
      } else {
        ws.send(JSON.stringify({ id: reqId, ok: true, attached: true, tabId: msg.tabId }));
      }
    });
    return;
  }

  // 4. DETACH_TAB (CDP)
  if (action === "DETACH_TAB") {
    const target = { tabId: msg.tabId };
    attachedTabs.delete(msg.tabId);
    chrome.debugger.detach(target, () => {
      ws.send(JSON.stringify({ id: reqId, ok: true, detached: true }));
    });
    return;
  }

  // 5. CDP_COMMAND
  if (action === "CDP_COMMAND") {
    const tabId = msg.tabId;
    const target = { tabId };
    const method = msg.method;
    const params = msg.params || {};

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, method, params, (result) => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true, result }));
        }
      });
    });
    return;
  }

  // 6. EVAL_DOM (evaluates JS inside tab context via CDP to bypass CSP)
  if (action === "EVAL_DOM") {
    const tabId = msg.tabId;
    const code = msg.code;
    const target = { tabId };

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(
        target,
        "Runtime.evaluate",
        {
          expression: code,
          returnByValue: true,
          awaitPromise: true,
        },
        (result) => {
          if (chrome.runtime.lastError) {
            ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
          } else if (result && result.exceptionDetails) {
            const desc = result.exceptionDetails.exception ? result.exceptionDetails.exception.description : result.exceptionDetails.text;
            ws.send(JSON.stringify({ id: reqId, ok: false, error: desc || "JS Exception" }));
          } else {
            ws.send(JSON.stringify({ id: reqId, ok: true, result: result && result.result ? result.result.value : null }));
          }
        }
      );
    });
    return;
  }

  // 7. TAKE_SCREENSHOT (captures tab viewport via CDP and returns base64 PNG)
  if (action === "TAKE_SCREENSHOT") {
    const tabId = msg.tabId;
    const target = { tabId };

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      const captureParams = { format: msg.format || "png" };
      if ((msg.format || "png") !== "png") {
        captureParams.quality = msg.quality || 85;
      }
      if (msg.fullPage) {
        captureParams.captureBeyondViewport = true;
      }
      chrome.debugger.sendCommand(
        target,
        "Page.captureScreenshot",
        captureParams,
        (result) => {
          if (chrome.runtime.lastError) {
            ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
          } else if (result && result.data) {
            ws.send(JSON.stringify({ id: reqId, ok: true, data: result.data }));
          } else {
            ws.send(JSON.stringify({ id: reqId, ok: false, error: "Failed to capture screenshot data" }));
          }
        }
      );
    });
    return;
  }

  // 8. UPLOAD_FILES (attaches files programmatically via CDP Page.setInterceptFileChooserDialog & DOM.setFileInputFiles)
  if (action === "UPLOAD_FILES") {
    const tabId = msg.tabId;
    const files = msg.files || [];
    const target = { tabId };

    if (!files || files.length === 0) {
      ws.send(JSON.stringify({ id: reqId, ok: false, error: "No files specified" }));
      return;
    }

    const doUpload = async () => {
      let isDone = false;
      const timeoutId = setTimeout(() => {
        if (!isDone) {
          isDone = true;
          chrome.debugger.onEvent.removeListener(onCDPEvent);
          chrome.debugger.sendCommand(target, "Page.setInterceptFileChooserDialog", { enabled: false }, () => {});
          ws.send(JSON.stringify({ id: reqId, ok: false, error: "Timeout waiting for file chooser dialog (15s)" }));
        }
      }, 15000);

      const onCDPEvent = (source, method, params) => {
        if (source.tabId === tabId && method === "Page.fileChooserOpened" && !isDone) {
          isDone = true;
          clearTimeout(timeoutId);
          chrome.debugger.onEvent.removeListener(onCDPEvent);

          const backendNodeId = params.backendNodeId;
          const setParams = { files: files };
          if (backendNodeId) setParams.backendNodeId = backendNodeId;

          chrome.debugger.sendCommand(target, "DOM.setFileInputFiles", setParams, (res) => {
            chrome.debugger.sendCommand(target, "Page.setInterceptFileChooserDialog", { enabled: false }, () => {});
            if (chrome.runtime.lastError) {
              ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
            } else {
              ws.send(JSON.stringify({ id: reqId, ok: true, uploaded: files, count: files.length }));
            }
          });
        }
      };

      chrome.debugger.onEvent.addListener(onCDPEvent);

      // Enable Page and DOM domains first so events fire
      chrome.debugger.sendCommand(target, "Page.enable", {}, () => {
        chrome.debugger.sendCommand(target, "DOM.enable", {}, () => {
          chrome.debugger.sendCommand(target, "Page.setInterceptFileChooserDialog", { enabled: true }, () => {
            if (chrome.runtime.lastError) {
              isDone = true;
              clearTimeout(timeoutId);
              chrome.debugger.onEvent.removeListener(onCDPEvent);
              ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
              return;
            }

            // Click trigger JS (supports custom triggerJs or default Gemini uploader)
            const clickTriggerJs = msg.triggerJs || `
            (async function() {
              const sleep = ms => new Promise(r => setTimeout(r, ms));
              let plusBtn = document.querySelector('button[aria-label="Upload & tools"], button[aria-label*="Upload" i], .simplified-input-menu button');
              if (plusBtn && plusBtn.getAttribute('aria-expanded') !== 'true') {
                plusBtn.click();
                await sleep(350);
              }
              let upBtn = document.querySelector('button[data-test-id="local-images-files-uploader-button"], [aria-label*="Upload files"] button, button[aria-label*="Upload files"]');
              if (!upBtn) {
                const allBtns = Array.from(document.querySelectorAll('button, [role="menuitem"], li'));
                upBtn = allBtns.find(b => {
                  const t = (b.innerText || '').trim().toLowerCase();
                  const a = (b.getAttribute('aria-label') || '').toLowerCase();
                  return t.includes('upload files') || a.includes('upload files') || t.includes('file upload') || a.includes('file upload');
                });
              }
              if (upBtn) {
                const rect = upBtn.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
                upBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
                upBtn.dispatchEvent(new MouseEvent('mousedown', opts));
                upBtn.dispatchEvent(new PointerEvent('pointerup', opts));
                upBtn.dispatchEvent(new MouseEvent('mouseup', opts));
                upBtn.dispatchEvent(new MouseEvent('click', opts));
                try { upBtn.click(); } catch(e) {}
                return { clicked: true };
              }
              return { clicked: false, error: 'Upload files button not found' };
            })()
            `;

            chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: clickTriggerJs, awaitPromise: true, returnByValue: true }, (evalRes) => {
              if (chrome.runtime.lastError) {
                console.warn("[ArgonBridge] Trigger warning:", chrome.runtime.lastError.message);
              }
            });
          });
        });
      });
    };

    chrome.debugger.attach(target, "1.3", () => {
      doUpload();
    });
    return;
  }


  // 9. NAVIGATE_TAB
  if (action === "NAVIGATE_TAB") {
    let tabId = msg.tabId;
    const url = msg.url;
    if (!url) {
      ws.send(JSON.stringify({ id: reqId, ok: false, error: "Missing 'url' parameter" }));
      return;
    }
    const doNav = (tId) => {
      chrome.tabs.update(tId, { url: url }, (updatedTab) => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
          return;
        }
        let completed = false;
        const listener = (tid, changeInfo) => {
          if (tid === tId && changeInfo.status === "complete") {
            completed = true;
            chrome.tabs.onUpdated.removeListener(listener);
            ws.send(JSON.stringify({ id: reqId, ok: true, tabId: tId, url: url, status: "complete" }));
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
        setTimeout(() => {
          if (!completed) {
            completed = true;
            chrome.tabs.onUpdated.removeListener(listener);
            ws.send(JSON.stringify({ id: reqId, ok: true, tabId: tId, url: url, status: "settled_timeout" }));
          }
        }, 12000);
      });
    };

    if (tabId) {
      doNav(tabId);
    } else {
      chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
        const activeTab = (tabs && tabs[0]) || null;
        if (!activeTab) {
          chrome.tabs.create({ url: url, active: true }, (newTab) => {
            ws.send(JSON.stringify({ id: reqId, ok: true, tabId: newTab.id, url: newTab.url, created: true }));
          });
        } else {
          doNav(activeTab.id);
        }
      });
    }
    return;
  }

  // 10. WAIT_FOR_ELEMENT
  if (action === "WAIT_FOR_ELEMENT") {
    const tabId = msg.tabId;
    const selector = msg.selector || "";
    const textContains = msg.textContains || "";
    const timeoutMs = Number(msg.timeoutMs || 10000);
    const target = { tabId };

    const waitJs = `
      (async function() {
        const sel = ${JSON.stringify(selector)};
        const txt = ${JSON.stringify(textContains)}.toLowerCase();
        const maxMs = ${timeoutMs};
        const start = Date.now();
        while (Date.now() - start < maxMs) {
          let el = null;
          if (sel) {
            const found = document.querySelector(sel);
            if (found && found.offsetWidth > 0 && found.offsetHeight > 0) {
              if (!txt || (found.innerText || '').toLowerCase().includes(txt)) {
                el = found;
              }
            }
          } else if (txt) {
            const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], span, div, h1, h2, h3, tr, td, p'));
            el = candidates.find(c => c.offsetWidth > 0 && c.offsetHeight > 0 && (c.innerText || '').toLowerCase().includes(txt));
          }
          if (el) {
            const rect = el.getBoundingClientRect();
            return {
              found: true,
              elapsedMs: Date.now() - start,
              text: (el.innerText || el.value || '').trim().slice(0, 100),
              tag: el.tagName.toLowerCase(),
              x: Math.round(rect.left + rect.width / 2),
              y: Math.round(rect.top + rect.height / 2)
            };
          }
          await new Promise(r => setTimeout(r, 200));
        }
        return { found: false, timeout: true, elapsedMs: maxMs };
      })()
    `;

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: waitJs, awaitPromise: true, returnByValue: true }, (res) => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true, result: res && res.result ? res.result.value : null }));
        }
      });
    });
    return;
  }

  // 11. GET_PAGE_DATA (Universal High-Density Structured Data & Interactive DOM Harvester)
  if (action === "GET_PAGE_DATA") {
    const tabId = msg.tabId;
    const target = { tabId };

    const extractJs = `
      (function() {
        const result = {
          title: document.title || '',
          url: window.location.href,
          readyState: document.readyState,
          hydration: {
            settled: false,
            activeOverlays: 0,
            hasSpinners: false
          },
          kpi_cards: [],
          tables: [],
          markdown_content: '',
          interactive_index: []
        };

        // 1. Hydration check
        const spinners = document.querySelectorAll('.spinner, [role="progressbar"], mat-progress-bar, .loading, .mat-progress-spinner');
        const visibleSpinners = Array.from(spinners).filter(s => s.offsetWidth > 0 && s.offsetHeight > 0);
        result.hydration.hasSpinners = visibleSpinners.length > 0;
        result.hydration.activeOverlays = document.querySelectorAll('.cdk-overlay-backdrop, .modal.show, [role="dialog"]').length;
        result.hydration.settled = !result.hydration.hasSpinners;

        // 2. KPI / Metrics extraction
        const kpiCandidates = document.querySelectorAll('.card, [role="region"], .metric, .kpi-card, .summary-card, [data-metric]');
        kpiCandidates.forEach(card => {
          if (card.offsetWidth === 0) return;
          const text = (card.innerText || '').trim();
          const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
          if (lines.length >= 2 && lines.length <= 6) {
            // Check if one of the lines looks like currency or a number
            const valIdx = lines.findIndex(l => /^[$€£¥]?[-+]?[0-9,]+(\.[0-9]+)?(%| hrs| TB| GB| MB)?$/i.test(l));
            if (valIdx !== -1) {
              const label = lines.slice(0, valIdx).join(' ') || lines[0];
              const value = lines[valIdx];
              const delta = lines.slice(valIdx + 1).join(' ') || null;
              result.kpi_cards.push({ label: label.slice(0, 60), value: value, delta: delta ? delta.slice(0, 60) : null });
            }
          }
        });
        // Deduplicate KPIs
        result.kpi_cards = result.kpi_cards.filter((v, i, a) => a.findIndex(t => t.label === v.label && t.value === v.value) === i).slice(0, 15);

        // 3. Tables Extraction (Native HTML tables + ARIA grids)
        const tableEls = document.querySelectorAll('table, [role="table"], [role="grid"], mat-table, cdk-table');
        tableEls.forEach((tbl, idx) => {
          if (tbl.offsetWidth === 0) return;
          const headers = [];
          const rows = [];

          // Find header cells
          const ths = tbl.querySelectorAll('th, [role="columnheader"]');
          ths.forEach(th => {
            const hText = (th.innerText || '').trim().replace(/\s+/g, ' ');
            if (hText) headers.push(hText);
          });

          // Find row elements
          const trs = tbl.querySelectorAll('tr, [role="row"], mat-row, cdk-row');
          trs.forEach(tr => {
            // Skip header rows if already captured
            if (tr.querySelector('th, [role="columnheader"]')) return;
            const cells = tr.querySelectorAll('td, [role="cell"], [role="gridcell"], mat-cell, cdk-cell');
            if (cells.length > 0) {
              const rowData = Array.from(cells).map(c => (c.innerText || '').trim().replace(/\s+/g, ' '));
              if (rowData.some(Boolean)) {
                rows.push(rowData);
              }
            }
          });

          if (headers.length > 0 || rows.length > 0) {
            let caption = '';
            const capEl = tbl.querySelector('caption, h2, h3, .table-title');
            if (capEl) caption = (capEl.innerText || '').trim();
            result.tables.push({
              table_id: "tbl_" + idx,
              caption: caption || ("Table " + (idx + 1)),
              headers: headers,
              rows: rows.slice(0, 60) // cap to 60 rows to prevent huge token blowups
            });
          }
        });

        // 4. Interactive Elements Indexing (Numbered Action Space [id])
        const interactiveSelectors = [
          'button',
          'a[href]',
          'input:not([type="hidden"])',
          'textarea',
          'select',
          '[role="button"]',
          '[role="combobox"]',
          '[role="tab"]',
          '[role="menuitem"]',
          '[role="checkbox"]',
          '[role="switch"]',
          '[role="option"]',
          'mat-select',
          '[contenteditable="true"]'
        ];
        const allInteractive = document.querySelectorAll(interactiveSelectors.join(', '));
        let elId = 1;
        allInteractive.forEach(el => {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0 || r.bottom < 0 || r.top > window.innerHeight * 2) return;
          const style = window.getComputedStyle(el);
          if (style.visibility === 'hidden' || style.display === 'none') return;

          el.setAttribute('data-agy-id', elId);
          const tag = el.tagName.toLowerCase();
          const role = el.getAttribute('role') || tag;
          const aria = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
          const text = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 60);

          let displayStr = "[" + elId + "] <" + tag;
          if (role && role !== tag) displayStr += ' role="' + role + '"';
          if (aria) displayStr += ' aria-label="' + aria + '"';
          displayStr += '>' + (text || (tag === 'input' ? aria : '')) + '</' + tag + '> (x:' + Math.round(r.left + r.width/2) + ', y:' + Math.round(r.top + r.height/2) + ')';

          result.interactive_index.push({
            id: elId,
            tag: tag,
            role: role,
            aria: aria,
            text: text,
            x: Math.round(r.left + r.width / 2),
            y: Math.round(r.top + r.height / 2),
            display: displayStr
          });
          elId++;
        });
        result.interactive_index = result.interactive_index.slice(0, 80);

        // 5. Clean Markdown Text
        const clone = document.body.cloneNode(true);
        // Remove noise
        const removeSelectors = ['script', 'style', 'svg', 'noscript', 'nav', 'header', 'footer', '.cdk-overlay-container'];
        clone.querySelectorAll(removeSelectors.join(', ')).forEach(n => n.remove());
        let md = (clone.innerText || '').split('\n').map(l => l.trim()).filter(Boolean).join('\n');
        result.markdown_content = md.slice(0, 8000); // high signal, compact

        return result;
      })()
    `;

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: extractJs, awaitPromise: true, returnByValue: true }, (res) => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true, data: res && res.result ? res.result.value : null }));
        }
      });
    });
    return;
  }

  // 12. CLICK_ELEMENT (Direct CDP Trusted Hardware Event + Fallback)
  if (action === "CLICK_ELEMENT") {
    const tabId = msg.tabId;
    const elementId = msg.elementId;
    const selector = msg.selector;
    let targetX = msg.x;
    let targetY = msg.y;
    const target = { tabId };

    const resolveCoordsJs = `
      (function() {
        let el = null;
        if (${JSON.stringify(elementId || null)}) {
          el = document.querySelector('[data-agy-id="' + "${elementId}" + '"]');
        } else if (${JSON.stringify(selector || null)}) {
          el = document.querySelector(${JSON.stringify(selector || '')});
        }
        if (el) {
          el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
          const r = el.getBoundingClientRect();
          const cx = Math.round(r.left + r.width / 2);
          const cy = Math.round(r.top + r.height / 2);
          const inViewport = cx >= 0 && cx <= window.innerWidth && cy >= 0 && cy <= window.innerHeight && r.width > 0 && r.height > 0;
          return {
            found: true,
            inViewport: inViewport,
            x: cx,
            y: cy,
            text: (el.innerText || el.value || '').slice(0, 50)
          };
        }
        return { found: false };
      })()
    `;

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: resolveCoordsJs, awaitPromise: true, returnByValue: true }, (evalRes) => {
        const val = evalRes && evalRes.result ? evalRes.result.value : null;
        if (val && val.found) {
          targetX = val.x;
          targetY = val.y;
        }

        if (targetX !== undefined && targetY !== undefined && targetX > 0 && targetY > 0) {
          // Send trusted CDP Mouse Pressed & Released
          chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
            type: "mousePressed",
            x: targetX,
            y: targetY,
            button: "left",
            clickCount: 1
          }, () => {
            setTimeout(() => {
              chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
                type: "mouseReleased",
                x: targetX,
                y: targetY,
                button: "left",
                clickCount: 1
              }, () => {
                ws.send(JSON.stringify({ id: reqId, ok: true, clicked: true, x: targetX, y: targetY, resolved: val }));
              });
            }, 60);
          });
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: Boolean(val && val.found), resolved: val }));
        }
      });
    });
    return;
  }

  // 13. TYPE_TEXT (Focus, Clear & Insert via CDP)
  if (action === "TYPE_TEXT") {
    const tabId = msg.tabId;
    const elementId = msg.elementId;
    const selector = msg.selector;
    const text = msg.text || "";
    const pressEnter = Boolean(msg.pressEnter);
    const clear = msg.clear !== false;
    const target = { tabId };

    const focusJs = `
      (function() {
        let el = null;
        if (${JSON.stringify(elementId || null)}) {
          el = document.querySelector('[data-agy-id="' + "${elementId}" + '"]');
        } else if (${JSON.stringify(selector || null)}) {
          el = document.querySelector(${JSON.stringify(selector || '')});
        }
        if (el) {
          el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
          el.focus();
          if (${clear}) {
            if (el.value !== undefined) el.value = '';
            if (el.isContentEditable) el.innerText = '';
          }
          return { found: true };
        }
        return { found: false };
      })()
    `;

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: focusJs, awaitPromise: true, returnByValue: true }, () => {
        chrome.debugger.sendCommand(target, "Input.insertText", { text: text }, (insertRes) => {
          if (pressEnter) {
            setTimeout(() => {
              chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
                type: "rawKeyDown",
                key: "Enter",
                code: "Enter",
                windowsVirtualKeyCode: 13
              }, () => {
                chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
                  type: "keyUp",
                  key: "Enter",
                  code: "Enter",
                  windowsVirtualKeyCode: 13
                }, () => {
                  ws.send(JSON.stringify({ id: reqId, ok: true, typed: text, enter: true }));
                });
              });
            }, 100);
          } else {
            ws.send(JSON.stringify({ id: reqId, ok: true, typed: text }));
          }
        });
      });
    });
    return;
  }

  // 14. SCROLL_PAGE
  if (action === "SCROLL_PAGE") {
    const tabId = msg.tabId;
    const direction = msg.direction || "down";
    const amount = Number(msg.amount || 600);
    const target = { tabId };

    const scrollJs = `
      (function() {
        const dir = ${JSON.stringify(direction)};
        const amt = ${amount};
        if (dir === 'down') window.scrollBy({ top: amt, behavior: 'smooth' });
        else if (dir === 'up') window.scrollBy({ top: -amt, behavior: 'smooth' });
        else if (dir === 'top') window.scrollTo({ top: 0, behavior: 'smooth' });
        else if (dir === 'bottom') window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        return { scrollX: window.scrollX, scrollY: window.scrollY, scrollHeight: document.body.scrollHeight };
      })()
    `;

    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Runtime.evaluate", { expression: scrollJs, awaitPromise: true, returnByValue: true }, (res) => {
        ws.send(JSON.stringify({ id: reqId, ok: true, result: res && res.result ? res.result.value : null }));
      });
    });
    return;
  }

  // 15. ENABLE_TELEMETRY (Opt-in Console & Network Error Capture via CDP)
  if (action === "ENABLE_TELEMETRY") {
    const tabId = msg.tabId;
    const target = { tabId };
    const enable = msg.enabled !== false;
    const bucket = ensureTelemetryBucket(tabId);
    if (!enable) {
      bucket.enabled = false;
      ws.send(JSON.stringify({ id: reqId, ok: true, enabled: false, tabId }));
      return;
    }
    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      bucket.enabled = true;
      chrome.debugger.sendCommand(target, "Log.enable", {}, () => {
        chrome.debugger.sendCommand(target, "Network.enable", {}, () => {
          if (msg.includeRuntime !== false) {
            chrome.debugger.sendCommand(target, "Runtime.enable", {}, () => {
              ws.send(JSON.stringify({ id: reqId, ok: true, enabled: true, tabId }));
            });
          } else {
            ws.send(JSON.stringify({ id: reqId, ok: true, enabled: true, tabId }));
          }
        });
      });
    });
    return;
  }

  // 16. GET_LOGS / CLEAR_LOGS
  if (action === "GET_LOGS") {
    const tabId = msg.tabId;
    const bucket = ensureTelemetryBucket(tabId);
    ws.send(JSON.stringify({
      id: reqId,
      ok: true,
      enabled: bucket.enabled,
      console: bucket.console,
      networkErrors: bucket.networkErrors,
    }));
    if (msg.clear) {
      bucket.console = [];
      bucket.networkErrors = [];
    }
    return;
  }

  if (action === "CLEAR_LOGS") {
    const tabId = msg.tabId;
    const bucket = ensureTelemetryBucket(tabId);
    bucket.console = [];
    bucket.networkErrors = [];
    ws.send(JSON.stringify({ id: reqId, ok: true, tabId }));
    return;
  }

  // 17. HANDLE_DIALOG (alert / confirm / prompt / beforeunload)
  if (action === "HANDLE_DIALOG") {
    const tabId = msg.tabId;
    const target = { tabId };
    const params = { accept: msg.accept !== false };
    if (msg.promptText !== undefined && msg.promptText !== null) {
      params.promptText = String(msg.promptText);
    }
    ensureAttached(tabId, (err) => {
      if (err) {
        ws.send(JSON.stringify({ id: reqId, ok: false, error: err }));
        return;
      }
      chrome.debugger.sendCommand(target, "Page.handleJavaScriptDialog", params, () => {
        if (chrome.runtime.lastError) {
          ws.send(JSON.stringify({ id: reqId, ok: false, error: chrome.runtime.lastError.message }));
        } else {
          ws.send(JSON.stringify({ id: reqId, ok: true, accepted: params.accept }));
        }
      });
    });
    return;
  }

  ws.send(JSON.stringify({ id: reqId, ok: false, error: `Unknown action: ${action}` }));
}

// Listen to content script notifications (quota errors, avatar discovered)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "QUOTA_EXHAUSTED" || request.type === "PAGE_EVENT") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: request.type,
          email: registeredEmail,
          tabId: sender.tab ? sender.tab.id : null,
          url: sender.tab ? sender.tab.url : null,
          payload: request.payload,
          timestamp: Date.now(),
        })
      );
    }
  }
  if (request.type === "DETECTED_EMAIL") {
    registeredEmail = request.email;
    chrome.storage.local.set({ profile_email: request.email });
  }
  sendResponse({ received: true });
});

// Initialize connection on extension load
connectWebSocket();
