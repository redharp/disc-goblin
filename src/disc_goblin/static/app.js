const appState = {
  overview: { drives: [], active_jobs: [], history: [], totals: {} },
  socket: null,
  reconnectTimer: null,
  reconnectAttempts: 0,
  socketGeneration: 0,
  pollTimer: null,
  activityTimer: null,
  activityInFlight: false,
  activityPending: false,
  lastActivityHydration: 0,
  activityJobs: new Map(),
  detailJobId: null,
  detailRequest: 0,
  destroyed: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function humanStatus(status) {
  return String(status || "unknown").replaceAll("_", " ");
}

function formatDuration(seconds) {
  if (!seconds) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function formatBytes(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(bytes);
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

function relativeTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const ranges = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, amount] of ranges) {
    if (Math.abs(seconds) >= amount) return formatter.format(Math.round(seconds / amount), unit);
  }
  return formatter.format(seconds, "second");
}

function elapsedTime(value) {
  if (!value) return "Waiting to start";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s elapsed`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m elapsed` : `${minutes}m elapsed`;
}

function titleFor(job) {
  if (job.title) return `${job.title}${job.year ? ` (${job.year})` : ""}`;
  return job.disc_name || "Unknown disc";
}

function statusCopy(job, progress) {
  const messages = {
    scanning: "Reading disc structure and titles",
    queued: "Waiting for an available rip slot",
    ripping: progress ? `Copying selected titles · ${progress}%` : "MakeMKV is starting the rip",
    publishing: "Moving verified files into the library",
    needs_review: "Rip secured in staging",
  };
  return messages[job.status] || humanStatus(job.status);
}

function badge(status) {
  return `<span class="status-pill ${escapeHtml(status)}">${escapeHtml(humanStatus(status))}</span>`;
}

function renderMetrics(data) {
  const reviewing = data.active_jobs.filter((job) => job.status === "needs_review").length;
  const working = data.active_jobs.filter((job) => job.status !== "needs_review").length;
  $("#metric-drives").textContent = data.drives.length;
  $("#metric-active").textContent = working;
  $("#metric-complete").textContent = data.totals.completed || 0;
  $("#metric-review").textContent = reviewing;
  $("#metric-drives-note").textContent = data.drives.length
    ? `${data.drives.filter((drive) => drive.disc_name).length} with media inserted`
    : "No optical hardware found";
}

function renderDrives(data) {
  const grid = $("#drive-grid");
  const activeByDrive = new Map(data.active_jobs.map((job) => [job.drive_id, job]));
  $("#drive-summary").textContent = data.drives.length
    ? `${data.drives.length} drive${data.drives.length === 1 ? "" : "s"} responding`
    : "No drives are visible to MakeMKV";
  if (!data.drives.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div><strong>No optical drives yet</strong><span>Expose /dev/sr* and /dev/sg* to the container, then scan again.</span></div>
      </div>`;
    return;
  }
  grid.innerHTML = data.drives
    .map((drive) => {
      const job = activeByDrive.get(drive.id);
      const active = job && ["scanning", "queued", "ripping", "publishing"].includes(job.status);
      const state = active ? job.status : drive.disc_name ? "ready" : "empty";
      const discCopy = drive.disc_name
        ? `<p class="disc-label"><small>MEDIA LOADED</small>${escapeHtml(drive.disc_name)}</p>`
        : `<p class="disc-label"><small>TRAY STATUS</small>Ready for a disc</p>`;
      const uhdStatus = drive.uhd_status || "unknown";
      const firmwareCopy = drive.firmware_version
        ? `${drive.firmware_platform || "platform ?"} · FW ${drive.firmware_version}`
        : "Firmware not audited";
      return `
        <article class="drive-card ${active ? "active" : ""}">
          <div class="drive-top">
            <span class="drive-number">DRIVE / ${String(drive.disc_index + 1).padStart(2, "0")}</span>
            <div class="drive-badges">
              <span class="firmware-pill ${escapeHtml(uhdStatus)}">UHD ${escapeHtml(humanStatus(uhdStatus))}</span>
              <span class="state-pill ${escapeHtml(state)}">${escapeHtml(humanStatus(state))}</span>
            </div>
          </div>
          <h3>${escapeHtml(drive.name)}</h3>
          <span class="device">${escapeHtml(drive.device || `disc:${drive.disc_index}`)} · ${escapeHtml(firmwareCopy)}</span>
          ${discCopy}
          <div class="drive-actions">
            <button class="mini-button" data-action="firmware-audit" data-drive="${escapeHtml(drive.id)}">Audit FW</button>
            ${
              drive.flash_candidate && !drive.disc_name && !active
                ? `<button class="mini-button flash-button" data-action="firmware-flash" data-drive="${escapeHtml(drive.id)}">Flash UHD FW</button>`
                : ""
            }
            ${
              drive.disc_name && !active
                ? `<button class="mini-button" data-action="rip" data-drive="${escapeHtml(drive.id)}">Rip now</button>`
                : ""
            }
            ${
              !active
                ? `<button class="mini-button" data-action="eject" data-drive="${escapeHtml(drive.id)}">Open tray</button>`
                : ""
            }
          </div>
        </article>`;
    })
    .join("");
}

function renderQueue(data) {
  const queue = $("#queue");
  if (!data.active_jobs.length) {
    queue.innerHTML = `
      <div class="empty-state">
        <div><strong>The goblin is idle</strong><span>Insert a Blu-ray. Ingest starts automatically.</span></div>
      </div>`;
    return;
  }
  queue.innerHTML = data.active_jobs
    .map((job) => {
      const progress = Math.max(0, Math.min(100, Math.round((job.progress || 0) * 100)));
      const review = job.status === "needs_review";
      const working = ["scanning", "queued", "ripping", "publishing"].includes(job.status);
      return `
        <article
          class="job-card ${review ? "review" : ""} ${working ? "working" : ""}"
          data-job="${escapeHtml(job.id)}"
        >
          <div class="job-name">
            ${badge(job.status)}
            <h3>${escapeHtml(titleFor(job))}</h3>
            <p>${escapeHtml(job.disc_name)} · ${escapeHtml(job.drive_id)} · ${escapeHtml(elapsedTime(job.started_at || job.created_at))}</p>
          </div>
          <div class="job-progress">
            <div class="progress-copy">
              <span>${escapeHtml(statusCopy(job, progress))}</span>
              <span>${progress}%</span>
            </div>
            <div class="progress-track ${working && progress === 0 ? "indeterminate" : ""}" style="--progress:${progress}%"><span></span></div>
          </div>
          <div class="job-actions">
            <button class="button button-quiet" data-action="job-detail" data-job="${escapeHtml(job.id)}">Details</button>
            ${
              review
                ? `<button class="button button-primary" data-action="review" data-job="${escapeHtml(job.id)}">Name & publish</button>`
                : `<button class="button button-danger" data-action="cancel" data-job="${escapeHtml(job.id)}">Cancel</button>`
            }
          </div>
        </article>`;
    })
    .join("");
}

function renderActivity() {
  const list = $("#activity-log");
  const details = [...appState.activityJobs.values()];
  const events = details
    .flatMap((job) =>
      (job.events || []).map((event) => ({
        ...event,
        jobId: job.id,
        jobTitle: titleFor(job),
      })),
    )
    .sort((left, right) => new Date(right.created_at) - new Date(left.created_at))
    .slice(0, 30);
  $("#activity-note").textContent = events.length
    ? `${events.length} recent event${events.length === 1 ? "" : "s"} · click one for details`
    : "No recorded job events yet";
  if (!events.length) {
    list.innerHTML = `<li class="activity-empty">No recorded job activity yet. Running jobs will report here.</li>`;
    return;
  }
  list.innerHTML = events
    .map(
      (event) => `
        <li>
          <button class="activity-item ${escapeHtml(event.level || "info")}" data-action="job-detail" data-job="${escapeHtml(event.jobId)}">
            <span class="activity-dot" aria-hidden="true"></span>
            <span class="activity-copy">
              <strong>${escapeHtml(event.message)}</strong>
              <small>${escapeHtml(event.jobTitle)} · ${escapeHtml(relativeTime(event.created_at))}</small>
            </span>
          </button>
        </li>`,
    )
    .join("");
}

async function hydrateActivity() {
  appState.activityTimer = null;
  if (appState.activityInFlight) {
    appState.activityPending = true;
    return;
  }
  appState.activityInFlight = true;
  appState.lastActivityHydration = Date.now();
  const jobs = [
    ...appState.overview.active_jobs,
    ...appState.overview.history.slice(0, 8),
  ].filter((job, index, all) => all.findIndex((item) => item.id === job.id) === index);
  try {
    const details = await Promise.all(
      jobs.map((job) =>
        api(`/api/jobs/${job.id}`).catch(() => appState.activityJobs.get(job.id) || null),
      ),
    );
    appState.activityJobs = new Map(
      details.filter(Boolean).map((detail) => [detail.id, detail]),
    );
    renderActivity();
    if (appState.detailJobId) {
      const detail = appState.activityJobs.get(appState.detailJobId);
      if (detail) renderJobDetail(detail);
    }
  } finally {
    appState.activityInFlight = false;
    if (appState.activityPending) {
      appState.activityPending = false;
      scheduleActivityHydration();
    }
  }
}

function scheduleActivityHydration() {
  if (appState.activityTimer || appState.destroyed) return;
  const delay = Math.max(250, 2000 - (Date.now() - appState.lastActivityHydration));
  appState.activityTimer = setTimeout(hydrateActivity, delay);
}

function renderHistory(data) {
  const body = $("#history-body");
  if (!data.history.length) {
    body.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div><strong>No history yet</strong><span>Your completed and failed jobs will land here.</span></div></div></td></tr>`;
    return;
  }
  body.innerHTML = data.history
    .map(
      (job) => `
        <tr>
          <td><strong>${escapeHtml(titleFor(job))}</strong><small>${escapeHtml(job.media_type)}</small></td>
          <td><strong>${escapeHtml(job.disc_name)}</strong><small>${escapeHtml(job.drive_id)}</small></td>
          <td>${badge(job.status)}</td>
          <td><span class="path" title="${escapeHtml(job.final_path || job.stage_path)}">${escapeHtml(job.final_path || job.stage_path || "—")}</span></td>
          <td>${escapeHtml(relativeTime(job.completed_at || job.created_at))}</td>
          <td>
            ${
              job.status === "needs_review"
                ? `<button class="mini-button" data-action="review" data-job="${escapeHtml(job.id)}">Review</button>`
                : job.status === "failed"
                  ? `<button class="mini-button" data-action="retry" data-job="${escapeHtml(job.id)}">Retry</button>`
                  : ""
            }
          </td>
        </tr>`,
    )
    .join("");
}

function render(data) {
  appState.overview = data;
  renderMetrics(data);
  renderDrives(data);
  renderQueue(data);
  renderHistory(data);
  scheduleActivityHydration();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function setConnection(state, text, detail = "") {
  const element = $("#socket-state");
  element.className = `connection ${state}`;
  $("span", element).textContent = text;
  element.title = detail || text;
}

function connect() {
  if (appState.destroyed || !navigator.onLine) {
    setConnection("offline", "Offline", "This browser is offline");
    return;
  }
  clearTimeout(appState.reconnectTimer);
  const generation = ++appState.socketGeneration;
  if (appState.socket && appState.socket.readyState < WebSocket.CLOSING) {
    appState.socket.close();
  }
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${location.host}/api/ws`);
  appState.socket = socket;
  setConnection("syncing", "Syncing", "Opening the live dashboard channel");
  socket.addEventListener("open", () => {
    if (generation !== appState.socketGeneration) return;
    appState.reconnectAttempts = 0;
    setConnection("online", "Live", "Live updates connected");
  });
  socket.addEventListener("message", (event) => {
    if (generation !== appState.socketGeneration) return;
    try {
      render(JSON.parse(event.data));
      setConnection("online", "Live", `Last update ${new Date().toLocaleTimeString()}`);
    } catch {
      setConnection("syncing", "Syncing", "Received an invalid live update; polling is active");
    }
  });
  socket.addEventListener("close", () => {
    if (generation !== appState.socketGeneration || appState.destroyed) return;
    appState.socket = null;
    appState.reconnectAttempts += 1;
    setConnection("syncing", "Polling", "Live channel paused; dashboard polling is active");
    refresh().catch(() => setConnection("offline", "Offline", "Dashboard is unreachable"));
    const delay = Math.min(15000, 1200 * 2 ** Math.min(appState.reconnectAttempts, 4));
    appState.reconnectTimer = setTimeout(connect, delay);
  });
  socket.addEventListener("error", () => socket.close());
}

let toastTimer;
function toast(message, type = "") {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    element.className = "toast";
  }, 3500);
}

async function refresh() {
  const overview = await api("/api/overview");
  render(overview);
  if (!appState.socket || appState.socket.readyState !== WebSocket.OPEN) {
    setConnection("syncing", "Polling", `Last refresh ${new Date().toLocaleTimeString()}`);
  }
}

function renderJobDetail(job) {
  const progress = Math.max(0, Math.min(100, Math.round((job.progress || 0) * 100)));
  const events = job.events || [];
  const titles = job.titles || [];
  $("#job-dialog-title").textContent = titleFor(job);
  $("#job-dialog-body").innerHTML = `
    <div class="job-detail-summary">
      <div>${badge(job.status)}<strong>${progress}%</strong><small>${escapeHtml(statusCopy(job, progress))}</small></div>
      <div><span>Drive</span><strong>${escapeHtml(job.drive_id)}</strong><small>${escapeHtml(job.disc_name)}</small></div>
      <div><span>Runtime</span><strong>${escapeHtml(elapsedTime(job.started_at || job.created_at))}</strong><small>Started ${escapeHtml(relativeTime(job.started_at || job.created_at))}</small></div>
    </div>
    <div class="job-detail-progress">
      <div class="progress-track ${progress === 0 && ["scanning", "queued", "ripping"].includes(job.status) ? "indeterminate" : ""}" style="--progress:${progress}%"><span></span></div>
    </div>
    <div class="job-detail-grid">
      <section>
        <h3>Titles</h3>
        <div class="detail-list">
          ${
            titles.length
              ? titles
                  .map(
                    (title) => `
                      <div>
                        <strong>${escapeHtml(title.name || `Title ${title.title_index}`)}</strong>
                        <small>${escapeHtml(formatDuration(title.duration_seconds))} · ${escapeHtml(formatBytes(title.size_bytes))}${title.ripped_path ? " · ripped" : ""}</small>
                      </div>`,
                  )
                  .join("")
              : `<p class="detail-empty">Disc titles are still being scanned.</p>`
          }
        </div>
      </section>
      <section>
        <h3>Event log</h3>
        <div class="detail-list event-list">
          ${
            events.length
              ? events
                  .map(
                    (event) => `
                      <div class="detail-event ${escapeHtml(event.level || "info")}">
                        <strong>${escapeHtml(event.message)}</strong>
                        <small>${escapeHtml(relativeTime(event.created_at))}</small>
                      </div>`,
                  )
                  .join("")
              : `<p class="detail-empty">Waiting for the first job event.</p>`
          }
        </div>
      </section>
    </div>
    ${job.error ? `<p class="job-detail-error">${escapeHtml(job.error)}</p>` : ""}
    <div class="dialog-actions">
      ${
        job.status === "needs_review"
          ? `<button class="button button-primary" data-action="review" data-job="${escapeHtml(job.id)}">Name & publish</button>`
          : ["scanning", "queued", "ripping", "publishing"].includes(job.status)
            ? `<button class="button button-danger" data-action="cancel" data-job="${escapeHtml(job.id)}">Cancel job</button>`
            : ""
      }
      <button class="button button-quiet" data-action="close-job">Close</button>
    </div>`;
}

async function openJobDetail(jobId) {
  appState.detailJobId = jobId;
  const request = ++appState.detailRequest;
  $("#job-dialog-title").textContent = "Loading ingest…";
  $("#job-dialog-body").innerHTML = `<p class="dialog-copy">Loading job telemetry…</p>`;
  const dialog = $("#job-dialog");
  if (!dialog.open) dialog.showModal();
  const job = await api(`/api/jobs/${jobId}`);
  if (request !== appState.detailRequest || appState.detailJobId !== jobId) return;
  appState.activityJobs.set(job.id, job);
  renderJobDetail(job);
}

async function openReview(jobId) {
  const job = await api(`/api/jobs/${jobId}`);
  $("#review-job-id").value = job.id;
  $("#review-title").value = job.title || "";
  $("#review-year").value = job.year || "";
  $("#review-edition").value = job.edition || "";
  $("#review-season").value = job.season ?? 1;
  $("#review-episode").value = job.episode_start ?? 1;
  const type = job.media_type === "tv" ? "tv" : "movie";
  $(`input[name="media_type"][value="${type}"]`).checked = true;
  $("#review-form").classList.toggle("tv-mode", type === "tv");
  $("#review-error").textContent = "";
  $("#review-titles").innerHTML = job.titles
    .map(
      (title) => `
        <label class="title-option">
          <input type="checkbox" name="selected_title" value="${title.id}" ${title.selected ? "checked" : ""} />
          <strong>${escapeHtml(title.name || `Title ${title.title_index}`)}</strong>
          <span>${formatDuration(title.duration_seconds)} · ${formatBytes(title.size_bytes)}</span>
        </label>`,
    )
    .join("");
  $("#review-dialog").showModal();
}

async function performAction(action, target) {
  if (action === "job-detail") {
    await openJobDetail(target.dataset.job);
    return;
  }
  if (action === "close-job") {
    appState.detailJobId = null;
    appState.detailRequest += 1;
    $("#job-dialog").close();
    return;
  }
  if (action === "review") {
    appState.detailJobId = null;
    if ($("#job-dialog").open) $("#job-dialog").close();
    await openReview(target.dataset.job);
    return;
  }
  if (action === "rip") {
    await api(`/api/drives/${target.dataset.drive}/rip`, { method: "POST", body: "{}" });
    toast("Rip queued.");
  } else if (action === "eject") {
    await api(`/api/drives/${target.dataset.drive}/eject`, { method: "POST", body: "{}" });
    toast("Tray opened.");
  } else if (action === "retry") {
    await api(`/api/jobs/${target.dataset.job}/retry`, { method: "POST", body: "{}" });
    toast("Retry queued.");
  } else if (action === "cancel") {
    await api(`/api/jobs/${target.dataset.job}/cancel`, { method: "POST", body: "{}" });
    toast("Cancelling job.");
  } else if (action === "firmware-audit") {
    await api(`/api/drives/${target.dataset.drive}/firmware/audit`, {
      method: "POST",
      body: "{}",
    });
    toast("Firmware and LibreDrive audit complete.");
  } else if (action === "firmware-flash") {
    const driveId = target.dataset.drive;
    const approved = window.confirm(
      "Firmware flashing can permanently damage an incompatible drive. Continue only if the exact model, platform, image hash, and profile are trusted.",
    );
    if (!approved) return;
    await api(`/api/drives/${driveId}/firmware/flash`, {
      method: "POST",
      body: JSON.stringify({ confirmation: `FLASH ${driveId}` }),
    });
    toast("Firmware flashed and post-flash identity verified.");
  }
  await refresh();
}

document.addEventListener("click", async (event) => {
  const target =
    event.target.closest("[data-action]") ||
    (event.target.closest(".job-card[data-job]")
      ? {
          dataset: {
            action: "job-detail",
            job: event.target.closest(".job-card[data-job]").dataset.job,
          },
        }
      : null);
  if (!target) return;
  target.disabled = true;
  try {
    await performAction(target.dataset.action, target);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    target.disabled = false;
  }
});

$("#scan-button").addEventListener("click", async () => {
  const button = $("#scan-button");
  button.disabled = true;
  button.textContent = "Scanning…";
  try {
    await api("/api/poll", { method: "POST", body: "{}" });
    await refresh();
    toast("Drive scan complete.");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Scan drives";
  }
});

$$('input[name="media_type"]').forEach((input) => {
  input.addEventListener("change", () => {
    $("#review-form").classList.toggle("tv-mode", input.value === "tv" && input.checked);
  });
});

$("#review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#publish-button");
  button.disabled = true;
  button.textContent = "Publishing…";
  $("#review-error").textContent = "";
  const type = $('input[name="media_type"]:checked').value;
  const payload = {
    media_type: type,
    title: $("#review-title").value.trim(),
    year: $("#review-year").value ? Number($("#review-year").value) : null,
    season: type === "tv" ? Number($("#review-season").value || 1) : null,
    episode_start: type === "tv" ? Number($("#review-episode").value || 1) : null,
    edition: type === "movie" ? $("#review-edition").value.trim() : "",
    selected_title_ids: $$('input[name="selected_title"]:checked').map((input) =>
      Number(input.value),
    ),
  };
  if (!payload.selected_title_ids.length) {
    $("#review-error").textContent = "Select at least one title to publish.";
    button.disabled = false;
    button.textContent = "Confirm & publish";
    return;
  }
  try {
    await api(`/api/jobs/${$("#review-job-id").value}/metadata`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#review-dialog").close();
    toast("Published with a clean library name.");
    await refresh();
  } catch (error) {
    $("#review-error").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Confirm & publish";
  }
});

async function boot() {
  try {
    const [health, overview] = await Promise.all([api("/healthz"), api("/api/overview")]);
    $("#footer-library").textContent = health.simulation
      ? `SIMULATION / ${health.library_root}`
      : `LIBRARY / ${health.library_root}`;
    render(overview);
  } catch (error) {
    toast(`Disc Goblin could not start: ${error.message}`, "error");
  }
  connect();
  appState.pollTimer = setInterval(() => {
    if (document.visibilityState === "visible") {
      refresh().catch(() => {
        if (!appState.socket || appState.socket.readyState !== WebSocket.OPEN) {
          setConnection("offline", "Offline", "Dashboard is unreachable");
        }
      });
    }
  }, 5000);
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  refresh().catch(() => {});
  if (!appState.socket || appState.socket.readyState >= WebSocket.CLOSING) connect();
});

window.addEventListener("online", connect);
window.addEventListener("offline", () => {
  clearTimeout(appState.reconnectTimer);
  setConnection("offline", "Offline", "This browser is offline");
});

window.addEventListener("pagehide", () => {
  appState.destroyed = true;
  clearTimeout(appState.reconnectTimer);
  clearTimeout(appState.activityTimer);
  clearInterval(appState.pollTimer);
  appState.socket?.close();
});

$("#job-dialog").addEventListener("close", () => {
  appState.detailJobId = null;
  appState.detailRequest += 1;
});

boot();
