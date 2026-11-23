(() => {
  let pollTimer = null;
  let pollingActive = true;
  let pollIntervalMs = 5000;
  let latestProcesses = [];
  let latestSnapshots = [];
  let chartSeries = [];

  const els = {
    globalHealthDot: document.getElementById("global-health-dot"),
    plainHealthSummary: document.getElementById("plain-health-summary"),
    hostIdentity: document.getElementById("host-identity"),
    pollInterval: document.getElementById("poll-interval"),
    themeToggleBtn: document.getElementById("theme-toggle-btn"),
    togglePollBtn: document.getElementById("toggle-poll-btn"),
    recordSnapshotBtn: document.getElementById("record-snapshot-btn"),
    errorBanner: document.getElementById("error-banner"),
    errorBannerText: document.getElementById("error-banner-text"),

    archWslBadge: document.getElementById("arch-wsl-badge"),
    archWslDetail: document.getElementById("arch-wsl-detail"),
    archBridgeBadge: document.getElementById("arch-bridge-badge"),
    archBridgeDetail: document.getElementById("arch-bridge-detail"),
    archVmBadge: document.getElementById("arch-vm-badge"),
    archVmDetail: document.getElementById("arch-vm-detail"),

    navServerCount: document.getElementById("nav-server-count"),
    navServiceCount: document.getElementById("nav-service-count"),
    navAlertCount: document.getElementById("nav-alert-count"),
    navHistoryCount: document.getElementById("nav-history-count"),

    cpuPercentVal: document.getElementById("cpu-percent-val"),
    cpuFill: document.getElementById("cpu-fill"),
    cpuMeterBar: document.getElementById("cpu-meter-bar"),
    cpuStateBadge: document.getElementById("cpu-state-badge"),
    cpuCoresVal: document.getElementById("cpu-cores-val"),
    loadAvgVal: document.getElementById("load-avg-val"),
    uptimeVal: document.getElementById("uptime-val"),

    memPercentVal: document.getElementById("mem-percent-val"),
    memFill: document.getElementById("mem-fill"),
    memMeterBar: document.getElementById("mem-meter-bar"),
    memStateBadge: document.getElementById("mem-state-badge"),
    memFreeVal: document.getElementById("mem-free-val"),
    memUsedVal: document.getElementById("mem-used-val"),
    swapUsedVal: document.getElementById("swap-used-val"),

    diskPercentVal: document.getElementById("disk-percent-val"),
    diskFill: document.getElementById("disk-fill"),
    diskMeterBar: document.getElementById("disk-meter-bar"),
    diskStateBadge: document.getElementById("disk-state-badge"),
    diskUsedVal: document.getElementById("disk-used-val"),
    diskFreeVal: document.getElementById("disk-free-val"),

    netRateVal: document.getElementById("net-rate-val"),
    vmDbPillBadge: document.getElementById("vm-db-pill-badge"),
    kpiDbLatency: document.getElementById("kpi-db-latency"),
    netRxTxVal: document.getElementById("net-rx-tx-val"),
    netIpsVal: document.getElementById("net-ips-val"),

    chartCanvas: document.getElementById("telemetry-chart"),
    procFilterInput: document.getElementById("proc-filter-input"),
    processTbody: document.getElementById("process-tbody"),

    fleetSummaryBadge: document.getElementById("fleet-summary-badge"),
    serversTbody: document.getElementById("servers-tbody"),
    addServerForm: document.getElementById("add-server-form"),

    servicesTbody: document.getElementById("services-tbody"),
    addServiceForm: document.getElementById("add-service-form"),

    alertsTbody: document.getElementById("alerts-tbody"),
    triggerTestAlertBtn: document.getElementById("trigger-test-alert-btn"),
    alertRulesForm: document.getElementById("alert-rules-form"),
    ruleCpu: document.getElementById("rule-cpu"),
    ruleMem: document.getElementById("rule-mem"),
    ruleDisk: document.getElementById("rule-disk"),
    rulesSavedBadge: document.getElementById("rules-saved-badge"),

    historyCountLabel: document.getElementById("history-count-label"),
    historyTbody: document.getElementById("history-tbody"),
    exportCsvBtn: document.getElementById("export-csv-btn"),

    dbModeBadge: document.getElementById("db-mode-badge"),
    dbEndpointVal: document.getElementById("db-endpoint-val"),
    dbTcpVal: document.getElementById("db-tcp-val"),
    dbAuthVal: document.getElementById("db-auth-val"),
    dbLatencyVal: document.getElementById("db-latency-val"),
    dbRowsVal: document.getElementById("db-rows-val"),
    dbErrorNote: document.getElementById("db-error-note"),
    dbConfigForm: document.getElementById("db-config-form"),
    dbHostInput: document.getElementById("db-host-input"),
    dbPortInput: document.getElementById("db-port-input"),
    dbUserInput: document.getElementById("db-user-input"),
    dbPassInput: document.getElementById("db-pass-input"),
    dbNameInput: document.getElementById("db-name-input"),

    lastUpdatedVal: document.getElementById("last-updated-val"),
  };

  // Tab switching
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-target");
      tabButtons.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", String(active));
      });
      tabPanels.forEach((p) => {
        p.classList.toggle("hidden", p.id !== targetId);
      });
      if (targetId === "panel-overview") {
        drawChart();
      }
    });
  });

  // Theme toggle
  els.themeToggleBtn.addEventListener("click", () => {
    const html = document.documentElement;
    const next = html.getAttribute("data-theme") === "light" ? "dark" : "light";
    html.setAttribute("data-theme", next);
    els.themeToggleBtn.textContent = next === "light" ? "Dark Mode" : "Light Mode";
    drawChart();
  });

  function formatUptime(sec) {
    const hrs = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const secs = sec % 60;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  }

  function updateMeter(fillEl, barEl, badgeEl, pct, labels) {
    const clamped = Math.max(0, Math.min(100, pct));
    fillEl.style.width = `${clamped}%`;
    barEl.setAttribute("aria-valuenow", String(clamped));
    fillEl.classList.remove("warn", "crit");
    badgeEl.className = "status-badge";
    if (clamped >= 85) {
      fillEl.classList.add("crit");
      badgeEl.classList.add("offline");
      badgeEl.textContent = labels.crit;
    } else if (clamped >= 65) {
      fillEl.classList.add("warn");
      badgeEl.classList.add("warn");
      badgeEl.textContent = labels.warn;
    } else {
      badgeEl.classList.add("online");
      badgeEl.textContent = labels.ok;
    }
  }

  function drawChart() {
    const canvas = els.chartCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const styles = getComputedStyle(document.documentElement);
    const gridColor = styles.getPropertyValue("--chart-grid").trim() || "#dce2d8";
    const cpuColor = styles.getPropertyValue("--chart-cpu").trim() || "#b35900";
    const memColor = styles.getPropertyValue("--chart-mem").trim() || "#157340";
    const mutedColor = styles.getPropertyValue("--text-muted").trim() || "#455248";

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padL = 42;
    const padR = 16;
    const padT = 16;
    const padB = 26;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.fillStyle = mutedColor;
    ctx.font = "11px monospace";

    [0, 25, 50, 75, 100].forEach((val) => {
      const y = padT + plotH - (val / 100) * plotH;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      ctx.fillText(`${val}%`, 6, y + 4);
    });

    if (chartSeries.length === 0) return;

    const plotLine = (key, color) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      chartSeries.forEach((pt, idx) => {
        const x =
          chartSeries.length === 1
            ? padL + plotW / 2
            : padL + (idx / (chartSeries.length - 1)) * plotW;
        const y = padT + plotH - (Math.min(100, Math.max(0, pt[key])) / 100) * plotH;
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };

    plotLine("cpu", cpuColor);
    plotLine("mem", memColor);
  }

  function renderProcesses() {
    const query = (els.procFilterInput.value || "").trim().toLowerCase();
    const filtered = latestProcesses.filter(
      (p) =>
        !query ||
        String(p.command).toLowerCase().includes(query) ||
        String(p.user).toLowerCase().includes(query) ||
        String(p.pid).includes(query)
    );

    if (filtered.length === 0) {
      els.processTbody.innerHTML = `<tr><td colspan="5" class="state-cell">No matching running programs found.</td></tr>`;
      return;
    }

    els.processTbody.innerHTML = filtered
      .map(
        (p) => `
      <tr>
        <td><strong>${p.command}</strong></td>
        <td class="mono-value">${p.user}</td>
        <td class="mono-value">${p.cpu.toFixed(1)}%</td>
        <td class="mono-value">${p.mem.toFixed(1)}%</td>
        <td class="mono-value">#${p.pid}</td>
      </tr>`
      )
      .join("");
  }

  els.procFilterInput.addEventListener("input", renderProcesses);

  function renderServers(servers) {
    els.navServerCount.textContent = String(servers.length);
    els.fleetSummaryBadge.textContent = `${servers.length} Servers`;

    if (servers.length === 0) {
      els.serversTbody.innerHTML = `<tr><td colspan="8" class="state-cell">No servers added yet. Use the form on the right to add one.</td></tr>`;
      return;
    }

    els.serversTbody.innerHTML = servers
      .map(
        (s) => `
      <tr>
        <td>
          <span class="status-badge ${s.status === "ONLINE" ? "online" : "offline"}">${s.status}</span>
        </td>
        <td><strong>${s.name}</strong><br><small class="muted-small">${s.os_type}</small></td>
        <td class="mono-value">${s.ip_address}<br><small class="muted-small">${s.hostname}</small></td>
        <td>${s.role}<br><small class="muted-small">${s.environment}</small></td>
        <td class="mono-value">${Number(s.cpu_percent || 0).toFixed(1)}%</td>
        <td class="mono-value">${Number(s.mem_percent || 0).toFixed(1)}%</td>
        <td class="mono-value">${s.latency_ms !== null && s.latency_ms !== undefined ? `${s.latency_ms} ms` : "--"}</td>
        <td>
          <button type="button" class="btn btn-secondary btn-sm delete-server-btn" data-id="${s.id}">Remove</button>
        </td>
      </tr>`
      )
      .join("");

    els.serversTbody.querySelectorAll(".delete-server-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.getAttribute("data-id"));
        await fetch("/api/servers/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        await fetchDashboard();
      });
    });
  }

  function renderServices(services) {
    els.navServiceCount.textContent = String(services.length);

    if (services.length === 0) {
      els.servicesTbody.innerHTML = `<tr><td colspan="6" class="state-cell">No port checks configured yet.</td></tr>`;
      return;
    }

    els.servicesTbody.innerHTML = services
      .map(
        (svc) => `
      <tr>
        <td>
          <span class="status-badge ${svc.status === "ONLINE" ? "online" : "offline"}">${svc.status === "ONLINE" ? "OPEN / OK" : "UNREACHABLE"}</span>
        </td>
        <td><strong>${svc.service_name}</strong></td>
        <td class="mono-value">${svc.host}:${svc.port}</td>
        <td>${svc.protocol}</td>
        <td class="mono-value">${svc.latency_ms !== null && svc.latency_ms !== undefined ? `${svc.latency_ms} ms` : "Timed out"}</td>
        <td>
          <button type="button" class="btn btn-secondary btn-sm delete-service-btn" data-id="${svc.id}">Remove</button>
        </td>
      </tr>`
      )
      .join("");

    els.servicesTbody.querySelectorAll(".delete-service-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.getAttribute("data-id"));
        await fetch("/api/services/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        await fetchDashboard();
      });
    });
  }

  function renderAlerts(alerts, rules) {
    const unacked = alerts.filter((a) => !a.acknowledged);
    els.navAlertCount.textContent = String(unacked.length);

    if (document.activeElement !== els.ruleCpu && document.activeElement !== els.ruleMem && document.activeElement !== els.ruleDisk) {
      els.ruleCpu.value = rules.cpu_warn;
      els.ruleMem.value = rules.mem_warn;
      els.ruleDisk.value = rules.disk_warn;
    }

    if (alerts.length === 0) {
      els.alertsTbody.innerHTML = `<tr><td colspan="6" class="state-cell">No alerts triggered. Everything is operating within safe limits.</td></tr>`;
      return;
    }

    els.alertsTbody.innerHTML = alerts
      .map(
        (a) => `
      <tr>
        <td><span class="status-badge ${a.severity === "CRITICAL" ? "offline" : "warn"}">${a.severity}</span></td>
        <td><strong>${a.server_name}</strong></td>
        <td>${a.metric_name} (<span class="mono-value">${a.metric_value}</span>)</td>
        <td>${a.message}</td>
        <td class="mono-value">${a.created_at}</td>
        <td>
          ${
            a.acknowledged
              ? `<span class="muted-small">Resolved</span>`
              : `<button type="button" class="btn btn-secondary btn-sm ack-alert-btn" data-id="${a.id}">Mark Resolved</button>`
          }
        </td>
      </tr>`
      )
      .join("");

    els.alertsTbody.querySelectorAll(".ack-alert-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.getAttribute("data-id"));
        await fetch("/api/alerts/ack", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        await fetchDashboard();
      });
    });
  }

  function renderDatabaseStatus(db, m) {
    els.dbEndpointVal.textContent = `${db.host}:${db.port} (${db.database})`;
    els.dbTcpVal.textContent = db.tcp_reachable ? "OPEN (Reachable)" : "CLOSED / UNREACHABLE";
    els.dbAuthVal.textContent = db.mysql_authenticated ? "LOGGED IN" : "NOT LOGGED IN";
    els.dbLatencyVal.textContent = `${db.latency_ms} ms`;
    els.kpiDbLatency.textContent = `DB Ping: ${db.latency_ms} ms`;
    els.dbRowsVal.textContent = String(db.stored_snapshots);
    els.dbModeBadge.textContent = db.mysql_authenticated ? "Connected to VM DB" : "Local Buffer";

    els.archWslDetail.textContent = `${m.host.hostname} (${m.host.distro}) · IP ${m.host.wsl_ip}`;
    els.archBridgeBadge.textContent = `Port ${db.port} · ${db.latency_ms} ms`;

    if (db.mysql_authenticated) {
      els.vmDbPillBadge.className = "status-badge online";
      els.vmDbPillBadge.textContent = "VM DB Connected";
      els.archVmBadge.className = "status-badge online";
      els.archVmBadge.textContent = "CONNECTED";
      els.archVmDetail.textContent = `Saving records to '${db.database}' inside VirtualBox VM (${db.stored_snapshots} saved).`;
      els.dbErrorNote.textContent = `Successfully connected to VirtualBox VM database '${db.database}' at ${db.host}:${db.port}.`;
      els.plainHealthSummary.textContent = `All systems healthy — WSL2 Linux Server (${m.cpu_percent.toFixed(1)}% CPU, ${m.memory.percent.toFixed(1)}% RAM) is actively syncing to your VirtualBox VM Database (${db.stored_snapshots} saved records).`;
    } else {
      els.vmDbPillBadge.className = "status-badge warn";
      els.vmDbPillBadge.textContent = "Buffering Locally";
      els.archVmBadge.className = "status-badge warn";
      els.archVmBadge.textContent = "BUFFER MODE";
      els.archVmDetail.textContent = "VM port 3306 unreachable; temporarily saving readings in WSL memory.";
      els.dbErrorNote.textContent = db.error || "VM database unreachable; buffering in local memory.";
      els.plainHealthSummary.textContent = `WSL2 Linux Server is healthy (${m.cpu_percent.toFixed(1)}% CPU), temporarily buffering readings until the VirtualBox VM Database reconnects.`;
    }
  }

  function renderHistory(rows) {
    latestSnapshots = rows || [];
    els.navHistoryCount.textContent = String(latestSnapshots.length);
    els.historyCountLabel.textContent = `${latestSnapshots.length} saved readings`;
    if (latestSnapshots.length === 0) {
      els.historyTbody.innerHTML = `<tr><td colspan="8" class="state-cell">No readings saved yet. Click "Save Reading to VM Database" in the top right.</td></tr>`;
      return;
    }
    els.historyTbody.innerHTML = latestSnapshots
      .map(
        (r) => `
      <tr>
        <td class="mono-value">#${r.id}</td>
        <td class="mono-value">${r.recorded_at}</td>
        <td><strong>${r.hostname}</strong></td>
        <td class="mono-value">${Number(r.cpu_percent).toFixed(1)}%</td>
        <td class="mono-value">${Number(r.load_1m).toFixed(2)}</td>
        <td class="mono-value">${r.mem_used_mb} / ${r.mem_total_mb} MB (${Number(r.mem_percent).toFixed(1)}%)</td>
        <td class="mono-value">${r.disk_used_gb} / ${r.disk_total_gb} GB (${Number(r.disk_percent).toFixed(1)}%)</td>
        <td><span class="status-badge ${r.storage_target === "vm_mysql" ? "online" : "warn"}">${r.storage_target === "vm_mysql" ? "VirtualBox VM DB" : "WSL Buffer"}</span></td>
      </tr>`
      )
      .join("");
  }

  async function fetchDashboard() {
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      els.errorBanner.classList.add("hidden");
      const m = data.metrics;
      const h = m.host;

      els.hostIdentity.textContent = `${h.hostname} (${h.distro}) ➔ VirtualBox VM Database (${data.database.host}:${data.database.port})`;
      els.uptimeVal.textContent = formatUptime(h.uptime_seconds);
      els.lastUpdatedVal.textContent = `Last updated: ${m.timestamp}`;

      els.cpuPercentVal.textContent = `${m.cpu_percent.toFixed(1)}%`;
      updateMeter(els.cpuFill, els.cpuMeterBar, els.cpuStateBadge, m.cpu_percent, {
        ok: "Low / Normal Load",
        warn: "Moderate Load",
        crit: "Heavy CPU Load",
      });
      els.cpuCoresVal.textContent = `${h.cpu_cores} CPU Cores`;
      els.loadAvgVal.textContent = h.load_avg.join(" / ");

      els.memPercentVal.textContent = `${m.memory.percent.toFixed(1)}%`;
      updateMeter(els.memFill, els.memMeterBar, els.memStateBadge, m.memory.percent, {
        ok: "Plenty of Free RAM",
        warn: "Moderate RAM Use",
        crit: "Low Free Memory",
      });
      els.memFreeVal.textContent = `${m.memory.available_mb} MB Free`;
      els.memUsedVal.textContent = `${m.memory.used_mb} / ${m.memory.total_mb} MB`;
      els.swapUsedVal.textContent = `${m.memory.swap_used_mb} / ${m.memory.swap_total_mb} MB`;

      els.diskPercentVal.textContent = `${m.disk.percent.toFixed(1)}%`;
      updateMeter(els.diskFill, els.diskMeterBar, els.diskStateBadge, m.disk.percent, {
        ok: "Plenty of Disk Space",
        warn: "Disk Filling Up",
        crit: "Disk Almost Full",
      });
      els.diskUsedVal.textContent = `${m.disk.used_gb} / ${m.disk.total_gb} GB`;
      els.diskFreeVal.textContent = `${m.disk.free_gb} GB Free`;

      const totalRate = (m.network.rx_rate_kbps + m.network.tx_rate_kbps).toFixed(1);
      els.netRateVal.textContent = `${totalRate} KB/s`;
      els.netRxTxVal.textContent = `${m.network.rx_rate_kbps} KB/s down · ${m.network.tx_rate_kbps} KB/s up`;
      els.netIpsVal.textContent = `${h.wsl_ip} ➔ ${h.windows_host_gateway}`;

      chartSeries.push({ ts: m.timestamp, cpu: m.cpu_percent, mem: m.memory.percent });
      if (chartSeries.length > 24) chartSeries = chartSeries.slice(-24);
      drawChart();

      latestProcesses = m.processes || [];
      renderProcesses();
      renderServers(data.servers || []);
      renderServices(data.services || []);
      renderAlerts(data.alerts || [], data.rules || { cpu_warn: 75, mem_warn: 80, disk_warn: 85 });
      renderDatabaseStatus(data.database, m);
      renderHistory(data.snapshots || []);
    } catch (err) {
      els.errorBanner.classList.remove("hidden");
      els.errorBannerText.textContent = `Unable to reach WSL server: ${err.message}`;
    }
  }

  function schedulePolling() {
    if (pollTimer) clearInterval(pollTimer);
    if (pollingActive) {
      pollTimer = setInterval(fetchDashboard, pollIntervalMs);
    }
  }

  els.togglePollBtn.addEventListener("click", () => {
    pollingActive = !pollingActive;
    els.togglePollBtn.textContent = pollingActive ? "Pause Live Updates" : "Resume Live Updates";
    if (pollingActive) fetchDashboard();
    schedulePolling();
  });

  els.pollInterval.addEventListener("change", (e) => {
    pollIntervalMs = Number(e.target.value) || 5000;
    schedulePolling();
  });

  els.recordSnapshotBtn.addEventListener("click", async () => {
    els.recordSnapshotBtn.disabled = true;
    try {
      await fetch("/api/snapshots/record", { method: "POST" });
      await fetchDashboard();
    } finally {
      els.recordSnapshotBtn.disabled = false;
    }
  });

  els.addServerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      name: document.getElementById("srv-name").value.trim(),
      hostname: document.getElementById("srv-hostname").value.trim(),
      ip_address: document.getElementById("srv-ip").value.trim(),
      environment: document.getElementById("srv-env").value,
      os_type: document.getElementById("srv-os").value.trim(),
      role: document.getElementById("srv-role").value.trim(),
    };
    await fetch("/api/servers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    els.addServerForm.reset();
    document.getElementById("srv-os").value = "Ubuntu Linux";
    document.getElementById("srv-role").value = "Web / API Server";
    await fetchDashboard();
  });

  els.addServiceForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      service_name: document.getElementById("svc-name").value.trim(),
      protocol: document.getElementById("svc-proto").value,
      host: document.getElementById("svc-host").value.trim(),
      port: Number(document.getElementById("svc-port").value) || 80,
    };
    await fetch("/api/services", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    els.addServiceForm.reset();
    document.getElementById("svc-host").value = "127.0.0.1";
    document.getElementById("svc-port").value = "8080";
    await fetchDashboard();
  });

  els.alertRulesForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      cpu_warn: Number(els.ruleCpu.value),
      mem_warn: Number(els.ruleMem.value),
      disk_warn: Number(els.ruleDisk.value),
    };
    await fetch("/api/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    els.rulesSavedBadge.textContent = "Saved in VM DB";
    await fetchDashboard();
  });

  els.triggerTestAlertBtn.addEventListener("click", async () => {
    await fetch("/api/alerts/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        server_name: "Primary App Node",
        severity: "WARNING",
        metric_name: "Processor Load Check",
        metric_value: "84.2%",
        message: "Sample warning alert saved to VirtualBox VM database.",
      }),
    });
    await fetchDashboard();
  });

  els.exportCsvBtn.addEventListener("click", () => {
    if (!latestSnapshots.length) return;
    const headers = ["id", "recorded_at", "hostname", "cpu_percent", "load_1m", "mem_used_mb", "mem_total_mb", "mem_percent", "disk_used_gb", "disk_total_gb", "disk_percent", "storage_target"];
    const csvRows = [
      headers.join(","),
      ...latestSnapshots.map((r) => headers.map((k) => JSON.stringify(r[k] ?? "")).join(",")),
    ];
    const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "server_telemetry_snapshots.csv";
    a.click();
    URL.revokeObjectURL(url);
  });

  els.dbConfigForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      host: els.dbHostInput.value.trim(),
      port: Number(els.dbPortInput.value) || 3306,
      user: els.dbUserInput.value.trim(),
      password: els.dbPassInput.value,
      database: els.dbNameInput.value.trim(),
    };
    await fetch("/api/db/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await fetchDashboard();
  });

  fetchDashboard();
  schedulePolling();
})();
