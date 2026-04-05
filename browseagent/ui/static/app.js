// ── BrowseAgent UI — WebSocket Client & UI Logic ─────────────

(() => {
  "use strict";

  // ── DOM References ─────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const taskInput = $("#task-input");
  const btnRun = $("#btn-run");
  const btnPause = $("#btn-pause");
  const btnResume = $("#btn-resume");
  const btnStop = $("#btn-stop");
  const btnTakeover = $("#btn-takeover");
  const btnResumeTakeover = $("#btn-resume-takeover");
  const btnClearLog = $("#btn-clear-log");
  const maxStepsInput = $("#max-steps-input");
  const planCard = $("#plan-card");
  const stepLog = $("#step-log");
  const screenshot = $("#browser-screenshot");
  const placeholder = $("#browser-placeholder");
  const takeoverBanner = $("#takeover-banner");
  const takeoverInputLayer = $("#takeover-input-layer");
  const browserViewport = $("#browser-viewport");
  const resultsArea = $("#results-area");
  const resultsWrapper = $("#results-table-wrapper");
  const connBadge = $("#connection-badge");
  const stateBadge = $("#state-badge");

  let ws = null;
  let isRunning = false;
  let isTakeover = false;

  // Browser viewport dimensions (Playwright default)
  const BROWSER_WIDTH = 1280;
  const BROWSER_HEIGHT = 800;

  // ── WebSocket Connection ───────────────────────────
  function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
      setBadge(connBadge, "connected", "Connected");
      log("info", "Connected to BrowseAgent server");
    };

    ws.onclose = () => {
      setBadge(connBadge, "disconnected", "Disconnected");
      setIdle();
      log("warn", "Connection lost. Reconnecting in 3s...");
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    };
  }

  // ── Message Router ─────────────────────────────────
  function handleMessage(msg) {
    switch (msg.type) {
      case "connected":
        log("success", msg.message);
        break;

      case "status":
        handleStatus(msg.state);
        break;

      case "plan":
        showPlan(msg);
        break;

      case "step":
        log("step", `Step ${msg.step}/${msg.max_steps} \u2192 ${msg.description}`);
        break;

      case "step_error":
        log("error", `Step ${msg.step} failed: ${msg.error}`);
        break;

      case "screenshot":
        showScreenshot(msg.image);
        break;

      case "error":
        log("error", msg.message);
        break;

      case "completed":
        handleCompleted(msg);
        break;
    }
  }

  // ── Status Handling ────────────────────────────────
  function handleStatus(state) {
    switch (state) {
      case "planning":
        setBadge(stateBadge, "running", "Planning");
        setRunning();
        log("info", "Planning task...");
        break;

      case "launching":
        log("info", "Launching browser...");
        break;

      case "running":
        setBadge(stateBadge, "running", "Running");
        exitTakeover();
        btnPause.classList.remove("hidden");
        btnResume.classList.add("hidden");
        break;

      case "paused":
        setBadge(stateBadge, "paused", "Paused");
        btnPause.classList.add("hidden");
        btnResume.classList.remove("hidden");
        btnResume.disabled = false;
        log("warn", "Paused. Click Resume to continue.");
        break;

      case "takeover":
        setBadge(stateBadge, "takeover", "Manual Control");
        enterTakeover();
        log("warn", "Manual control active \u2014 click and type directly on the browser view.");
        break;

      case "stopped":
        setBadge(stateBadge, "failed", "Stopped");
        exitTakeover();
        setIdle();
        log("warn", "Task stopped by user.");
        break;

      case "settings_updated":
        log("info", "Settings updated.");
        break;
    }
  }

  // ── Takeover Mode ──────────────────────────────────
  function enterTakeover() {
    isTakeover = true;
    takeoverBanner.classList.remove("hidden");
    takeoverInputLayer.classList.remove("hidden");
    takeoverInputLayer.classList.add("active");
    takeoverInputLayer.focus();
  }

  function exitTakeover() {
    isTakeover = false;
    takeoverBanner.classList.add("hidden");
    takeoverInputLayer.classList.add("hidden");
    takeoverInputLayer.classList.remove("active");
  }

  /**
   * Translate a mouse event on the screenshot/input-layer
   * into (x, y) coordinates in the actual browser viewport.
   */
  function toBrowserCoords(e) {
    const rect = screenshot.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return null;

    // Mouse position relative to the displayed image
    const relX = e.clientX - rect.left;
    const relY = e.clientY - rect.top;

    // Scale to actual browser viewport
    const x = Math.round((relX / rect.width) * BROWSER_WIDTH);
    const y = Math.round((relY / rect.height) * BROWSER_HEIGHT);

    if (x < 0 || y < 0 || x > BROWSER_WIDTH || y > BROWSER_HEIGHT) return null;
    return { x, y };
  }

  // ── Takeover: Mouse Events ─────────────────────────
  takeoverInputLayer.addEventListener("click", (e) => {
    if (!isTakeover) return;
    const coords = toBrowserCoords(e);
    if (coords) {
      sendCommand("mouse_click", { x: coords.x, y: coords.y });
      showClickRipple(e.clientX, e.clientY);
    }
  });

  takeoverInputLayer.addEventListener("dblclick", (e) => {
    if (!isTakeover) return;
    const coords = toBrowserCoords(e);
    if (coords) {
      sendCommand("mouse_dblclick", { x: coords.x, y: coords.y });
    }
  });

  // ── Takeover: Keyboard Events ──────────────────────
  takeoverInputLayer.addEventListener("keydown", (e) => {
    if (!isTakeover) return;
    e.preventDefault();
    e.stopPropagation();

    // Map browser key names to Playwright key names
    const key = mapKey(e);
    if (key) {
      sendCommand("key_press", { key });
    }
  });

  takeoverInputLayer.addEventListener("keypress", (e) => {
    if (!isTakeover) return;
    e.preventDefault();
    e.stopPropagation();
  });

  function mapKey(e) {
    // For printable single characters, send as type
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      sendCommand("type_text", { text: e.key });
      return null; // handled via type_text
    }
    // Special keys
    const keyMap = {
      Enter: "Enter",
      Backspace: "Backspace",
      Delete: "Delete",
      Tab: "Tab",
      Escape: "Escape",
      ArrowUp: "ArrowUp",
      ArrowDown: "ArrowDown",
      ArrowLeft: "ArrowLeft",
      ArrowRight: "ArrowRight",
      Home: "Home",
      End: "End",
      PageUp: "PageUp",
      PageDown: "PageDown",
      " ": "Space",
    };
    return keyMap[e.key] || null;
  }

  // ── Click Ripple Effect ────────────────────────────
  function showClickRipple(clientX, clientY) {
    const ripple = document.createElement("div");
    ripple.style.cssText = `
      position: fixed; left: ${clientX - 12}px; top: ${clientY - 12}px;
      width: 24px; height: 24px; border-radius: 50%;
      border: 2px solid #fdcb6e; pointer-events: none; z-index: 999;
      animation: ripple-fade 0.4s ease-out forwards;
    `;
    document.body.appendChild(ripple);
    setTimeout(() => ripple.remove(), 500);
  }

  // Add ripple animation
  const style = document.createElement("style");
  style.textContent = `
    @keyframes ripple-fade {
      0% { transform: scale(0.5); opacity: 1; }
      100% { transform: scale(2); opacity: 0; }
    }
  `;
  document.head.appendChild(style);

  // ── Plan Display ───────────────────────────────────
  function showPlan(plan) {
    $("#plan-goal").textContent = plan.goal;
    $("#plan-summary").textContent = plan.plan_summary;
    $("#plan-url").textContent = plan.first_url;
    $("#plan-steps").textContent = `Estimated steps: ${plan.steps_estimate}`;
    planCard.classList.remove("hidden");
    log("success", `Plan ready: ${plan.plan_summary}`);
  }

  // ── Screenshot Display ─────────────────────────────
  function showScreenshot(base64) {
    screenshot.src = `data:image/png;base64,${base64}`;
    screenshot.classList.remove("hidden");
    placeholder.classList.add("hidden");
  }

  // ── Completion ─────────────────────────────────────
  function handleCompleted(msg) {
    const statusLabel = msg.status === "completed" ? "completed" : "failed";
    setBadge(stateBadge, statusLabel === "completed" ? "completed" : "failed",
      statusLabel.charAt(0).toUpperCase() + statusLabel.slice(1));

    if (msg.status === "completed") {
      log("success", `Task complete in ${msg.total_steps} steps (${msg.elapsed}s)`);
    } else if (msg.status === "max_steps_reached") {
      log("warn", `Max steps reached (${msg.total_steps} steps, ${msg.elapsed}s)`);
    } else {
      log("error", `Task failed after ${msg.total_steps} steps (${msg.elapsed}s)`);
    }

    if (msg.data && msg.data.length > 0) {
      log("success", `Extracted ${msg.data.length} items`);
      showResultsTable(msg.data);
    }

    exitTakeover();
    setIdle();
  }

  // ── Results Table ──────────────────────────────────
  function showResultsTable(data) {
    if (!data || data.length === 0) return;

    const headers = Object.keys(data[0]);
    let html = '<table class="results-table"><thead><tr>';
    headers.forEach((h) => (html += `<th>${esc(h)}</th>`));
    html += "</tr></thead><tbody>";
    data.forEach((row) => {
      html += "<tr>";
      headers.forEach((h) => (html += `<td title="${esc(String(row[h] || ""))}">${esc(String(row[h] || ""))}</td>`));
      html += "</tr>";
    });
    html += "</tbody></table>";

    resultsWrapper.innerHTML = html;
    resultsArea.classList.remove("hidden");
  }

  // ── Logging ────────────────────────────────────────
  function log(level, message) {
    const icons = {
      step: "\u25ce",
      success: "\u2713",
      error: "\u2717",
      info: "\u25cb",
      warn: "\u26a0",
    };

    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.innerHTML = `
      <span class="log-icon log-${level}">${icons[level] || "\u25cb"}</span>
      <span class="log-${level}">${esc(message)}</span>
    `;
    stepLog.appendChild(entry);
    stepLog.scrollTop = stepLog.scrollHeight;
  }

  // ── Commands ───────────────────────────────────────
  function sendCommand(command, extra = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ command, ...extra }));
    }
  }

  function runTask() {
    const task = taskInput.value.trim();
    if (!task || isRunning) return;

    const maxSteps = parseInt(maxStepsInput.value) || 40;
    sendCommand("update_settings", { max_steps: maxSteps });

    // Clear previous state
    planCard.classList.add("hidden");
    resultsArea.classList.add("hidden");
    resultsWrapper.innerHTML = "";
    exitTakeover();

    sendCommand("run", { task });
  }

  // ── UI State Helpers ───────────────────────────────
  function setRunning() {
    isRunning = true;
    btnRun.disabled = true;
    taskInput.disabled = true;
    btnPause.disabled = false;
    btnPause.classList.remove("hidden");
    btnResume.classList.add("hidden");
    btnStop.disabled = false;
    btnTakeover.disabled = false;
  }

  function setIdle() {
    isRunning = false;
    btnRun.disabled = false;
    taskInput.disabled = false;
    btnPause.disabled = true;
    btnResume.disabled = true;
    btnStop.disabled = true;
    btnTakeover.disabled = true;
    btnPause.classList.remove("hidden");
    btnResume.classList.add("hidden");
  }

  function setBadge(el, cls, text) {
    el.className = `badge badge-${cls}`;
    el.textContent = text;
  }

  function esc(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Resizable Divider ──────────────────────────────
  function initDivider() {
    const divider = $("#divider");
    const leftPanel = $(".left-panel");
    let isDragging = false;

    divider.addEventListener("mousedown", (e) => {
      isDragging = true;
      divider.classList.add("dragging");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      const newWidth = Math.min(Math.max(e.clientX, 280), window.innerWidth - 400);
      leftPanel.style.width = `${newWidth}px`;
    });

    document.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        divider.classList.remove("dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    });
  }

  // ── Event Listeners ────────────────────────────────
  btnRun.addEventListener("click", runTask);

  taskInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      runTask();
    }
  });

  btnPause.addEventListener("click", () => sendCommand("pause"));
  btnResume.addEventListener("click", () => sendCommand("resume"));
  btnStop.addEventListener("click", () => sendCommand("stop"));
  btnTakeover.addEventListener("click", () => sendCommand("takeover"));
  btnResumeTakeover.addEventListener("click", () => sendCommand("resume"));

  btnClearLog.addEventListener("click", () => {
    stepLog.innerHTML = "";
  });

  // ── Init ───────────────────────────────────────────
  initDivider();
  connect();
})();
