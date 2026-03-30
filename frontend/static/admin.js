const API = "/api";
const TOKEN_KEY = "plombir_admin_token";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[m]));

let token = localStorage.getItem(TOKEN_KEY) || "";
let ordersCache = [];

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
  if (!res.ok) throw new Error(data.detail || data.error || `${res.status}`);
  return data;
}

function setAuthMsg(msg, ok = false) { $("auth-msg").textContent = msg; $("auth-msg").style.color = ok ? "#065f46" : "#b91c1c"; }
function setMsg(id, msg, ok = false) { $(id).textContent = msg; $(id).style.color = ok ? "#065f46" : "#b91c1c"; }

function showAuthed(user) {
  $("auth-card").classList.add("hidden");
  $("app-card").classList.remove("hidden");
  $("me").textContent = ` · ${user.email} (${user.role})`;
}

function showLogin() {
  $("app-card").classList.add("hidden");
  $("auth-card").classList.remove("hidden");
}

async function checkMe() {
  if (!token) return showLogin();
  try {
    const me = await api("/admin/auth/me");
    showAuthed(me.user);
    await Promise.all([loadOrders(), loadMappings()]);
  } catch (_) {
    token = "";
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
  }
}

async function login() {
  const email = $("login-email").value.trim();
  const password = $("login-password").value;
  if (!email || !password) return setAuthMsg("Введите email и пароль");
  try {
    const data = await api("/admin/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    token = data.token;
    localStorage.setItem(TOKEN_KEY, token);
    setAuthMsg("Вход успешен", true);
    await checkMe();
  } catch (e) {
    setAuthMsg(`Ошибка входа: ${e.message}`);
  }
}

async function logout() {
  try { await api("/admin/auth/logout", { method: "POST" }); } catch (_) {}
  token = "";
  localStorage.removeItem(TOKEN_KEY);
  showLogin();
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const tab = b.dataset.tab;
      ["orders", "mapping", "broadcast"].forEach((name) => {
        $(`tab-${name}`).classList.toggle("hidden", name !== tab);
      });
    });
  });
}

async function loadOrders() {
  try {
    const rows = await api("/admin/orders?limit=40");
    ordersCache = Array.isArray(rows) ? rows : [];
    renderOrders();
    $("order-detail").classList.add("hidden");
    $("orders-list").classList.remove("hidden");
  } catch (e) {
    $("orders-list").innerHTML = `<div class="item small">Ошибка: ${esc(e.message)}</div>`;
  }
}

function renderOrders() {
  const q = ($("orders-q")?.value || "").trim().toLowerCase();
  const status = ($("orders-status")?.value || "").trim();
  const rows = ordersCache.filter((o) => {
    if (status && String(o.status || "") !== status) return false;
    if (!q) return true;
    const hay = [
      o.id,
      o.customer_name,
      o.customer_phone,
      o.telegram_username,
      o.telegram_user_id,
      o.status,
    ].map((x) => String(x || "").toLowerCase()).join(" ");
    return hay.includes(q);
  });
  $("orders-list").innerHTML = rows.map((o) => `
    <div class="item">
      <button class="order-click" onclick="openOrder(${Number(o.id)})">
        <div><strong>#${o.id}</strong> · ${esc(o.customer_name)} · ${esc(o.status)} · ${Math.round(Number(o.total || 0))} ₽</div>
        <div class="small mono">${esc(o.customer_phone || "")} · ${esc(o.payment_status || "")} · ${esc(o.created_at || "")}</div>
      </button>
    </div>
  `).join("") || '<div class="item small">Ничего не найдено</div>';
}

window.openOrder = async function (orderId) {
  try {
    const o = await api(`/orders/${orderId}`);
    $("order-detail-title").textContent = `Заказ #${o.id}`;
    $("order-detail-content").textContent = JSON.stringify(o, null, 2);
    $("orders-list").classList.add("hidden");
    $("order-detail").classList.remove("hidden");
    history.replaceState(null, "", `#order-${o.id}`);
  } catch (e) {
    alert(`Не удалось загрузить заказ: ${e.message}`);
  }
};

function closeOrderDetail() {
  $("order-detail").classList.add("hidden");
  $("orders-list").classList.remove("hidden");
  if (location.hash.startsWith("#order-")) {
    history.replaceState(null, "", "#orders");
  }
}

async function loadFeedProducts() {
  const q = $("feed-q").value.trim();
  const rows = await api(`/admin/feed-products?limit=300&unmapped_only=true&q=${encodeURIComponent(q)}`);
  $("feed-list").innerHTML = rows.map((r) => `
    <div class="item">
      <div><strong>${esc(r.name)}</strong></div>
      <div class="small mono">key: ${esc(r.tilda_key)}</div>
      <button class="secondary" onclick="pickTildaKey('${esc(r.tilda_key)}')">Взять key</button>
    </div>
  `).join("") || '<div class="item small">Нет данных</div>';
}

window.pickTildaKey = function (key) {
  $("map-tilda-key").value = key;
};

window.pickMs = function (href, id, name) {
  $("map-ms-href").value = href;
  $("map-ms-id").value = id || "";
  $("map-ms-name").value = name || "";
};

async function searchMs() {
  const q = $("ms-q").value.trim();
  const rows = await api(`/admin/moysklad/cache/search?q=${encodeURIComponent(q)}&limit=200`);
  $("ms-list").innerHTML = rows.map((r) => `
    <div class="item">
      <div><strong>${esc(r.name || "")}</strong></div>
      <div class="small mono">code=${esc(r.code || "")} · ext=${esc(r.external_code || "")}</div>
      <div class="small mono">${esc(r.ms_href || "")}</div>
      <button class="secondary" onclick="pickMs('${esc(r.ms_href)}', '${esc(r.ms_id || "")}', '${esc(r.name || "")}')">Выбрать</button>
    </div>
  `).join("") || '<div class="item small">Нет данных</div>';
}

async function refreshMsCache() {
  setMsg("map-msg", "Обновляю кэш МС...");
  try {
    const data = await api("/admin/moysklad/cache/refresh", { method: "POST" });
    setMsg("map-msg", `Кэш обновлён: ${data.count} позиций`, true);
  } catch (e) {
    setMsg("map-msg", `Ошибка: ${e.message}`);
  }
}

async function saveMapping() {
  const payload = {
    tilda_key: $("map-tilda-key").value.trim(),
    ms_href: $("map-ms-href").value.trim(),
    ms_id: $("map-ms-id").value.trim(),
    ms_name: $("map-ms-name").value.trim(),
    ms_type: "assortment",
    note: "admin-ui",
  };
  if (!payload.tilda_key || !payload.ms_href) return setMsg("map-msg", "Нужны tilda key и ms href");
  try {
    await api("/admin/mappings", { method: "POST", body: JSON.stringify(payload) });
    setMsg("map-msg", "Маппинг сохранён", true);
    await loadMappings();
  } catch (e) {
    setMsg("map-msg", `Ошибка: ${e.message}`);
  }
}

async function deleteMapping() {
  const key = $("map-delete-key").value.trim();
  if (!key) return setMsg("map-msg", "Введите tilda key");
  try {
    await api(`/admin/mappings/${encodeURIComponent(key)}`, { method: "DELETE" });
    setMsg("map-msg", "Маппинг удалён", true);
    await loadMappings();
  } catch (e) {
    setMsg("map-msg", `Ошибка: ${e.message}`);
  }
}

async function loadMappings() {
  try {
    const rows = await api("/admin/mappings?limit=500");
    $("mapping-list").innerHTML = rows.map((r) => `
      <div class="item">
        <div><strong>${esc(r.tilda_key)}</strong> → ${esc(r.ms_name || r.ms_id || "")}</div>
        <div class="small mono">${esc(r.ms_href || "")}</div>
        <div class="small">updated: ${esc(r.updated_at || "")} · by: ${esc(r.updated_by || "")}</div>
      </div>
    `).join("") || '<div class="item small">Пока пусто</div>';
  } catch (e) {
    $("mapping-list").innerHTML = `<div class="item small">Ошибка: ${esc(e.message)}</div>`;
  }
}

async function sendBroadcast() {
  const text = $("broadcast-text").value.trim();
  const dry_run = $("broadcast-dry").checked;
  const limit = Number($("broadcast-limit").value || 200);
  if (!text) return setMsg("broadcast-msg", "Пустой текст");
  setMsg("broadcast-msg", "Запуск...");
  try {
    const data = await api("/admin/broadcast", {
      method: "POST",
      body: JSON.stringify({ text, parse_mode: "HTML", dry_run, limit }),
    });
    setMsg("broadcast-msg", JSON.stringify(data), true);
  } catch (e) {
    setMsg("broadcast-msg", `Ошибка: ${e.message}`);
  }
}

function bind() {
  $("btn-login").addEventListener("click", login);
  $("btn-logout").addEventListener("click", logout);
  $("btn-orders-refresh").addEventListener("click", loadOrders);
  $("orders-q").addEventListener("input", renderOrders);
  $("orders-status").addEventListener("change", renderOrders);
  $("btn-order-back").addEventListener("click", closeOrderDetail);
  $("btn-feed-load").addEventListener("click", () => loadFeedProducts().catch((e) => setMsg("map-msg", e.message)));
  $("btn-ms-search").addEventListener("click", () => searchMs().catch((e) => setMsg("map-msg", e.message)));
  $("btn-ms-refresh").addEventListener("click", refreshMsCache);
  $("btn-map-save").addEventListener("click", saveMapping);
  $("btn-map-delete").addEventListener("click", deleteMapping);
  $("btn-map-list").addEventListener("click", loadMappings);
  $("btn-broadcast").addEventListener("click", sendBroadcast);
  setupTabs();
}

bind();
checkMe();
