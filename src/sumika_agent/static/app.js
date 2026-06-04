const state = {
  token: localStorage.getItem("sumika_admin_token") || "",
};

const $ = (id) => document.getElementById(id);

function headers() {
  return { Authorization: `Bearer ${state.token}`, "Content-Type": "application/json" };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return response.json();
}

function fmt(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

async function loadStatus() {
  const data = await api("/api/status");
  const budget = data.budget;
  const openrouter = data.openrouter;
  $("status-grid").innerHTML = [
    metric("OneBot", `${data.onebot_clients} 连接`),
    metric("OpenRouter", openrouter.ok ? "可用" : "不可用", openrouter.ok ? "ok" : "warn"),
    metric("流量", `${budget.month_used_gib} / ${budget.soft_limit_gib} GiB`, budget.level === "normal" ? "ok" : "warn"),
    metric("预算状态", budget.level),
  ].join("");
}

function metric(label, value, badge = "") {
  const cls = badge ? `badge ${badge}` : "badge";
  return `<div class="metric"><span>${label}</span><strong><span class="${cls}">${value}</span></strong></div>`;
}

async function loadApprovals() {
  const rows = await api("/api/approvals");
  $("approvals").innerHTML = rows.length
    ? rows.map((row) => `
      <div class="item">
        <div class="item-row">
          <div>
            <strong>${row.request_type}</strong>
            <div class="muted">user ${fmt(row.user_id)} group ${fmt(row.group_id)}</div>
            <div>${fmt(row.comment)}</div>
            <div class="muted">${fmt(row.natural_reply)}</div>
          </div>
          <div class="actions">
            <span class="badge">${row.status}</span>
            ${row.status === "pending" ? `<button data-approval="${row.id}" data-decision="approve">通过</button><button class="danger" data-approval="${row.id}" data-decision="reject">拒绝</button>` : ""}
          </div>
        </div>
      </div>
    `).join("")
    : `<p class="muted">暂无待审批请求</p>`;
}

async function loadWhitelist() {
  const rows = await api("/api/whitelist");
  $("whitelist").innerHTML = rows.length
    ? rows.map((row) => `
      <div class="item">
        <div class="item-row">
          <span>${row.target_type} ${row.target_id} ${row.label || ""}</span>
          <span class="badge ${row.enabled ? "ok" : "warn"}">${row.enabled ? "启用" : "停用"}</span>
        </div>
      </div>
    `).join("")
    : `<p class="muted">暂无白名单</p>`;
}

async function loadWorldMemory() {
  const rows = await api("/api/memory/world");
  $("world-memory").innerHTML = rows.map((row) => `
    <div class="item">
      <div>${row.content}</div>
      <div class="muted">${row.source}</div>
    </div>
  `).join("");
}

async function loadUserMemory() {
  const rows = await api("/api/memory/users");
  $("user-memory").innerHTML = `
    <table>
      <thead><tr><th>用户</th><th>好感</th><th>摘要</th><th>更新时间</th></tr></thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${row.display_name || row.user_id}</td>
            <td>${Math.round(row.favorability)}</td>
            <td>${row.summary || "—"}</td>
            <td>${row.updated_at ? new Date(row.updated_at * 1000).toLocaleString() : "—"}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

async function refreshAll() {
  if (!state.token) return;
  await Promise.all([loadStatus(), loadApprovals(), loadWhitelist(), loadWorldMemory(), loadUserMemory()]);
}

$("token-input").value = state.token;
$("token-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = $("token-input").value.trim();
  localStorage.setItem("sumika_admin_token", state.token);
  await refreshAll();
});

$("approvals").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-approval]");
  if (!button) return;
  await api(`/api/approvals/${button.dataset.approval}/${button.dataset.decision}`, { method: "POST" });
  await loadApprovals();
});

$("whitelist-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await api("/api/whitelist", {
    method: "POST",
    body: JSON.stringify({
      target_type: $("target-type").value,
      target_id: $("target-id").value.trim(),
      label: $("target-label").value.trim(),
      enabled: true,
    }),
  });
  $("target-id").value = "";
  $("target-label").value = "";
  await loadWhitelist();
});

$("world-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = $("world-content").value.trim();
  if (!content) return;
  await api("/api/memory/world", { method: "POST", body: JSON.stringify({ content }) });
  $("world-content").value = "";
  await loadWorldMemory();
});

refreshAll().catch((error) => console.warn(error));
setInterval(() => refreshAll().catch(() => {}), 30000);

