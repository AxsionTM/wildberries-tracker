/* WB Monitor — Telegram Mini App frontend. Vanilla JS, без сборки и зависимостей,
 * чтобы приложение грузилось мгновенно внутри Telegram WebView. */

(() => {
  "use strict";

  // ------------------------------------------------------------------
  // Telegram WebApp bootstrap
  // ------------------------------------------------------------------
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  function applyTheme() {
    const root = document.documentElement;
    const p = (tg && tg.themeParams) || {};
    const map = {
      "--tg-bg": p.bg_color,
      "--tg-secondary-bg": p.secondary_bg_color,
      "--tg-text": p.text_color,
      "--tg-hint": p.hint_color,
      "--tg-link": p.link_color,
      "--tg-button": p.button_color,
      "--tg-button-text": p.button_text_color,
    };
    for (const [cssVar, value] of Object.entries(map)) {
      if (value) root.style.setProperty(cssVar, value);
    }
  }

  if (tg) {
    tg.ready();
    tg.expand();
    applyTheme();
    tg.onEvent("themeChanged", applyTheme);
    try { tg.setHeaderColor("secondary_bg_color"); } catch (e) { /* старые клиенты */ }
  }

  function initDataHeader() {
    if (tg && tg.initData) return "tma " + tg.initData;
    // Вне Telegram (обычный браузер) — работать не будет без WEBAPP_DEV_MODE
    // и параметра ?dev=<telegram_id> в адресной строке, см. README.
    const params = new URLSearchParams(window.location.search);
    const devId = params.get("dev");
    if (devId) return "tma dev:" + devId;
    return "";
  }

  function haptic(kind) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (kind === "success" || kind === "error" || kind === "warning") {
        tg.HapticFeedback.notificationOccurred(kind);
      } else {
        tg.HapticFeedback.impactOccurred(kind || "light");
      }
    } catch (e) { /* noop */ }
  }

  // ------------------------------------------------------------------
  // API helper
  // ------------------------------------------------------------------
  async function api(path, options = {}) {
    const res = await fetch("/api" + path, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        "Authorization": initDataHeader(),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    if (!res.ok) {
      let detail = "Ошибка запроса";
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch (e) { /* тело не json */ }
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  // ------------------------------------------------------------------
  // Small utils
  // ------------------------------------------------------------------
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatRub(value) {
    if (value === null || value === undefined) return "—";
    return Math.round(value).toLocaleString("ru-RU") + " ₽";
  }

  function formatDate(iso) {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  let toastTimer = null;
  function toast(message) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2400);
  }

  function confirmAction(message) {
    return new Promise((resolve) => {
      if (tg && tg.showConfirm) {
        tg.showConfirm(message, (ok) => resolve(!!ok));
      } else {
        resolve(window.confirm(message));
      }
    });
  }

  // ------------------------------------------------------------------
  // App state
  // ------------------------------------------------------------------
  const state = {
    tab: "products",
    me: null,
    products: [],
    total: 0,
    loadingProducts: false,
    fields: [],
  };

  const viewEl = document.getElementById("view");
  const tabs = Array.from(document.querySelectorAll(".tab"));
  const bellBtn = document.getElementById("notifBell");
  const userSubtitle = document.getElementById("userSubtitle");

  function setActiveTab(tab) {
    state.tab = tab;
    tabs.forEach((btn) => btn.classList.toggle("is-active", btn.dataset.tab === tab));
    render();
  }

  tabs.forEach((btn) => btn.addEventListener("click", () => { haptic("light"); setActiveTab(btn.dataset.tab); }));

  bellBtn.addEventListener("click", async () => {
    if (!state.me) return;
    const next = !state.me.notifications_enabled;
    bellBtn.disabled = true;
    try {
      state.me = await api("/me", { method: "PATCH", body: { notifications_enabled: next } });
      updateBell();
      toast(next ? "🔔 Уведомления включены" : "🔕 Уведомления выключены");
      haptic("success");
    } catch (e) {
      toast(e.message);
      haptic("error");
    } finally {
      bellBtn.disabled = false;
    }
  });

  function updateBell() {
    if (!state.me) return;
    bellBtn.classList.toggle("is-on", state.me.notifications_enabled);
  }

  // ------------------------------------------------------------------
  // Router-ish render
  // ------------------------------------------------------------------
  let detailProductId = null;

  function render() {
    if (detailProductId !== null) {
      renderDetail(detailProductId);
      return;
    }
    if (state.tab === "products") renderProductsList();
    else if (state.tab === "add") renderAdd();
    else if (state.tab === "export") renderExport();
  }

  function openDetail(id) {
    detailProductId = id;
    render();
  }

  function closeDetail() {
    detailProductId = null;
    render();
  }

  // ------------------------------------------------------------------
  // Products list
  // ------------------------------------------------------------------
  async function loadProducts() {
    state.loadingProducts = true;
    try {
      const data = await api("/products?page=0&per_page=100");
      state.products = data.items;
      state.total = data.total;
    } finally {
      state.loadingProducts = false;
    }
  }

  function trendBadge(p) {
    if (p.price_change_percent === null || p.price_change_percent === undefined) return "";
    if (Math.abs(p.price_change_percent) < 0.05) return `<span class="pcard__trend flat"></span>`;
    const down = p.price_change_percent < 0;
    return `<span class="pcard__trend ${down ? "down" : "up"}">${down ? "↓" : "↑"} ${Math.abs(p.price_change_percent).toFixed(1)}%</span>`;
  }

  function productCardHtml(p) {
    const name = escapeHtml(p.name || `Артикул ${p.nm_id}`);
    const badge = escapeHtml(p.brand || p.category || "Wildberries");
    return `
      <button class="pcard ${p.is_paused ? "is-paused" : ""}" data-id="${p.id}" type="button">
        <div class="pcard__top">
          <span class="pcard__badge">${badge}</span>
          ${trendBadge(p)}
        </div>
        <p class="pcard__name">${name}</p>
        <div class="pcard__row">
          <div class="pcard__price">
            <span class="pcard__price-now">${formatRub(p.current_price)}</span>
            ${p.price_without_discount && p.discount_percent ? `<span class="pcard__price-old">${formatRub(p.price_without_discount)}</span>` : ""}
          </div>
          ${p.discount_percent ? `<span class="pcard__discount">-${Math.round(p.discount_percent)}%</span>` : ""}
        </div>
        <div class="pcard__meta">
          ${p.rating ? `<span class="pcard__rating">⭐ ${p.rating.toFixed(1)}</span>` : ""}
          <span class="pcard__stock">${p.is_available ? `📦 ${p.stock ?? "в наличии"}` : "❌ нет в наличии"}</span>
          <span class="pcard__paused">⏸ пауза</span>
        </div>
      </button>`;
  }

  async function renderProductsList() {
    viewEl.innerHTML = `
      <p class="section-title">Мои товары ${state.total ? `· ${state.total}` : ""}</p>
      <div id="plistBox">
        <div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>
      </div>`;

    try {
      await loadProducts();
    } catch (e) {
      viewEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">⚠️</div>
        <p class="empty-state__title">Не удалось загрузить товары</p>
        <p class="empty-state__hint">${escapeHtml(e.message)}</p></div>`;
      return;
    }

    if (state.tab !== "products" || detailProductId !== null) return; // пользователь уже ушёл с экрана

    if (!state.products.length) {
      viewEl.innerHTML = `<div class="empty-state">
        <div class="empty-state__icon">🛍️</div>
        <p class="empty-state__title">Пока нет товаров</p>
        <p class="empty-state__hint">Добавь артикул или ссылку Wildberries на вкладке «Добавить» —<br/>и приложение начнёт следить за ценой.</p>
      </div>`;
      return;
    }

    viewEl.innerHTML = `
      <p class="section-title">Мои товары · ${state.total}</p>
      <div class="plist">${state.products.map(productCardHtml).join("")}</div>`;

    viewEl.querySelectorAll(".pcard").forEach((card) => {
      card.addEventListener("click", () => { haptic("light"); openDetail(Number(card.dataset.id)); });
    });
  }

  // ------------------------------------------------------------------
  // Product detail
  // ------------------------------------------------------------------
  function drawChart(canvas, points) {
    const prices = points.map((p) => p.price).filter((v) => v !== null && v !== undefined);
    if (prices.length < 2) return false;

    const dpr = window.devicePixelRatio || 1;
    const cssWidth = canvas.parentElement.clientWidth - 20;
    const cssHeight = 140;
    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    canvas.style.width = cssWidth + "px";
    canvas.style.height = cssHeight + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const padX = 6, padY = 14;
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const span = max - min || 1;
    const stepX = (cssWidth - padX * 2) / (points.length - 1);

    const xy = points.map((p, i) => {
      const v = p.price === null || p.price === undefined ? null : p.price;
      const x = padX + i * stepX;
      const y = v === null ? null : padY + (1 - (v - min) / span) * (cssHeight - padY * 2);
      return [x, y];
    }).filter(([, y]) => y !== null);

    const accentA = getComputedStyle(document.documentElement).getPropertyValue("--accent-a").trim() || "#6c2bd9";
    const accentB = getComputedStyle(document.documentElement).getPropertyValue("--accent-b").trim() || "#e0409d";

    // область под линией
    const grad = ctx.createLinearGradient(0, 0, 0, cssHeight);
    grad.addColorStop(0, hexToRgba(accentA, 0.22));
    grad.addColorStop(1, hexToRgba(accentA, 0));
    ctx.beginPath();
    ctx.moveTo(xy[0][0], cssHeight - padY);
    xy.forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.lineTo(xy[xy.length - 1][0], cssHeight - padY);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // линия
    const lineGrad = ctx.createLinearGradient(0, 0, cssWidth, 0);
    lineGrad.addColorStop(0, accentA);
    lineGrad.addColorStop(1, accentB);
    ctx.beginPath();
    xy.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.strokeStyle = lineGrad;
    ctx.lineWidth = 2.4;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    // точка на последнем значении
    const [lastX, lastY] = xy[xy.length - 1];
    ctx.beginPath();
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
    ctx.fillStyle = accentB;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#fff";
    ctx.stroke();

    return true;
  }

  function hexToRgba(hex, alpha) {
    const h = hex.replace("#", "");
    const bigint = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    const r = (bigint >> 16) & 255, g = (bigint >> 8) & 255, b = bigint & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function switchHtml(id, isOn, label, hint) {
    return `
      <div class="switch-row">
        <div>
          <div class="switch-row__label">${escapeHtml(label)}</div>
          ${hint ? `<div class="switch-row__hint">${escapeHtml(hint)}</div>` : ""}
        </div>
        <button class="switch ${isOn ? "is-on" : ""}" data-switch="${id}" type="button"></button>
      </div>`;
  }

  async function renderDetail(productId) {
    viewEl.innerHTML = `<div class="skeleton" style="height:220px"></div>`;

    let data;
    try {
      data = await api(`/products/${productId}`);
    } catch (e) {
      viewEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">⚠️</div>
        <p class="empty-state__title">Не удалось открыть товар</p>
        <p class="empty-state__hint">${escapeHtml(e.message)}</p></div>
        <button class="btn btn-secondary" id="backBtn">← Назад к списку</button>`;
      document.getElementById("backBtn").addEventListener("click", closeDetail);
      return;
    }
    if (detailProductId !== productId) return;

    const p = data.product;
    const change = p.price_change_percent;
    const changeHtml = (change === null || change === undefined || Math.abs(change) < 0.05)
      ? ""
      : `<span class="price-hero__change ${change < 0 ? "down" : "up"}">${change < 0 ? "↓" : "↑"} ${Math.abs(change).toFixed(1)}%</span>`;

    viewEl.innerHTML = `
      <div class="detail-header">
        <button class="detail-back" id="backBtn" type="button">‹ Все товары</button>
        <h2 class="detail-title">${escapeHtml(p.name || "Артикул " + p.nm_id)}</h2>
        <p class="detail-sub">${escapeHtml(p.brand || "—")} · артикул ${p.nm_id} ${p.group_name ? "· " + escapeHtml(p.group_name) : ""}</p>
      </div>

      <div class="price-hero">
        <div>
          <span class="price-hero__now">${formatRub(p.current_price)}</span>
          ${p.price_without_discount && p.discount_percent ? `<span class="price-hero__old">${formatRub(p.price_without_discount)}</span>` : ""}
        </div>
        ${changeHtml}
      </div>

      <div class="chart-wrap">
        <canvas id="priceChart"></canvas>
        <div id="chartEmpty" class="chart-wrap__empty" style="display:none">Пока недостаточно данных для графика — загляни сюда после пары обновлений цены</div>
      </div>

      <div class="stat-grid">
        <div class="stat-box"><p class="stat-box__label">Рейтинг</p><p class="stat-box__value">${p.rating ? "⭐ " + p.rating.toFixed(1) : "—"}</p></div>
        <div class="stat-box"><p class="stat-box__label">Отзывы</p><p class="stat-box__value">${p.feedbacks_count ?? "—"}</p></div>
        <div class="stat-box"><p class="stat-box__label">Остаток</p><p class="stat-box__value">${p.is_available ? (p.stock ?? "в наличии") : "нет в наличии"}</p></div>
        <div class="stat-box"><p class="stat-box__label">Продавец</p><p class="stat-box__value">${escapeHtml(p.seller || "—")}</p></div>
      </div>

      <a class="btn btn-secondary" href="${escapeHtml(p.url)}" target="_blank" rel="noopener" id="openWbBtn" style="margin-bottom:16px">Открыть на Wildberries ↗</a>

      <div class="panel">
        <p class="panel-title">Мониторинг</p>
        ${switchHtml("notifications_enabled", p.notifications_enabled, "Уведомления по товару", "Оповещать об изменениях этого товара")}
        ${switchHtml("is_paused", p.is_paused, "Пауза", "Временно не отслеживать цену/остатки", true)}
      </div>

      <div class="panel">
        <p class="panel-title">Оповещать, если</p>
        ${switchHtml("notify_price_drop", p.notify_price_drop, "Цена упала")}
        ${switchHtml("notify_price_rise", p.notify_price_rise, "Цена выросла")}
        ${switchHtml("notify_availability", p.notify_availability, "Появился/пропал из наличия")}
        ${switchHtml("notify_promo", p.notify_promo, "Попал в акцию")}
        ${switchHtml("notify_rating_change", p.notify_rating_change, "Изменился рейтинг")}
        ${switchHtml("notify_feedbacks_change", p.notify_feedbacks_change, "Появились новые отзывы")}
      </div>

      <div class="panel">
        <p class="panel-title">Пороги (необязательно)</p>
        <div style="padding:10px 2px 14px">
          <div class="field-row">
            <div class="field"><label>Цена ниже, ₽</label><input class="input" type="number" inputmode="numeric" id="priceBelow" value="${p.price_below ?? ""}" placeholder="—"></div>
            <div class="field"><label>Цена выше, ₽</label><input class="input" type="number" inputmode="numeric" id="priceAbove" value="${p.price_above ?? ""}" placeholder="—"></div>
          </div>
          <div class="field-row">
            <div class="field"><label>Изменение, %</label><input class="input" type="number" inputmode="numeric" id="thPercent" value="${p.price_threshold_percent ?? ""}" placeholder="любое"></div>
            <div class="field"><label>Изменение, ₽</label><input class="input" type="number" inputmode="numeric" id="thRub" value="${p.price_threshold_rub ?? ""}" placeholder="любое"></div>
          </div>
          <button class="btn btn-secondary" id="saveThresholdsBtn" type="button">Сохранить пороги</button>
        </div>
      </div>

      <button class="btn btn-danger" id="deleteBtn" type="button" style="margin-top:4px">Удалить из мониторинга</button>
    `;

    document.getElementById("backBtn").addEventListener("click", closeDetail);

    const canvas = document.getElementById("priceChart");
    const ok = drawChart(canvas, data.history);
    if (!ok) {
      canvas.style.display = "none";
      document.getElementById("chartEmpty").style.display = "block";
    }

    viewEl.querySelectorAll("[data-switch]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const key = btn.dataset.switch;
        const nextOn = !btn.classList.contains("is-on");
        btn.classList.toggle("is-on", nextOn);
        haptic("light");
        try {
          await api(`/products/${productId}`, { method: "PATCH", body: { [key]: nextOn } });
          if (key === "is_paused") {
            toast(nextOn ? "⏸ Мониторинг товара на паузе" : "▶️ Мониторинг возобновлён");
          }
        } catch (e) {
          btn.classList.toggle("is-on", !nextOn); // откат
          toast(e.message);
          haptic("error");
        }
      });
    });

    document.getElementById("saveThresholdsBtn").addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      const val = (id) => {
        const raw = document.getElementById(id).value.trim();
        return raw === "" ? null : Number(raw);
      };
      btn.disabled = true;
      btn.textContent = "Сохраняю…";
      try {
        await api(`/products/${productId}`, {
          method: "PATCH",
          body: {
            price_below: val("priceBelow"),
            price_above: val("priceAbove"),
            price_threshold_percent: val("thPercent"),
            price_threshold_rub: val("thRub"),
          },
        });
        toast("✅ Пороги сохранены");
        haptic("success");
      } catch (e) {
        toast(e.message);
        haptic("error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Сохранить пороги";
      }
    });

    document.getElementById("deleteBtn").addEventListener("click", async () => {
      const ok = await confirmAction("Удалить товар из мониторинга? Это действие нельзя отменить.");
      if (!ok) return;
      try {
        await api(`/products/${productId}`, { method: "DELETE" });
        toast("🗑 Товар удалён");
        haptic("success");
        closeDetail();
      } catch (e) {
        toast(e.message);
        haptic("error");
      }
    });
  }

  // ------------------------------------------------------------------
  // Add product
  // ------------------------------------------------------------------
  function renderAdd() {
    viewEl.innerHTML = `
      <p class="section-title">Добавить товар</p>
      <div class="field">
        <label>Артикул или ссылка WB</label>
        <textarea class="input" id="addInput" rows="4" placeholder="816758849&#10;https://www.wildberries.ru/catalog/816758849/detail.aspx"></textarea>
        <p class="hint-text">Можно несколько сразу — каждый артикул или ссылку с новой строки, либо через запятую.</p>
      </div>
      <button class="btn btn-primary" id="addSubmitBtn" type="button">Добавить</button>
      <div id="addResults" style="margin-top:18px"></div>
    `;

    document.getElementById("addSubmitBtn").addEventListener("click", async () => {
      const textarea = document.getElementById("addInput");
      const query = textarea.value.trim();
      const resultsBox = document.getElementById("addResults");
      if (!query) { toast("Введи артикул или ссылку"); return; }

      const btn = document.getElementById("addSubmitBtn");
      btn.disabled = true;
      btn.textContent = "Добавляю…";
      resultsBox.innerHTML = `<div class="skeleton"></div>`;

      try {
        const res = await api("/products", { method: "POST", body: { query } });
        haptic("success");
        resultsBox.innerHTML = `
          <p class="section-title">Готово: добавлено ${res.added}, уже было ${res.already}, ошибок ${res.failed}</p>
          <div class="panel">
            ${res.items.map((it) => `
              <div class="result-item">
                <span class="result-item__nm">${it.nm_id}${it.product && it.product.name ? " · " + escapeHtml(it.product.name.slice(0, 28)) : ""}</span>
                <span class="result-item__status ${it.status}">${it.status === "added" ? "добавлен" : it.status === "already" ? "уже был" : "ошибка"}</span>
              </div>`).join("")}
          </div>`;
        textarea.value = "";
        // сбрасываем кэш списка товаров, чтобы вкладка «Товары» подтянула актуальные данные
        state.products = [];
      } catch (e) {
        haptic("error");
        resultsBox.innerHTML = `<p class="hint-text" style="color:var(--bad)">${escapeHtml(e.message)}</p>`;
      } finally {
        btn.disabled = false;
        btn.textContent = "Добавить";
      }
    });
  }

  // ------------------------------------------------------------------
  // Export
  // ------------------------------------------------------------------
  async function renderExport() {
    viewEl.innerHTML = `<div class="skeleton"></div><div class="skeleton"></div>`;

    try {
      if (!state.fields.length) state.fields = await api("/fields");
      if (!state.products.length) await loadProducts();
    } catch (e) {
      viewEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">⚠️</div>
        <p class="empty-state__title">Не удалось загрузить данные</p>
        <p class="empty-state__hint">${escapeHtml(e.message)}</p></div>`;
      return;
    }
    if (state.tab !== "export" || detailProductId !== null) return;

    if (!state.products.length) {
      viewEl.innerHTML = `<div class="empty-state">
        <div class="empty-state__icon">📊</div>
        <p class="empty-state__title">Нечего выгружать</p>
        <p class="empty-state__hint">Сначала добавь хотя бы один товар в мониторинг.</p>
      </div>`;
      return;
    }

    viewEl.innerHTML = `
      <p class="section-title">Товары</p>
      <div class="panel">
        ${state.products.map((p) => `
          <label class="check-row">
            <input type="checkbox" class="export-product" value="${p.id}" checked>
            <span class="check-row__label">${escapeHtml((p.name || "Артикул " + p.nm_id).slice(0, 46))}<br/><span class="check-row__sub">${formatRub(p.current_price)}</span></span>
          </label>`).join("")}
      </div>

      <p class="section-title">Поля отчёта</p>
      <div class="panel">
        ${state.fields.map((f, i) => `
          <label class="check-row">
            <input type="checkbox" class="export-field" value="${f.key}" ${i < 5 ? "checked" : ""}>
            <span class="check-row__label">${escapeHtml(f.label.replace(/^\S+\s/, ""))}</span>
          </label>`).join("")}
      </div>

      <button class="btn btn-primary" id="exportBtn" type="button">Скачать Excel-отчёт</button>
    `;

    document.getElementById("exportBtn").addEventListener("click", async () => {
      const productIds = Array.from(document.querySelectorAll(".export-product:checked")).map((el) => Number(el.value));
      const fields = Array.from(document.querySelectorAll(".export-field:checked")).map((el) => el.value);
      if (!productIds.length) { toast("Выбери хотя бы один товар"); return; }
      if (!fields.length) { toast("Выбери хотя бы одно поле"); return; }

      const btn = document.getElementById("exportBtn");
      btn.disabled = true;
      btn.textContent = "Формирую отчёт…";
      try {
        const res = await api("/export", { method: "POST", body: { product_ids: productIds, fields } });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "wb_monitor_report.xlsx";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        toast("✅ Отчёт готов");
        haptic("success");
      } catch (e) {
        toast(e.message);
        haptic("error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Скачать Excel-отчёт";
      }
    });
  }

  // ------------------------------------------------------------------
  // Bootstrap
  // ------------------------------------------------------------------
  async function bootstrap() {
    setActiveTab("products");
    try {
      state.me = await api("/me");
      updateBell();
      userSubtitle.textContent = state.me.full_name
        ? `${state.me.full_name}${state.me.username ? " · @" + state.me.username : ""}`
        : "Мониторинг товаров Wildberries";
    } catch (e) {
      userSubtitle.textContent = "Не удалось авторизоваться";
      viewEl.innerHTML = `<div class="empty-state">
        <div class="empty-state__icon">🔒</div>
        <p class="empty-state__title">Открой приложение через Telegram</p>
        <p class="empty-state__hint">${escapeHtml(e.message)}</p>
      </div>`;
    }
  }

  bootstrap();
})();
