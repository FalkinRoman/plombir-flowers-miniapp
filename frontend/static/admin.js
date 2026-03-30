const API = "/api";
const TOKEN_KEY = "plombir_admin_token";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[m]));

function toast(msg, ok = true) {
  const stack = $("toast-stack");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = `toast ${ok ? "toast--ok" : "toast--err"}`;
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.28s ease";
    setTimeout(() => el.remove(), 280);
  }, 4000);
}

function setFeedWrapLoading(on) {
  const w = $("feed-list-wrap");
  if (w) w.classList.toggle("is-loading", !!on);
}
function setMsWrapLoading(on) {
  const w = $("ms-list-wrap");
  if (w) w.classList.toggle("is-loading", !!on);
}
function setBothWrapLoading(on) {
  setFeedWrapLoading(on);
  setMsWrapLoading(on);
}
const STATUS_PAYMENT_MAP = {
  pending: "Ожидает оплаты",
  succeeded: "Оплачен",
  canceled: "Отменен",
  not_required: "Оплата не требуется",
};
const STATUS_ORDER_MAP = {
  "Создан": "Создан",
  "Оплачен": "Оплачен",
  "Флорист": "Передан флористу",
  "Курьер": "Передан курьеру",
  "Доставлен": "Доставлен",
  "Отменен": "Отменен",
};

let token = localStorage.getItem(TOKEN_KEY) || "";
let ordersCache = [];
let selectedFeedItem = null;

/** Подсветка шагов: 1 — фид, 2 — кэш МС, ≥3 — оба готовы */
let mapWizardPhase = 1;

function updateMapWizardUI() {
  const b1 = $("btn-feed-refresh");
  const b2 = $("btn-ms-refresh");
  if (!b1 || !b2) return;
  [b1, b2].forEach((b) => b.classList.remove("wizard-btn--active", "wizard-btn--done", "wizard-btn--idle"));
  const ph = mapWizardPhase;
  if (ph <= 1) {
    b1.classList.add("wizard-btn--active");
    b2.classList.add("wizard-btn--idle");
  } else if (ph === 2) {
    b1.classList.add("wizard-btn--done");
    b2.classList.add("wizard-btn--active");
  } else {
    b1.classList.add("wizard-btn--done");
    b2.classList.add("wizard-btn--done");
  }
}

const EMPTY_MS =
  '<div class="item small">Пусто. Обнови кэш МС или измени поиск.</div>';

/** ms_type для БД/заказа: из API-href, не «assortment» по умолчанию (иначе meta.type не совпадает с href). */
function inferMsTypeFromHref(href) {
  const s = String(href || "").toLowerCase();
  if (s.includes("/entity/variant/")) return "variant";
  if (s.includes("/entity/service/")) return "service";
  if (s.includes("/entity/bundle/")) return "bundle";
  if (s.includes("/entity/consignment/")) return "consignment";
  if (s.includes("/entity/product/")) return "product";
  return "assortment";
}

/** Совпадает с id в API и с id= в веб-URL; uuidHref в JSON МС может отличаться. */
function msIdFromRemapHref(href) {
  const h = String(href || "").trim().replace(/\/+$/, "");
  if (!h || !h.includes("/entity/")) return "";
  const tail = h.split("/").pop() || "";
  return tail.length >= 32 && tail.includes("-") ? tail : "";
}

function renderMsList(rows, opts = {}) {
  const mode = opts.mode || "search";
  const showScore = mode === "suggest";
  const webTitle =
    "Если в кэше есть meta.uuidHref от МС — открываем его; иначе URL из id/API. В инпуты связки по-прежнему идёт API meta.href.";
  const html = (Array.isArray(rows) ? rows : []).map((r) => {
    const web = String(r.ms_web_url || "").trim();
    const hrefHint = esc(r.ms_href || "");
    const webBlock = web
      ? `<div class="small"><a href="${esc(web)}" target="_blank" rel="noopener noreferrer" title="${webTitle} API: ${hrefHint}">В МС ↗</a></div>`
      : "";
    return `
    <div class="item">
      ${showScore ? `<div class="small" style="color:#065f46;font-weight:600;">~${Math.round(Number(r.score || 0) * 100)}% совпадение</div>` : ""}
      <div><strong>${esc(r.name || "")}</strong></div>
      <div class="small mono">code=${esc(r.code || "")} · ext=${esc(r.external_code || "")}</div>
      ${webBlock}
      <button type="button" class="secondary btn-pick-ms"
        data-href="${encodeURIComponent(r.ms_href || "")}"
        data-mid="${encodeURIComponent(r.ms_id || "")}"
        data-mname="${encodeURIComponent(r.name || "")}">Выбрать</button>
    </div>`;
  }).join("");
  $("ms-list").innerHTML = html || EMPTY_MS;
}

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
function trPaymentStatus(s) { return STATUS_PAYMENT_MAP[String(s || "").toLowerCase()] || String(s || "—"); }
function trOrderStatus(s) { return STATUS_ORDER_MAP[String(s || "")] || String(s || "—"); }

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
    await Promise.all([loadOrders(), loadMappings(), loadMappingStats()]);
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
      if (tab === "mapping") {
        loadMappingStats().catch(() => {});
        loadMappings().catch(() => {});
      }
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
        <div><strong>#${o.id}</strong> · ${esc(o.customer_name)} · ${esc(trOrderStatus(o.status))} · ${Math.round(Number(o.total || 0))} ₽</div>
        <div class="small mono">${esc(o.customer_phone || "")} · ${esc(trPaymentStatus(o.payment_status))} · ${esc(o.created_at || "")}</div>
      </button>
    </div>
  `).join("") || '<div class="item small">Ничего не найдено</div>';
}

function prettyDate(v) {
  if (!v) return "—";
  try {
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return d.toLocaleString("ru-RU");
  } catch (_) {
    return String(v);
  }
}

function money(v) {
  const n = Number(v || 0);
  return `${Math.round(n)} ₽`;
}

function renderOrderDetailHtml(o) {
  const items = Array.isArray(o.items) ? o.items : [];
  const itemsHtml = items.map((it, idx) => {
    const title = `${it.name || "Товар"}${it.variant_label ? ` (${it.variant_label})` : ""}`;
    return `
      <div style="padding:8px 0; border-top:1px solid #eee;">
        <div><strong>${idx + 1}. ${esc(title)}</strong></div>
        <div class="small">Количество: ${esc(it.quantity || 1)} · Цена: ${money(it.price || 0)} · Сумма: ${money((Number(it.price || 0) * Number(it.quantity || 1)))}</div>
        <div class="small mono">Код товара: ${esc(it.product_code || it.product_id || "—")}</div>
      </div>
    `;
  }).join("") || `<div class="small">Товары не найдены</div>`;

  return `
    <div><strong>Статус заказа:</strong> ${esc(trOrderStatus(o.status))}</div>
    <div><strong>Статус оплаты:</strong> ${esc(trPaymentStatus(o.payment_status))}</div>
    <div><strong>Итого:</strong> ${money(o.total)}</div>
    <div><strong>Создан:</strong> ${esc(prettyDate(o.created_at))}</div>
    <hr style="border:0;border-top:1px solid #eee;margin:10px 0;">
    <div><strong>Клиент:</strong> ${esc(o.customer_name || "—")}</div>
    <div><strong>Телефон:</strong> ${esc(o.customer_phone || "—")}</div>
    <div><strong>Telegram username:</strong> ${esc(o.telegram_username || "—")}</div>
    <div><strong>ID Telegram:</strong> ${esc(o.telegram_user_id || "—")}</div>
    <hr style="border:0;border-top:1px solid #eee;margin:10px 0;">
    <div><strong>Тип доставки:</strong> ${esc(o.delivery_type || "—")}</div>
    <div><strong>Адрес:</strong> ${esc(o.delivery_address || "—")}</div>
    <div><strong>Дата:</strong> ${esc(o.delivery_date || "—")}</div>
    <div><strong>Время:</strong> ${esc(o.delivery_time || "—")}</div>
    <div><strong>Способ связи:</strong> ${esc(o.contact_method || "—")}</div>
    <div><strong>Получатель:</strong> ${esc(o.recipient_name || "—")}</div>
    <div><strong>Телефон получателя:</strong> ${esc(o.recipient_phone || "—")}</div>
    <div><strong>Комментарий курьеру:</strong> ${esc(o.courier_comment || "—")}</div>
    <div><strong>Текст открытки:</strong> ${esc(o.card_text || "—")}</div>
    <div><strong>Комментарий к заказу:</strong> ${esc(o.comment || "—")}</div>
    <hr style="border:0;border-top:1px solid #eee;margin:10px 0;">
    <div><strong>Товары</strong></div>
    ${itemsHtml}
  `;
}

window.openOrder = async function (orderId) {
  try {
    const o = await api(`/orders/${orderId}`);
    $("order-detail-title").textContent = `Заказ #${o.id}`;
    $("order-detail-content").innerHTML = renderOrderDetailHtml(o);
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

const EMPTY_FEED =
  '<div class="item small">Пусто: всё промаплено или нет совпадений с фильтром.</div>';

async function loadMappingStats() {
  const el = $("map-stats");
  if (!el) return;
  try {
    const s = await api("/admin/mapping-stats");
    const extra =
      s.mappings_db_rows != null && Number(s.mappings_db_rows) !== Number(s.mapped_count)
        ? ` · записей в таблице маппинга: ${s.mappings_db_rows}`
        : "";
    el.textContent = `Фид: ${s.feed_variants_total} · С маппингом: ${s.mapped_count} · Без: ${s.unmapped_count} · Кэш МС: ${s.ms_cache_rows}${extra}`;
    el.style.color = "#374151";
  } catch (e) {
    el.textContent = `Счётчики: ${e.message}`;
    el.style.color = "#b91c1c";
  }
}

async function refreshFeed() {
  setMsg("map-msg", "Качаю YML и обновляю фид…");
  setBothWrapLoading(true);
  try {
    const data = await api("/admin/feed/refresh", { method: "POST" });
    mapWizardPhase = 2;
    updateMapWizardUI();
    setMsg("map-msg", `Фид: ${data.products_count} товаров · дальше кэш МС`, true);
    await loadFeedProducts({ skipFeedLoading: true });
    toast(`Фид обновлён: ${data.products_count} товаров`, true);
  } catch (e) {
    setMsg("map-msg", `Ошибка: ${e.message}`);
    toast(`Фид: ${e.message}`, false);
  } finally {
    setBothWrapLoading(false);
  }
}

function clearMappingForm() {
  $("map-tilda-key").value = "";
  $("map-ms-href").value = "";
  $("map-ms-id").value = "";
  $("map-ms-name").value = "";
  $("ms-q").value = "";
  $("ms-list").innerHTML = '<div class="item small">Сброс. Выбери слева или найди в МС.</div>';
  selectedFeedItem = null;
  setMsg("map-msg", "Сброшено.", true);
}

function resetMappingUiAfterSave() {
  $("map-tilda-key").value = "";
  $("map-ms-href").value = "";
  $("map-ms-id").value = "";
  $("map-ms-name").value = "";
  $("ms-list").innerHTML =
    '<div class="item small">Связка сохранена — эта позиция убрана из списка слева. Выбери следующую или поиск справа.</div>';
  selectedFeedItem = null;
}

async function loadFeedProducts(opts = {}) {
  const skipFeedLoading = !!opts.skipFeedLoading;
  if (!skipFeedLoading) setFeedWrapLoading(true);
  try {
  const q = $("feed-q").value.trim();
  const rows = await api(`/admin/feed-products?limit=100000&unmapped_only=true&q=${encodeURIComponent(q)}`);
  $("feed-list").innerHTML = rows.map((r) => {
    const tu = String(r.tilda_url || "").trim();
    const tildaLink = tu
      ? `<div class="small"><a href="${esc(tu)}" target="_blank" rel="noopener noreferrer">На сайте ↗</a></div>`
      : "";
    return `
    <div class="item">
      <div><strong>${esc(r.name)}</strong></div>
      <div class="small mono">key: ${esc(r.tilda_key)}</div>
      ${tildaLink}
      <button type="button" class="secondary btn-pick-feed"
        data-k="${encodeURIComponent(String(r.tilda_key))}"
        data-name="${encodeURIComponent(String(r.name || ""))}">Выбрать</button>
    </div>`;
  }).join("") || EMPTY_FEED;
  await loadMappingStats();
  } finally {
    if (!skipFeedLoading) setFeedWrapLoading(false);
  }
}

/** Автоподбор топ-N из кэша МС по названию фида + key (серверный скоринг). */
async function suggestMsForFeed(feedName, tildaKey) {
  setMsWrapLoading(true);
  try {
  const params = new URLSearchParams({
    feed_name: feedName || "",
    tilda_key: tildaKey || "",
    limit: "8",
  });
  const rows = await api(`/admin/moysklad/cache/suggest?${params.toString()}`);
  renderMsList(rows, { mode: "suggest" });
  if (!rows.length) {
    $("ms-q").value = (feedName || "").replace(/\s*-\s*.*$/, "").trim() || tildaKey;
    await searchMs({ skipMsLoading: true });
    setMsg("map-msg", "Нет авто-совпадений — смотри поиск справа.", false);
    return;
  }
  setMsg("map-msg", `${rows.length} кандидатов · «Выбрать» → «Сохранить»`, true);
  } finally {
    setMsWrapLoading(false);
  }
}

async function searchMs(opts = {}) {
  const skipMsLoading = !!opts.skipMsLoading;
  if (!skipMsLoading) setMsWrapLoading(true);
  try {
  const q = $("ms-q").value.trim();
  const rows = await api(`/admin/moysklad/cache/search?q=${encodeURIComponent(q)}&limit=50000`);
  let finalRows = rows;
  let note = "";
  if (q && (!Array.isArray(rows) || rows.length === 0)) {
    finalRows = await api("/admin/moysklad/cache/search?q=&limit=50000");
    note = `Нет совпадений с «${q}». Показаны все ${finalRows.length} поз. из кэша (без фильтра).`;
  }
  renderMsList(finalRows, { mode: "search" });
  if (note) setMsg("map-msg", note);
  else setMsg("map-msg", `${finalRows.length} в кэше`, true);
  } finally {
    if (!skipMsLoading) setMsWrapLoading(false);
  }
}

async function refreshMsCache() {
  setMsg("map-msg", "Обновляю кэш МС...");
  setBothWrapLoading(true);
  try {
    const data = await api("/admin/moysklad/cache/refresh", { method: "POST" });
    mapWizardPhase = 3;
    updateMapWizardUI();
    setMsg("map-msg", `Кэш МС: ${data.count} поз. · слева «Показать»`, true);
    await loadMappingStats();
    toast(`Кэш МС обновлён: ${data.count} позиций`, true);
  } catch (e) {
    setMsg("map-msg", `Ошибка: ${e.message}`);
    toast(`Кэш МС: ${e.message}`, false);
  } finally {
    setBothWrapLoading(false);
  }
}

async function saveMapping() {
  const href = $("map-ms-href").value.trim();
  const idFromHref = msIdFromRemapHref(href);
  const payload = {
    tilda_key: $("map-tilda-key").value.trim(),
    ms_href: href,
    ms_id: idFromHref || $("map-ms-id").value.trim(),
    ms_name: $("map-ms-name").value.trim(),
    ms_type: inferMsTypeFromHref(href),
    note: "admin-ui",
  };
  if (!payload.tilda_key || !payload.ms_href) {
    toast("Нужны tilda key и ms href", false);
    return setMsg("map-msg", "Нужны tilda key и ms href");
  }
  try {
    await api("/admin/mappings", { method: "POST", body: JSON.stringify(payload) });
    if (payload.ms_id) $("map-ms-id").value = payload.ms_id;
    toast("Связка сохранена", true);
    setMsg("map-msg", "Сохранено — списки обновлены", true);
    resetMappingUiAfterSave();
    await loadMappings();
    await loadFeedProducts();
    await loadMappingStats();
  } catch (e) {
    toast(`Не сохранено: ${e.message}`, false);
    setMsg("map-msg", `Ошибка: ${e.message}`);
  }
}

async function deleteMappingByKey(key) {
  const k = String(key || "").trim();
  if (!k) return;
  try {
    await api(`/admin/mappings/${encodeURIComponent(k)}`, { method: "DELETE" });
    toast("Маппинг удалён", true);
    setMsg("map-msg", "Удалено — таблица и списки обновлены", true);
    await loadMappings();
    await loadFeedProducts();
    await loadMappingStats();
  } catch (e) {
    toast(`Удаление: ${e.message}`, false);
    setMsg("map-msg", `Ошибка: ${e.message}`);
  }
}

async function deleteMapping() {
  const key = $("map-delete-key").value.trim();
  if (!key) {
    toast("Введите tilda key", false);
    return setMsg("map-msg", "Введите tilda key");
  }
  await deleteMappingByKey(key);
  $("map-delete-key").value = "";
}

function renderMappingTable(rows) {
  const tb = $("mapping-tbody");
  if (!tb) return;
  if (!Array.isArray(rows) || !rows.length) {
    tb.innerHTML = '<tr><td colspan="8" class="small" style="color:#64748b;">Нет записей</td></tr>';
    return;
  }
  tb.innerHTML = rows
    .map((r) => {
      const tid = esc(String(r.tilda_key || ""));
      const keyRaw = String(r.tilda_key || "");
      const turl = String(r.tilda_url || "").trim();
      const tildaCell = turl
        ? `<a href="${esc(turl)}" target="_blank" rel="noopener noreferrer">На сайте ↗</a>`
        : `<span class="small" style="color:#94a3b8;">—</span>`;
      const msWeb = String(r.ms_web_url || "").trim();
      const msWebCell = msWeb
        ? `<a href="${esc(msWeb)}" target="_blank" rel="noopener noreferrer">В МС ↗</a>`
        : `<span class="small" style="color:#94a3b8;">—</span>`;
      const href = esc(String(r.ms_href || ""));
      return `
      <tr>
        <td class="mono">${esc(r.id ?? "")}</td>
        <td class="mono">${tid}</td>
        <td>${tildaCell}</td>
        <td>${esc(r.ms_name || r.ms_id || "—")}</td>
        <td>${msWebCell}</td>
        <td class="mono">${href}</td>
        <td class="small">${esc(r.updated_at || "")}<div style="color:#64748b;">${esc(r.updated_by || "")}</div></td>
        <td class="cell-actions">
          <button type="button" class="secondary btn-table btn-del-mapping" data-key="${encodeURIComponent(keyRaw)}">Удалить</button>
        </td>
      </tr>`;
    })
    .join("");
}

async function loadMappings() {
  const tb = $("mapping-tbody");
  try {
    const rows = await api("/admin/mappings?limit=10000");
    renderMappingTable(rows);
  } catch (e) {
    if (tb) tb.innerHTML = `<tr><td colspan="8" class="small" style="color:#b91c1c;">Ошибка: ${esc(e.message)}</td></tr>`;
    toast(`Список маппингов: ${e.message}`, false);
  }
}

async function sendBroadcast() {
  const text = $("broadcast-text").value.trim();
  const dry_run = $("broadcast-dry").checked;
  if (!text) return setMsg("broadcast-msg", "Пустой текст");
  setMsg("broadcast-msg", "Запуск...");
  try {
    const data = await api("/admin/broadcast", {
      method: "POST",
      body: JSON.stringify({ text, parse_mode: "HTML", dry_run }),
    });
    setMsg("broadcast-msg", JSON.stringify(data), true);
  } catch (e) {
    setMsg("broadcast-msg", `Ошибка: ${e.message}`);
  }
}

function bindMappingClicks() {
  $("feed-list").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btn-pick-feed");
    if (!btn || !btn.dataset.k) return;
    const key = decodeURIComponent(btn.dataset.k);
    const name = decodeURIComponent(btn.dataset.name || "");
    selectedFeedItem = { key, name };
    $("map-tilda-key").value = key;
    // По key в МС обычно не ищется; первичный поиск лучше по названию позиции.
    $("ms-q").value = (name || "").replace(/\s*-\s*.*$/, "").trim() || key;
    $("map-ms-href").value = "";
    $("map-ms-id").value = "";
    $("map-ms-name").value = "";
    setMsg("map-msg", "Ищу в МС…", true);
    suggestMsForFeed(name, key).catch((e) => setMsg("map-msg", e.message));
  });
  $("ms-list").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btn-pick-ms");
    if (!btn) return;
    const href = decodeURIComponent(btn.dataset.href || "");
    const midRaw = decodeURIComponent(btn.dataset.mid || "");
    const mid = msIdFromRemapHref(href) || midRaw;
    $("map-ms-href").value = href;
    $("map-ms-id").value = mid;
    $("map-ms-name").value = decodeURIComponent(btn.dataset.mname || "");
    setMsg("map-msg", "Подставлено из кэша (id = конец API-ссылки, как в заказах). «Сохранить»", true);
  });
  const mtb = $("mapping-tbody");
  if (mtb) {
    mtb.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".btn-del-mapping");
      if (!btn || btn.dataset.key == null) return;
      const key = decodeURIComponent(btn.dataset.key);
      if (!key) return;
      deleteMappingByKey(key);
    });
  }
}

function bind() {
  $("btn-login").addEventListener("click", login);
  $("btn-logout").addEventListener("click", logout);
  $("btn-orders-refresh").addEventListener("click", loadOrders);
  $("orders-q").addEventListener("input", renderOrders);
  $("orders-status").addEventListener("change", renderOrders);
  $("btn-order-back").addEventListener("click", closeOrderDetail);
  $("btn-feed-load").addEventListener("click", () =>
    loadFeedProducts()
      .then(() => {
        mapWizardPhase = 3;
        updateMapWizardUI();
      })
      .catch((e) => setMsg("map-msg", e.message)),
  );
  $("btn-feed-refresh").addEventListener("click", () => refreshFeed().catch((e) => setMsg("map-msg", e.message)));
  $("btn-ms-search").addEventListener("click", () => searchMs().catch((e) => setMsg("map-msg", e.message)));
  let msSearchTimer = null;
  $("ms-q").addEventListener("input", () => {
    clearTimeout(msSearchTimer);
    msSearchTimer = setTimeout(() => searchMs().catch((e) => setMsg("map-msg", e.message)), 380);
  });
  $("btn-ms-refresh").addEventListener("click", refreshMsCache);
  $("btn-map-save").addEventListener("click", saveMapping);
  $("btn-map-clear").addEventListener("click", clearMappingForm);
  $("btn-map-delete").addEventListener("click", deleteMapping);
  $("btn-map-list").addEventListener("click", loadMappings);
  $("btn-broadcast").addEventListener("click", sendBroadcast);
  bindMappingClicks();
  setupTabs();
  updateMapWizardUI();
}

bind();
checkMe();
