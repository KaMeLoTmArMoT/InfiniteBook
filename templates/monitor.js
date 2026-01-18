function connectMonitor() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/monitor`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateMonitorUI(data);
  };

  ws.onclose = () => {
    setTimeout(connectMonitor, 5000);
  };
}

function updateMonitorUI(data) {
  const olStat = document.getElementById("ollama-status");
  const olDot = document.getElementById("ollama-dot");

  if (data.ollama && data.ollama.status === "online") {
    olStat.innerText = "Online";
    olDot.classList.add("status-online");
  } else {
    olStat.innerText = "Offline";
    olDot.classList.remove("status-online");
  }

  const provEl = document.getElementById("llm-providers");
  if (provEl) {
    const ps = data.llm?.providers || [];
    provEl.innerText = ps.length ? ps.join(", ") : "None";
  }

  if (data.ram && !data.ram.error) {
    const used = data.ram.used || 0;
    const total = data.ram.total || 0;
    const pct = total > 0 ? (used / total) * 100 : 0;

  document.getElementById("ram-text").innerText =
    `${(used / (1024 ** 3)).toFixed(1)}G / ${(total / (1024 ** 3)).toFixed(1)}G`;

    const bar = document.getElementById("ram-bar");
    bar.style.width = `${pct}%`;
    bar.className = "progress-fill";
    if (pct > 70) bar.classList.add("warning");
    if (pct > 90) bar.classList.add("danger");
  }

  if (data.gpu && !data.gpu.error) {
    document.getElementById("gpu-name").innerText = (data.gpu.name || "").replace("NVIDIA GeForce ", "");
    document.getElementById("gpu-load").innerText = `${data.gpu.gpu_load}%`;

    const used = data.gpu.memory_used;
    const total = data.gpu.memory_total;
    const pct = total > 0 ? (used / total) * 100 : 0;

    document.getElementById("vram-text").innerText =
      `${(used / 1024).toFixed(1)}G / ${(total / 1024).toFixed(1)}G`;

    const bar = document.getElementById("vram-bar");
    bar.style.width = `${pct}%`;
    bar.className = "progress-fill";
    if (pct > 70) bar.classList.add("warning");
    if (pct > 90) bar.classList.add("danger");
  }
}
