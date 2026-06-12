/**
 * Panel admin Tienda Mágica — Feature 012.
 * SPA vanilla: hash-routing, sesión Bearer en sessionStorage, render por vista.
 */
(function () {
  'use strict';

  const API = '/v1/admin';
  const $ = (id) => document.getElementById(id);
  const content = () => $('content');

  const fmtCOP = (n) => '$' + Math.round(n).toLocaleString('es-CO');
  const fmtDate = (iso) => (iso || '').slice(0, 16).replace('T', ' ');
  const esc = (s) =>
    String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

  /* ── Sesión ── */
  const getToken = () => sessionStorage.getItem('tm_admin_token');

  async function apiFetch(path, options = {}) {
    const resp = await fetch(API + path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + getToken(),
        ...(options.headers || {}),
      },
    });
    if (resp.status === 401) {
      sessionStorage.removeItem('tm_admin_token');
      sessionStorage.setItem('tm_admin_return', location.hash);
      showLogin();
      throw new Error('session');
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.detail || 'error';
      throw new Error(detail);
    }
    return data;
  }

  let mfaToken = '';

  function showLogin() {
    $('app-view').setAttribute('hidden', '');
    $('mfa-view').setAttribute('hidden', '');
    $('login-view').removeAttribute('hidden');
    $('login-password').focus();
  }

  function showMfa(whatsappAvailable) {
    $('login-view').setAttribute('hidden', '');
    $('app-view').setAttribute('hidden', '');
    $('mfa-view').removeAttribute('hidden');
    $('mfa-error').textContent = '';
    $('mfa-wa-msg').textContent = '';
    $('mfa-code').value = '';
    $('mfa-wa-btn').style.display = whatsappAvailable ? '' : 'none';
    $('mfa-code').focus();
  }

  function showApp() {
    $('login-view').setAttribute('hidden', '');
    $('mfa-view').setAttribute('hidden', '');
    $('app-view').removeAttribute('hidden');
    const ret = sessionStorage.getItem('tm_admin_return');
    sessionStorage.removeItem('tm_admin_return');
    location.hash = ret || location.hash || '#/dashboard';
    route();
  }

  async function doLogin(e) {
    e.preventDefault();
    const btn = $('login-submit');
    btn.disabled = true;
    $('login-error').textContent = '';
    try {
      const resp = await fetch(API + '/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: $('login-password').value }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        $('login-error').textContent =
          resp.status === 429
            ? 'Demasiados intentos — espera 15 minutos'
            : 'Contraseña incorrecta';
        return;
      }
      $('login-password').value = '';
      if (data.mfa_required) {
        mfaToken = data.mfa_token;
        showMfa(data.whatsapp_available);
        return;
      }
      sessionStorage.setItem('tm_admin_token', data.token);
      showApp();
    } catch {
      $('login-error').textContent = 'Error de conexión';
    } finally {
      btn.disabled = false;
    }
  }

  async function doMfaVerify(e) {
    e.preventDefault();
    const btn = $('mfa-submit');
    btn.disabled = true;
    $('mfa-error').textContent = '';
    try {
      const resp = await fetch(API + '/login/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mfa_token: mfaToken, code: $('mfa-code').value.trim() }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        $('mfa-error').textContent = 'Código incorrecto o expirado';
        return;
      }
      sessionStorage.setItem('tm_admin_token', data.token);
      showApp();
    } catch {
      $('mfa-error').textContent = 'Error de conexión';
    } finally {
      btn.disabled = false;
    }
  }

  async function doMfaWhatsApp() {
    const btn = $('mfa-wa-btn');
    btn.disabled = true;
    $('mfa-wa-msg').textContent = 'Enviando…';
    try {
      const resp = await fetch(API + '/login/whatsapp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mfa_token: mfaToken }),
      });
      $('mfa-wa-msg').textContent = resp.ok
        ? '✅ Código enviado a tu WhatsApp'
        : 'No se pudo enviar el código';
    } catch {
      $('mfa-wa-msg').textContent = 'Error de conexión';
    } finally {
      btn.disabled = false;
    }
  }

  /* ── Helpers de render ── */
  const errCard = (msg) => `<div class="card"><p class="error">⚠️ ${esc(msg)}</p></div>`;
  const emptyState = (msg) => `<div class="empty">${esc(msg)}</div>`;
  const statusBadge = (s) => `<span class="badge ${esc(s)}">${esc(s)}</span>`;

  function bars(entries, total, cls = '') {
    if (!entries.length) return emptyState('Sin datos en el período');
    return entries
      .map(
        ([label, value]) => `
      <div class="bar-row">
        <span class="bar-label" title="${esc(label)}">${esc(label)}</span>
        <div class="bar-track"><div class="bar-fill ${cls}" style="width:${total ? Math.round((value / total) * 100) : 0}%"></div></div>
        <span class="bar-num">${value}</span>
      </div>`
      )
      .join('');
  }

  /* ── Vista: Dashboard ── */
  async function viewDashboard() {
    const period = sessionStorage.getItem('tm_admin_period') || '7d';
    content().innerHTML = `
      <div class="toolbar">
        <select id="period-sel" aria-label="Período">
          <option value="today">Hoy</option>
          <option value="7d">Últimos 7 días</option>
          <option value="30d">Últimos 30 días</option>
        </select>
      </div>
      <div id="dash-body">Cargando…</div>`;
    $('period-sel').value = period;
    $('period-sel').addEventListener('change', (e) => {
      sessionStorage.setItem('tm_admin_period', e.target.value);
      viewDashboard();
    });

    try {
      const s = await apiFetch(`/stats?period=${period}`);
      const totalPay = Object.values(s.by_payment).reduce((a, b) => a + b, 0);
      const totalUnits = s.top_products.reduce((a, p) => a + p.units, 0);
      $('dash-body').innerHTML = `
        <div class="metric-grid">
          <div class="metric"><div class="value">${fmtCOP(s.revenue)}</div><div class="label">Ventas</div></div>
          <div class="metric profit"><div class="value">${fmtCOP(s.estimated_profit)}</div><div class="label">Ganancia estimada</div></div>
          <div class="metric"><div class="value">${s.orders}</div><div class="label">Órdenes</div></div>
          <div class="metric"><div class="value">${fmtCOP(s.avg_ticket)}</div><div class="label">Ticket promedio</div></div>
        </div>
        <div class="card"><h2>Órdenes por estado</h2>${bars(Object.entries(s.by_status), Object.values(s.by_status).reduce((a, b) => a + b, 0))}</div>
        <div class="card"><h2>Método de pago</h2>${bars(
          Object.entries(s.by_payment).map(([k, v]) => [k === 'cod' ? '🏠 Contraentrega' : '💳 En línea', v]),
          totalPay,
          'cta'
        )}</div>
        <div class="card"><h2>Top productos</h2>${bars(s.top_products.map((p) => [p.name, p.units]), totalUnits)}</div>`;
    } catch (e) {
      if (e.message !== 'session') $('dash-body').innerHTML = errCard('No pudimos cargar las estadísticas de la tienda');
    }
  }

  /* ── Vista: Pedidos ── */
  let ordersPage = 1;

  async function viewOrders() {
    content().innerHTML = `
      <div class="toolbar">
        <select id="orders-status">
          <option value="">Todos los estados</option>
          ${['processing', 'completed', 'cancelled', 'on-hold', 'pending'].map((s) => `<option>${s}</option>`).join('')}
        </select>
        <input type="search" id="orders-search" placeholder="Buscar nombre o teléfono…">
        <button type="button" class="btn-primary" id="orders-go">Buscar</button>
      </div>
      <div id="orders-body">Cargando…</div>
      <div id="orders-detail"></div>`;
    $('orders-go').addEventListener('click', () => { ordersPage = 1; loadOrders(); });
    $('orders-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') { ordersPage = 1; loadOrders(); } });
    $('orders-status').addEventListener('change', () => { ordersPage = 1; loadOrders(); });
    loadOrders();
  }

  async function loadOrders() {
    const status = $('orders-status').value;
    const search = $('orders-search').value.trim();
    const q = new URLSearchParams({ page: ordersPage, per_page: 20 });
    if (status) q.set('status', status);
    if (search) q.set('search', search);
    $('orders-body').innerHTML = 'Cargando…';
    try {
      const data = await apiFetch('/orders?' + q);
      if (!data.items.length) { $('orders-body').innerHTML = emptyState('Sin pedidos que coincidan'); return; }
      $('orders-body').innerHTML = `
        <table>
          <thead><tr><th>#</th><th>Cliente</th><th>Total</th><th>Estado</th><th>Pago</th><th>Dropi</th><th>Fecha</th></tr></thead>
          <tbody>${data.items
            .map(
              (o) => `<tr class="clickable" data-order="${o.id}">
              <td>${o.number}</td>
              <td>${esc(o.customer_name)}<br><small>${esc(o.phone)}</small></td>
              <td>${fmtCOP(o.total)}</td>
              <td>${statusBadge(o.status)}</td>
              <td>${o.payment_method === 'cod' ? '🏠 COD' : '💳'}</td>
              <td>${o.dropi_synced ? '✅ ' + esc(o.dropi_order_id || '') : o.dropi_note ? '⚠️' : '—'}</td>
              <td>${fmtDate(o.date)}</td></tr>`
            )
            .join('')}</tbody>
        </table>
        <div class="pager">
          <button type="button" class="btn-ghost" id="pg-prev" ${ordersPage <= 1 ? 'disabled' : ''}>← Anterior</button>
          <span>Página ${ordersPage} · ${data.total} pedidos</span>
          <button type="button" class="btn-ghost" id="pg-next" ${ordersPage * 20 >= data.total ? 'disabled' : ''}>Siguiente →</button>
        </div>`;
      $('pg-prev').addEventListener('click', () => { ordersPage--; loadOrders(); });
      $('pg-next').addEventListener('click', () => { ordersPage++; loadOrders(); });
      document.querySelectorAll('[data-order]').forEach((tr) =>
        tr.addEventListener('click', () => openOrder(tr.dataset.order))
      );
    } catch (e) {
      if (e.message !== 'session') $('orders-body').innerHTML = errCard('No pudimos cargar los pedidos');
    }
  }

  async function openOrder(id) {
    $('orders-detail').innerHTML = '<div class="card">Cargando detalle…</div>';
    try {
      const o = await apiFetch('/orders/' + id);
      $('orders-detail').innerHTML = `
        <div class="card detail-panel">
          <h2>Pedido #${o.number} ${statusBadge(o.status)}</h2>
          <p><strong>${esc(o.customer_name)}</strong> · 📱 ${esc(o.phone)}<br>
          📍 ${esc(o.address)} ${esc(o.address_extra)} — ${esc(o.city)}, ${esc(o.state)}<br>
          💰 ${esc(o.payment_method_title)} · ${o.cod_modal ? 'vía modal COD' : 'checkout estándar'}<br>
          🚚 Dropi: ${o.dropi_synced ? '✅ orden ' + esc(o.dropi_order_id) : o.dropi_note ? '⚠️ ' + esc(o.dropi_note) : 'no aplica'}</p>
          <table class="keep-cols">
            <thead><tr><th>Producto</th><th>Cant.</th><th>Total</th></tr></thead>
            <tbody>${o.items.map((i) => `<tr><td>${esc(i.name)}</td><td>${i.quantity}</td><td>${fmtCOP(i.total)}</td></tr>`).join('')}</tbody>
          </table>
          <div class="toolbar" style="margin-top:var(--space-sm)">
            <select id="order-status-sel">${['processing', 'completed', 'cancelled', 'on-hold']
              .map((s) => `<option ${s === o.status ? 'selected' : ''}>${s}</option>`)
              .join('')}</select>
            <button type="button" class="btn-primary" id="order-status-save">Cambiar estado</button>
            <span id="order-status-msg" class="error"></span>
          </div>
          ${o.notes.length ? `<h2>Notas</h2>${o.notes.map((n) => `<p><small>${fmtDate(n.date)}</small> — ${esc(n.note)}</p>`).join('')}` : ''}
        </div>`;
      $('order-status-save').addEventListener('click', async () => {
        const status = $('order-status-sel').value;
        if (!confirm(`¿Cambiar el pedido #${o.number} a "${status}"?`)) return;
        try {
          await apiFetch(`/orders/${id}/status`, { method: 'PUT', body: JSON.stringify({ status }) });
          loadOrders();
          openOrder(id);
        } catch (e) {
          $('order-status-msg').textContent = 'No se pudo cambiar: ' + e.message;
        }
      });
    } catch (e) {
      if (e.message !== 'session') $('orders-detail').innerHTML = errCard('No pudimos cargar el detalle');
    }
  }

  /* ── Vista: Clientes ── */
  async function viewCustomers() {
    content().innerHTML = `
      <div class="toolbar">
        <input type="search" id="cust-search" placeholder="Buscar nombre o teléfono…">
        <button type="button" class="btn-primary" id="cust-go">Buscar</button>
      </div>
      <div id="cust-body">Cargando…</div>`;
    const load = async () => {
      const search = $('cust-search').value.trim();
      $('cust-body').innerHTML = 'Cargando…';
      try {
        const data = await apiFetch('/customers' + (search ? '?search=' + encodeURIComponent(search) : ''));
        if (!data.items.length) { $('cust-body').innerHTML = emptyState('Sin clientes aún'); return; }
        $('cust-body').innerHTML = `
          <table>
            <thead><tr><th>Cliente</th><th>Teléfono</th><th>Ciudad</th><th>Compras</th><th>Total</th><th>Última</th></tr></thead>
            <tbody>${data.items
              .map(
                (c, i) => `<tr class="clickable" data-cust="${i}">
                <td>${esc(c.name) || '—'}</td><td>${esc(c.phone)}</td><td>${esc(c.city)}</td>
                <td>${c.orders_count}</td><td>${fmtCOP(c.total_spent)}</td><td>${fmtDate(c.last_order_date)}</td></tr>
                <tr hidden data-cust-detail="${i}"><td colspan="6">${c.orders
                  .map((o) => `#${o.id} · ${fmtDate(o.date)} · ${fmtCOP(o.total)} · ${esc(o.status)}`)
                  .join('<br>')}</td></tr>`
              )
              .join('')}</tbody>
          </table>`;
        document.querySelectorAll('[data-cust]').forEach((tr) =>
          tr.addEventListener('click', () => {
            const d = document.querySelector(`[data-cust-detail="${tr.dataset.cust}"]`);
            if (d) d.hidden = !d.hidden;
          })
        );
      } catch (e) {
        if (e.message !== 'session') $('cust-body').innerHTML = errCard('No pudimos cargar los clientes');
      }
    };
    $('cust-go').addEventListener('click', load);
    $('cust-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') load(); });
    load();
  }

  /* ── Vista: Productos ── */
  async function viewProducts() {
    content().innerHTML = '<div id="prod-body">Cargando…</div>';
    try {
      const data = await apiFetch('/products');
      if (!data.items.length) { $('prod-body').innerHTML = emptyState('Sin productos'); return; }
      $('prod-body').innerHTML = `
        <div class="card"><h2>Productos (${data.items.length})</h2>
        <table class="keep-cols">
          <thead><tr><th></th><th>Producto</th><th>Precio</th><th>Stock</th><th>Margen</th><th></th></tr></thead>
          <tbody>${data.items
            .map(
              (p) => `<tr data-prod="${p.id}">
              <td><img src="${esc(p.image)}" alt="" loading="lazy"></td>
              <td>${esc(p.name)}<br><span class="badge ${p.origin}">${p.origin === 'dropi' ? 'Dropi' : 'Propio'}</span></td>
              <td><input class="inline-edit" type="number" min="1" step="100" value="${p.price}" data-field="price" aria-label="Precio de ${esc(p.name)}"></td>
              <td><input class="inline-edit" type="number" min="0" step="1" value="${p.stock ?? ''}" data-field="stock" aria-label="Stock de ${esc(p.name)}"></td>
              <td>${
                p.origin === 'dropi'
                  ? p.margin_alert
                    ? `<span class="badge alert">⚠️ ${fmtCOP(p.margin)}</span>`
                    : `<span class="badge ok">${fmtCOP(p.margin)}</span>`
                  : '—'
              }</td>
              <td><button type="button" class="btn-primary" data-save="${p.id}">Guardar</button><span class="error" data-msg="${p.id}"></span></td>
              </tr>`
            )
            .join('')}</tbody>
        </table>
        <p><small>Margen = precio − costo Dropi − flete estimado. Alerta cuando ≤ 0: Dropi rechaza la orden.</small></p></div>`;
      document.querySelectorAll('[data-save]').forEach((btn) =>
        btn.addEventListener('click', async () => {
          const id = btn.dataset.save;
          const row = document.querySelector(`[data-prod="${id}"]`);
          const price = parseFloat(row.querySelector('[data-field="price"]').value);
          const stockRaw = row.querySelector('[data-field="stock"]').value;
          const body = { price };
          if (stockRaw !== '') body.stock = parseInt(stockRaw, 10);
          btn.disabled = true;
          try {
            await apiFetch('/products/' + id, { method: 'PUT', body: JSON.stringify(body) });
            viewProducts();
          } catch (e) {
            document.querySelector(`[data-msg="${id}"]`).textContent = e.message;
            btn.disabled = false;
          }
        })
      );
    } catch (e) {
      if (e.message !== 'session') $('prod-body').innerHTML = errCard('No pudimos cargar los productos');
    }
  }

  /* ── Vista: IA ── */
  async function viewAI() {
    content().innerHTML = '<div id="ai-body">Cargando…</div>';
    try {
      const [metrics, convs] = await Promise.all([
        apiFetch('/ai/metrics'),
        apiFetch('/ai/conversations?limit=20'),
      ]);
      const intentTotal = Object.values(metrics.intents).reduce((a, b) => a + b, 0);
      const intentLabels = { buy: '🛒 Compra', recommend: '✨ Recomendación', track: '📦 Rastreo', chat: '💬 Conversación', other: '❓ Otro' };
      $('ai-body').innerHTML = `
        <div class="metric-grid">
          <div class="metric"><div class="value">${metrics.conversations}</div><div class="label">Conversaciones</div></div>
          <div class="metric"><div class="value">${metrics.messages}</div><div class="label">Mensajes</div></div>
        </div>
        <div class="card"><h2>Intenciones</h2>${bars(
          Object.entries(metrics.intents).map(([k, v]) => [intentLabels[k] || k, v]),
          intentTotal
        )}</div>
        <div class="card"><h2>Últimas conversaciones</h2>
          ${
            convs.items.length
              ? convs.items
                  .map(
                    (c) => `<p class="clickable" data-conv="${esc(c.session_id)}" tabindex="0" role="button">
                    <small>${fmtDate(c.date)} · ${c.messages} mensajes</small><br>${esc(c.first_message) || '(sesión sin mensajes)'}</p>`
                  )
                  .join('')
              : emptyState('Aún no hay conversaciones registradas')
          }
          <div id="conv-detail"></div>
        </div>`;
      document.querySelectorAll('[data-conv]').forEach((p) =>
        p.addEventListener('click', async () => {
          const d = await apiFetch('/ai/conversations/' + p.dataset.conv);
          $('conv-detail').innerHTML =
            '<hr>' +
            d.messages
              .map((m) => `<div class="msg ${esc(m.role)}">${esc(m.content)}${m.intent ? `<br><small>intent: ${esc(m.intent)}</small>` : ''}</div>`)
              .join('');
        })
      );
    } catch (e) {
      if (e.message !== 'session') $('ai-body').innerHTML = errCard('No pudimos cargar las métricas del asistente');
    }
  }

  /* ── Router ── */
  const routes = {
    dashboard: viewDashboard,
    orders: viewOrders,
    customers: viewCustomers,
    products: viewProducts,
    ai: viewAI,
  };

  function route() {
    if (!getToken()) { showLogin(); return; }
    const name = (location.hash || '#/dashboard').replace('#/', '') || 'dashboard';
    const view = routes[name] || viewDashboard;
    document.querySelectorAll('#sidenav a').forEach((a) =>
      a.classList.toggle('active', a.dataset.nav === name)
    );
    view();
  }

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded', async () => {
    $('login-form').addEventListener('submit', doLogin);
    $('mfa-form').addEventListener('submit', doMfaVerify);
    $('mfa-wa-btn').addEventListener('click', doMfaWhatsApp);
    $('logout-btn').addEventListener('click', async () => {
      try { await apiFetch('/logout', { method: 'POST' }); } catch { /* sesión ya inválida */ }
      sessionStorage.removeItem('tm_admin_token');
      showLogin();
    });
    window.addEventListener('hashchange', route);

    if (getToken()) {
      try {
        await apiFetch('/me');
        showApp();
        return;
      } catch { /* cae al login */ }
    }
    showLogin();
  });
})();
