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
  // Celda de envío Dropi en la tabla de pedidos (feature 016)
  function dropiShipCell(o) {
    if (o.dropi_status) {
      const carrier = o.dropi_carrier ? `<br><small>${esc(o.dropi_carrier)}</small>` : '';
      return `<span class="badge dropi">${esc(o.dropi_status)}</span>${carrier}`;
    }
    if (o.dropi_synced) return '✅ ' + esc(o.dropi_order_id || '');
    if (o.dropi_note) return '⚠️';
    return '—';
  }

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

  const CHART_VARS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6'];
  const statusLabels = {
    processing: '⚙️ Procesando',
    completed: '✅ Completada',
    cancelled: '✖️ Cancelada',
    'on-hold': '⏸️ En espera',
    pending: '🕒 Pendiente',
    failed: '⚠️ Fallida',
    refunded: '↩️ Reembolsada',
  };

  /* Donut SVG-less con conic-gradient + leyenda. entries: [[label, value], …] */
  function donut(entries, centerCap = '') {
    const data = entries.filter(([, v]) => v > 0);
    const total = data.reduce((a, [, v]) => a + v, 0);
    if (!total) return emptyState('Sin datos en el período');
    let acc = 0;
    const stops = data
      .map(([, v], i) => {
        const from = (acc / total) * 360;
        acc += v;
        const to = (acc / total) * 360;
        return `var(${CHART_VARS[i % CHART_VARS.length]}) ${from}deg ${to}deg`;
      })
      .join(', ');
    const legend = data
      .map(([label, v], i) => {
        const pct = Math.round((v / total) * 100);
        return `<li>
          <span class="dot" style="background:var(${CHART_VARS[i % CHART_VARS.length]})"></span>
          <span>${esc(label)}</span>
          <b>${v} <span class="pct">${pct}%</span></b>
        </li>`;
      })
      .join('');
    return `<div class="donut-wrap">
      <div class="donut" style="background:conic-gradient(${stops})" role="img" aria-label="${esc(centerCap)}: ${total}">
        <div class="donut-hole"><span class="donut-total">${total}</span><span class="donut-cap">${esc(centerCap)}</span></div>
      </div>
      <ul class="legend">${legend}</ul>
    </div>`;
  }

  /* ── Vista: Dashboard ── */
  async function viewDashboard() {
    const period = sessionStorage.getItem('tm_admin_period') || '7d';
    content().innerHTML = `
      <div class="page-head">
        <div>
          <h1>📊 Dashboard</h1>
          <p class="sub">Resumen de ventas y operación de la tienda</p>
        </div>
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
      const totalUnits = s.top_products.reduce((a, p) => a + p.units, 0);
      $('dash-body').innerHTML = `
        <div class="metric-grid">
          <div class="metric"><div class="value">${fmtCOP(s.revenue)}</div><div class="label">Ventas</div></div>
          <div class="metric profit"><div class="value">${fmtCOP(s.estimated_profit)}</div><div class="label">Ganancia estimada</div></div>
          <div class="metric"><div class="value">${s.orders}</div><div class="label">Órdenes</div></div>
          <div class="metric"><div class="value">${fmtCOP(s.avg_ticket)}</div><div class="label">Ticket promedio</div></div>
        </div>
        <div class="chart-grid">
          <div class="card"><h2>📦 Órdenes por estado</h2>${donut(
            Object.entries(s.by_status).map(([k, v]) => [statusLabels[k] || k, v]),
            'órdenes'
          )}</div>
          <div class="card"><h2>💳 Método de pago</h2>${donut(
            Object.entries(s.by_payment).map(([k, v]) => [k === 'cod' ? '🏠 Contraentrega' : '💳 En línea', v]),
            'pagos'
          )}</div>
        </div>
        <div class="card"><h2>🏆 Top productos</h2>${bars(s.top_products.map((p) => [p.name, p.units]), totalUnits)}</div>`;
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
        <button type="button" class="btn-ghost" id="orders-sync" title="Traer estado/envío desde Dropi">🔄 Sincronizar Dropi</button>
        <span id="orders-sync-msg" class="login-sub"></span>
      </div>
      <div id="orders-body">Cargando…</div>
      <div id="orders-detail"></div>`;
    $('orders-go').addEventListener('click', () => { ordersPage = 1; loadOrders(); });
    $('orders-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') { ordersPage = 1; loadOrders(); } });
    $('orders-status').addEventListener('change', () => { ordersPage = 1; loadOrders(); });
    $('orders-sync').addEventListener('click', syncDropiOrders);
    loadOrders();
  }

  async function syncDropiOrders() {
    const btn = $('orders-sync');
    const msg = $('orders-sync-msg');
    btn.disabled = true;
    msg.textContent = 'Sincronizando con Dropi…';
    try {
      await apiFetch('/orders/sync', { method: 'POST' });
      // El sync corre en background; refrescamos tras unos segundos.
      setTimeout(() => { msg.textContent = '✅ Sincronización en curso — actualizando…'; loadOrders(); }, 4000);
      setTimeout(() => { msg.textContent = ''; loadOrders(); }, 9000);
    } catch (e) {
      msg.textContent =
        e.message === 'already_running' ? '⏳ Ya hay un sync en curso'
        : e.message === 'dropi_sync_disabled' ? '⚠️ Sync Dropi no configurado'
        : 'No se pudo iniciar el sync';
    } finally {
      btn.disabled = false;
    }
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
          <thead><tr><th>#</th><th>Cliente</th><th>Total</th><th>Estado</th><th>Pago</th><th>Envío Dropi</th><th>Fecha</th></tr></thead>
          <tbody>${data.items
            .map(
              (o) => `<tr class="clickable" data-order="${o.id}">
              <td>${o.number}</td>
              <td>${esc(o.customer_name)}<br><small>${esc(o.phone)}</small></td>
              <td>${fmtCOP(o.total)}</td>
              <td>${statusBadge(o.status)}</td>
              <td>${o.payment_method === 'cod' ? '🏠 COD' : '💳'}</td>
              <td>${dropiShipCell(o)}</td>
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
          ${o.dropi_status ? `<p class="dropi-ship">
            📦 <strong>Estado Dropi:</strong> <span class="badge dropi">${esc(o.dropi_status)}</span>
            ${o.dropi_carrier ? ` · 🚛 ${esc(o.dropi_carrier)}` : ''}
            ${o.dropi_guide ? ` · guía ${esc(o.dropi_guide)}` : ''}
            ${o.dropi_guide_url ? ` · <a href="${esc(o.dropi_guide_url)}" target="_blank" rel="noopener">ver guía</a>` : ''}
            ${o.dropi_synced_at ? `<br><small>sincronizado ${fmtDate(o.dropi_synced_at)}</small>` : ''}
          </p>` : ''}
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

  /* ── Vista: Pedidos Dropi (feature 017) ── */
  async function viewDropiOrders() {
    content().innerHTML = `
      <div class="page-head">
        <div>
          <h1>🚚 Pedidos Dropi</h1>
          <p class="sub">Pedidos directos de Dropi — incluye los que no están en la tienda</p>
        </div>
        <div class="toolbar" style="margin:0">
          <button type="button" class="btn-ghost" id="dropi-refresh">🔄 Refrescar</button>
          <button type="button" class="btn-primary" id="dropi-sync" title="Volcar estado/guía a las órdenes de la tienda">⬇️ Sincronizar a tienda</button>
          <span id="dropi-msg" class="login-sub"></span>
        </div>
      </div>
      <div id="dropi-body">Cargando…</div>`;
    $('dropi-refresh').addEventListener('click', viewDropiOrders);
    $('dropi-sync').addEventListener('click', async () => {
      const btn = $('dropi-sync');
      const msg = $('dropi-msg');
      btn.disabled = true;
      msg.textContent = 'Sincronizando a la tienda…';
      try {
        await apiFetch('/orders/sync', { method: 'POST' });
        msg.textContent = '✅ Sync en curso — revisa Pedidos en unos segundos';
      } catch (e) {
        msg.textContent =
          e.message === 'already_running' ? '⏳ Ya hay un sync en curso'
          : e.message === 'dropi_sync_disabled' ? '⚠️ Sync Dropi no configurado'
          : 'No se pudo iniciar el sync';
      } finally {
        btn.disabled = false;
      }
    });
    try {
      const data = await apiFetch('/dropi/orders');
      if (!data.items.length) { $('dropi-body').innerHTML = emptyState('Sin pedidos en Dropi'); return; }
      $('dropi-body').innerHTML = `
        <p class="login-sub">${data.total} pedidos en Dropi · ${data.in_store} también en la tienda · ${data.total - data.in_store} solo en Dropi</p>
        <table>
          <thead><tr><th>Dropi #</th><th>En tienda</th><th>Cliente</th><th>Ciudad</th><th>Total</th><th>Estado</th><th>Transportadora</th><th>Guía</th><th>Fecha</th></tr></thead>
          <tbody>${data.items
            .map(
              (o) => `<tr>
              <td>${o.dropi_order_id}</td>
              <td>${o.in_store ? '🏬 #' + esc(String(o.wc_order_id)) : '<span class="badge dropi">solo Dropi</span>'}</td>
              <td>${esc(o.customer || '—')}<br><small>${esc(o.phone || '')}</small></td>
              <td>${esc(o.city || '—')}${o.state ? ', ' + esc(o.state) : ''}</td>
              <td>${o.total != null ? fmtCOP(o.total) : '—'}</td>
              <td>${o.status ? '<span class="badge dropi">' + esc(o.status) + '</span>' : '—'}</td>
              <td>${esc(o.carrier || '—')}</td>
              <td>${o.guide_url ? `<a href="${esc(o.guide_url)}" target="_blank" rel="noopener">guía</a>` : esc(o.guide || '—')}</td>
              <td>${fmtDate(o.created_at)}</td></tr>`
            )
            .join('')}</tbody>
        </table>`;
    } catch (e) {
      if (e.message === 'session') return;
      $('dropi-body').innerHTML = errCard(
        e.message === 'dropi_sync_disabled' ? 'Sync Dropi no configurado (falta DROPI_WC_INTEGRATION_KEY)'
        : e.message === 'dropi_unavailable' ? 'No pudimos consultar Dropi (red o WAF)'
        : 'No pudimos cargar los pedidos de Dropi'
      );
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

  /* ── Vista: Productos (lista) ── */
  async function viewProducts() {
    content().innerHTML = '<div id="prod-body">Cargando…</div>';
    try {
      const data = await apiFetch('/products');
      if (!data.items.length) { $('prod-body').innerHTML = emptyState('Sin productos'); return; }
      $('prod-body').innerHTML = `
        <div class="card"><h2>Productos (${data.items.length})</h2>
        <p><small>Haz clic en un producto para editar fotos y descripción. El interruptor lo muestra u oculta en la tienda al instante.</small></p>
        <table class="keep-cols">
          <thead><tr><th></th><th>Producto</th><th>Precio</th><th>Stock</th><th>Margen</th><th>Visible</th><th></th></tr></thead>
          <tbody>${data.items
            .map(
              (p) => `<tr data-prod="${p.id}">
              <td><img src="${esc(p.image)}" alt="" loading="lazy"></td>
              <td class="prod-name clickable" data-edit="${p.id}">${esc(p.name)}<br><span class="badge ${p.origin}">${p.origin === 'dropi' ? 'Dropi' : 'Propio'}</span></td>
              <td><input class="inline-edit" type="number" min="1" step="100" value="${p.price}" data-field="price" aria-label="Precio de ${esc(p.name)}"></td>
              <td><input class="inline-edit" type="number" min="0" step="1" value="${p.stock ?? ''}" data-field="stock" aria-label="Stock de ${esc(p.name)}"></td>
              <td>${
                p.origin === 'dropi'
                  ? p.margin_alert
                    ? `<span class="badge alert" title="Precio mínimo recomendado: ${p.price_floor != null ? fmtCOP(p.price_floor) : '—'}">⚠️ ${fmtCOP(p.margin)}</span>${p.price_floor != null ? `<br><small>mín ${fmtCOP(p.price_floor)}</small>` : ''}`
                    : `<span class="badge ok">${fmtCOP(p.margin)}</span>`
                  : '—'
              }</td>
              <td><label class="switch"><input type="checkbox" data-visible="${p.id}" ${p.status === 'publish' ? 'checked' : ''} aria-label="Visible en tienda"><span class="slider"></span></label></td>
              <td><button type="button" class="btn-primary" data-save="${p.id}">Guardar</button>
                  <button type="button" class="btn-ghost" data-edit="${p.id}">✏️ Editar</button>
                  <span class="error" data-msg="${p.id}"></span></td>
              </tr>`
            )
            .join('')}</tbody>
        </table>
        <p><small>Margen = precio − costo Dropi − flete estimado. Alerta cuando ≤ 0: Dropi rechaza la orden.</small></p></div>`;

      document.querySelectorAll('[data-edit]').forEach((el) =>
        el.addEventListener('click', () => { location.hash = '#/products/' + el.dataset.edit; })
      );
      document.querySelectorAll('[data-visible]').forEach((chk) =>
        chk.addEventListener('change', async () => {
          chk.disabled = true;
          const msg = document.querySelector(`[data-msg="${chk.dataset.visible}"]`);
          try {
            await apiFetch('/products/' + chk.dataset.visible, { method: 'PUT', body: JSON.stringify({ visible: chk.checked }) });
            msg.textContent = chk.checked ? '✅ Visible' : '🙈 Oculto';
            msg.className = 'scout-add-msg ok';
          } catch (e) {
            chk.checked = !chk.checked;
            msg.textContent = 'No se pudo cambiar';
          } finally { chk.disabled = false; }
        })
      );
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

  /* ── Vista: Editar producto (feature 015) ── */
  let adminConfig = null;

  /* ── Editor de secciones del producto (feature 019, opción A) ──
     Los toggles controlan qué secciones del template real ve el cliente.
     Claves = secciones reales de templates/product.php en la tienda. */
  const PE_SECTIONS = [
    ['benefits', '✅ Beneficios (bullets)'],
    ['boxes', '📦 Incluye / Garantía'],
    ['serve', '🪄 ¿Esto me sirve? (asistente IA)'],
    ['reviews', '⭐ Reseñas verificadas'],
    ['recs', '🔗 Recomendador (relacionados)'],
  ];

  function peDefaults() {
    const sections = {};
    PE_SECTIONS.forEach(([k]) => (sections[k] = true));
    return { sections };
  }

  function peLandingCardHtml() {
    const toggles = PE_SECTIONS.map(
      ([k, label]) => `<label class="switch-inline le-sec"><input type="checkbox" data-sec="${k}"> ${esc(label)}</label>`
    ).join('');
    return `<div class="card" id="pe-landing">
      <h2>🧩 Secciones de la página del producto</h2>
      <p><small>Activa o desactiva qué secciones ve el cliente en la tienda. Lo apagado no se muestra.</small></p>
      <div class="le-toggles">${toggles}</div>
      <hr>
      <p><strong>Contenido de las secciones</strong> <small>· las imágenes se gestionan arriba en "Creativos (fotos)"</small></p>
      <label for="tm-benefits">✅ Beneficios <small>(uno por línea)</small></label>
      <textarea id="tm-benefits" rows="4" placeholder="Recargable USB&#10;Cabe en tu bolso&#10;Tritura hielo"></textarea>
      <div class="le-inline">
        <div style="flex:1"><label for="tm-includes">📦 Incluye</label><input type="text" id="tm-includes" placeholder="1x licuadora, cable USB, vaso"></div>
        <div style="flex:1"><label for="tm-warranty">🛡️ Garantía</label><input type="text" id="tm-warranty" placeholder="30 días de garantía"></div>
      </div>
      <label for="tm-usecase">🪄 ¿Esto me sirve? <small>(caso de uso para el asistente IA)</small></label>
      <input type="text" id="tm-usecase" placeholder="Para batidos en el gym, oficina o viajes">
      <div class="le-inline">
        <div><label for="tm-size">📏 Tamaño</label><input type="text" id="tm-size" placeholder="20 × 8 cm" style="width:160px"></div>
        <div><label for="tm-badge">🏷️ Badge</label><input type="text" id="tm-badge" placeholder="más vendido" style="width:160px"></div>
        <div><label for="tm-rating">⭐ Rating</label><input type="number" id="tm-rating" min="0" max="5" step="0.1" style="width:90px"></div>
        <div><label for="tm-reviews"># Reseñas</label><input type="number" id="tm-reviews" min="0" step="1" style="width:110px"></div>
      </div>
      <div class="le-save-row">
        <button type="button" class="btn-cta" id="pe-landing-save">💾 Guardar secciones y contenido</button>
        <span id="pe-landing-msg" aria-live="polite"></span>
      </div>
    </div>`;
  }

  function peHydrate(L, tm) {
    const sec = (L && L.sections) || {};
    PE_SECTIONS.forEach(([k]) => {
      const t = document.querySelector(`[data-sec="${k}"]`);
      if (t) t.checked = sec[k] !== false;
    });
    tm = tm || {};
    $('tm-benefits').value = (tm.benefits || []).join('\n');
    $('tm-includes').value = tm.includes || '';
    $('tm-warranty').value = tm.warranty || '';
    $('tm-usecase').value = tm.use_case || '';
    $('tm-size').value = tm.size || '';
    $('tm-badge').value = tm.badge || '';
    $('tm-rating').value = tm.rating || '';
    $('tm-reviews').value = tm.reviews || '';
  }

  function peCollectTmMeta() {
    return {
      benefits: $('tm-benefits').value.split('\n').map((s) => s.trim()).filter(Boolean),
      includes: $('tm-includes').value.trim(),
      warranty: $('tm-warranty').value.trim(),
      use_case: $('tm-usecase').value.trim(),
      size: $('tm-size').value.trim(),
      badge: $('tm-badge').value.trim(),
      rating: parseFloat($('tm-rating').value) || 0,
      reviews: parseInt($('tm-reviews').value, 10) || 0,
    };
  }

  function peCollectLanding() {
    const sections = {};
    PE_SECTIONS.forEach(([k]) => {
      const t = document.querySelector(`[data-sec="${k}"]`);
      sections[k] = t ? t.checked : true;
    });
    return { sections };
  }

  function peBindLanding() {} // opción A: solo toggles, sin filas que enlazar

  async function viewProductEdit(id) {
    content().innerHTML = '<div id="pe-body">Cargando…</div>';
    try {
      if (!adminConfig) adminConfig = await apiFetch('/config').catch(() => ({}));
      const p = await apiFetch('/products/' + id);
      const heat = adminConfig && adminConfig.clarity_project_id
        ? `<a class="btn-ghost" href="https://clarity.microsoft.com/projects/view/${esc(adminConfig.clarity_project_id)}/heatmaps" target="_blank" rel="noopener">🗺️ Ver mapa de calor</a>
           <small>En Clarity cambia entre 📱 móvil y 💻 escritorio. Filtra por la URL del producto.</small>`
        : `<small>⚠️ Mapa de calor no configurado — falta el Project ID de Microsoft Clarity.</small>`;

      $('pe-body').innerHTML = `
        <div class="toolbar">
          <button type="button" class="btn-ghost" id="pe-back">← Volver</button>
          ${p.permalink ? `<a class="btn-ghost" href="${esc(p.permalink)}" target="_blank" rel="noopener">🔗 Ver en tienda</a>` : ''}
          <label class="switch-inline"><input type="checkbox" id="pe-visible" ${p.visible ? 'checked' : ''}> Visible en tienda</label>
          <span id="pe-msg" aria-live="polite"></span>
        </div>
        <div class="card">
          <h2>Editar producto</h2>
          <label for="pe-name">Nombre</label>
          <input type="text" id="pe-name" value="${esc(p.name)}" maxlength="300">
          <label for="pe-price">Precio (COP)</label>
          <input type="number" id="pe-price" value="${p.regular_price || p.price}" min="1" step="100">
          <label for="pe-stock">Stock</label>
          <input type="number" id="pe-stock" value="${p.stock ?? ''}" min="0" step="1">
          <label for="pe-short">Descripción corta</label>
          <textarea id="pe-short" rows="2" maxlength="10000">${esc(p.short_description)}</textarea>
          <label for="pe-desc">Descripción</label>
          <textarea id="pe-desc" rows="8" maxlength="50000">${esc(p.description)}</textarea>
          <button type="button" class="btn-cta" id="pe-save">Guardar cambios</button>
        </div>
        <div class="card">
          <h2>Creativos (fotos)</h2>
          <div class="pe-gallery" id="pe-gallery">${
            p.images.length
              ? p.images.map((im) => `<div class="pe-thumb"><img src="${esc(im.src)}" alt="" loading="lazy">${im.id ? `<button type="button" class="pe-del" data-img="${im.id}" title="Quitar">✕</button>` : ''}</div>`).join('')
              : '<span class="empty">Sin fotos aún</span>'
          }</div>
          <label class="btn-primary pe-upload-btn">📤 Subir creativo<input type="file" id="pe-upload" accept="image/*" hidden></label>
          <span id="pe-upload-msg"></span>
          <p><small>JPG/PNG/WebP, máx 8 MB. Al guardar se refleja en la tienda si el producto está visible.</small></p>
        </div>
        ${peLandingCardHtml()}
        <div class="card">
          <h2>🗺️ Mapa de calor</h2>
          ${heat}
        </div>`;

      // landing: hidratar config existente (o defaults) + bind add/quitar
      const L = p.landing && Object.keys(p.landing).length ? { ...peDefaults(), ...p.landing } : peDefaults();
      if (!L.sections) L.sections = peDefaults().sections;
      peHydrate(L, p.tm_meta || {});
      peBindLanding();

      $('pe-back').addEventListener('click', () => { location.hash = '#/products'; });

      $('pe-visible').addEventListener('change', async (e) => {
        try {
          await apiFetch('/products/' + id, { method: 'PUT', body: JSON.stringify({ visible: e.target.checked }) });
          $('pe-msg').textContent = e.target.checked ? '✅ Visible en la tienda' : '🙈 Oculto';
        } catch { e.target.checked = !e.target.checked; $('pe-msg').textContent = 'No se pudo cambiar'; }
      });

      const peSave = async (btn) => {
        const buttons = ['pe-save', 'pe-landing-save'].map((x) => $(x)).filter(Boolean);
        buttons.forEach((b) => (b.disabled = true));
        const msgs = ['pe-msg', 'pe-landing-msg'].map((x) => $(x)).filter(Boolean);
        msgs.forEach((m) => (m.textContent = 'Guardando…'));
        const body = {
          name: $('pe-name').value.trim(),
          price: parseFloat($('pe-price').value) || undefined,
          description: $('pe-desc').value,
          short_description: $('pe-short').value,
          landing: peCollectLanding(),
          tm_meta: peCollectTmMeta(),
        };
        const stockRaw = $('pe-stock').value;
        if (stockRaw !== '') body.stock = parseInt(stockRaw, 10);
        try {
          await apiFetch('/products/' + id, { method: 'PUT', body: JSON.stringify(body) });
          msgs.forEach((m) => (m.textContent = '✅ Guardado — reflejado en la tienda'));
        } catch (err) {
          msgs.forEach((m) => (m.textContent = 'No se pudo guardar: ' + err.message));
        } finally {
          buttons.forEach((b) => (b.disabled = false));
        }
      };
      $('pe-save').addEventListener('click', peSave);
      if ($('pe-landing-save')) $('pe-landing-save').addEventListener('click', peSave);

      $('pe-upload').addEventListener('change', async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        $('pe-upload-msg').textContent = '⏳ Subiendo…';
        const fd = new FormData();
        fd.append('file', f);
        try {
          // apiFetch fuerza JSON; subo con fetch directo conservando el Bearer
          const resp = await fetch(API + '/products/' + id + '/image', {
            method: 'POST', headers: { Authorization: 'Bearer ' + getToken() }, body: fd,
          });
          if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).message || 'error');
          $('pe-upload-msg').textContent = '✅ Foto agregada';
          viewProductEdit(id);
        } catch (err) {
          $('pe-upload-msg').textContent = 'No se pudo subir (¿formato o tamaño?)';
        }
      });

      document.querySelectorAll('[data-img]').forEach((btn) =>
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          try {
            await apiFetch(`/products/${id}/image/${btn.dataset.img}`, { method: 'DELETE' });
            viewProductEdit(id);
          } catch { btn.disabled = false; }
        })
      );
    } catch (e) {
      if (e.message !== 'session') $('pe-body').innerHTML = errCard('No pudimos cargar el producto');
    }
  }

  /* ── Vista: IA ── */
  const fmtUSD = (n) => '$' + Number(n).toFixed(n >= 1 ? 2 : 4) + ' USD';

  async function viewAI() {
    const period = sessionStorage.getItem('tm_admin_ai_period') || '7d';
    content().innerHTML = '<div id="ai-body">Cargando…</div>';
    try {
      const [metrics, convs, usage] = await Promise.all([
        apiFetch('/ai/metrics'),
        apiFetch('/ai/conversations?limit=20'),
        apiFetch(`/ai/usage?period=${period}`),
      ]);
      const intentLabels = { buy: '🛒 Compra', recommend: '✨ Recomendación', track: '📦 Rastreo', chat: '💬 Conversación', other: '❓ Otro' };
      const maxModelCost = Math.max(...usage.by_model.map((m) => m.cost_usd), 0.0001);
      $('ai-body').innerHTML = `
        <div class="page-head">
          <div>
            <h1>🪄 Asistente IA</h1>
            <p class="sub">Consumo, costo e intenciones del asistente</p>
          </div>
          <select id="ai-period-sel" aria-label="Período de consumo">
            <option value="today">Hoy</option>
            <option value="7d">Últimos 7 días</option>
            <option value="30d">Últimos 30 días</option>
          </select>
        </div>
        <div class="metric-grid">
          <div class="metric"><div class="value">${usage.total_tokens.toLocaleString('es-CO')}</div><div class="label">Tokens (${period})</div></div>
          <div class="metric profit"><div class="value">${fmtUSD(usage.cost_usd)}</div><div class="label">Costo estimado</div></div>
          <div class="metric"><div class="value">${fmtUSD(usage.avg_cost_per_conversation)}</div><div class="label">Costo / conversación</div></div>
          <div class="metric"><div class="value">${metrics.conversations}</div><div class="label">Conversaciones</div></div>
          <div class="metric"><div class="value">${metrics.messages}</div><div class="label">Mensajes</div></div>
        </div>
        <div class="card"><h2>🤖 Consumo por modelo</h2>${
          usage.by_model.length
            ? usage.by_model
                .map(
                  (m) => `
            <div class="bar-row">
              <span class="bar-label" title="${esc(m.model)}">${esc(m.model.split('/').pop())}</span>
              <div class="bar-track"><div class="bar-fill cta" style="width:${Math.round((m.cost_usd / maxModelCost) * 100)}%"></div></div>
              <span class="bar-num">${fmtUSD(m.cost_usd)} · ${m.tokens.toLocaleString('es-CO')} tk</span>
            </div>`
                )
                .join('') +
              (usage.unestimated_calls ? `<p><small>⚠️ ${usage.unestimated_calls} llamadas sin precio configurado (no estimadas)</small></p>` : '')
            : emptyState('Sin consumo de IA en el período')
        }</div>
        <div class="chart-grid">
          <div class="card"><h2>🎯 Intenciones</h2>${donut(
            Object.entries(metrics.intents).map(([k, v]) => [intentLabels[k] || k, v]),
            'intenciones'
          )}</div>
          <div class="card"><h2>📡 Consumo por canal</h2>${bars(
            (usage.by_channel || []).map((c) => [
              c.channel === 'whatsapp' ? '💬 WhatsApp' : c.channel === 'web' ? '💻 Chat web' : c.channel,
              c.tokens,
            ]),
            (usage.by_channel || []).reduce((a, c) => a + c.tokens, 0),
            'cta'
          )}</div>
        </div>
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
      $('ai-period-sel').value = period;
      $('ai-period-sel').addEventListener('change', (e) => {
        sessionStorage.setItem('tm_admin_ai_period', e.target.value);
        viewAI();
      });
    } catch (e) {
      if (e.message !== 'session') $('ai-body').innerHTML = errCard('No pudimos cargar las métricas del asistente');
    }
  }

  /* ── Vista: WhatsApp (feature 013) ── */
  let waPollTimer = null;
  let waOpenPhone = null;

  async function viewWhatsApp() {
    clearInterval(waPollTimer);
    content().innerHTML = `
      <div class="wa-layout">
        <div id="wa-list" class="card">Cargando…</div>
        <div id="wa-thread" class="card"><div class="empty">Elige una conversación</div></div>
      </div>`;
    await loadWaList();
    waPollTimer = setInterval(async () => {
      if (!location.hash.includes('whatsapp')) { clearInterval(waPollTimer); return; }
      await loadWaList();
      if (waOpenPhone) await openWaThread(waOpenPhone, true);
    }, 10000);
  }

  async function loadWaList() {
    try {
      const data = await apiFetch('/wa/conversations');
      if (!data.items.length) {
        $('wa-list').innerHTML = emptyState('Aún no hay conversaciones de WhatsApp');
        return;
      }
      $('wa-list').innerHTML = data.items
        .map(
          (c) => `
        <div class="wa-item clickable ${c.phone === waOpenPhone ? 'active' : ''}" data-wa="${esc(c.phone)}" tabindex="0" role="button">
          <div class="wa-item-top">
            <strong>${esc(c.name || c.phone)}</strong>
            <span class="badge ${c.mode === 'human' ? 'alert' : 'ok'}">${c.mode === 'human' ? '🙋 humano' : '🤖 bot'}</span>
          </div>
          <small>${esc(c.last_author === 'customer' ? '' : c.last_author + ': ')}${esc(c.last_message)}</small><br>
          <small class="wa-time">${fmtDate(c.last_activity)}</small>
        </div>`
        )
        .join('');
      document.querySelectorAll('[data-wa]').forEach((el) =>
        el.addEventListener('click', () => openWaThread(el.dataset.wa))
      );
    } catch (e) {
      if (e.message !== 'session') $('wa-list').innerHTML = errCard('No pudimos cargar la bandeja');
    }
  }

  let waLastRender = '';

  async function openWaThread(phone, silent = false) {
    waOpenPhone = phone;
    if (!silent) $('wa-thread').innerHTML = 'Cargando…';
    try {
      const t = await apiFetch('/wa/conversations/' + phone);

      // Poll silencioso: si nada cambió, no re-renderizar (sin parpadeo);
      // si cambió, preservar el borrador del composer antes de redibujar.
      const fingerprint = phone + '|' + t.mode + '|' + t.messages.length + '|' + t.window_open;
      if (silent && fingerprint === waLastRender) return;
      waLastRender = fingerprint;
      const draft = $('wa-text') ? $('wa-text').value : '';

      const authorLabel = { customer: '', bot: '🤖 ', admin: '🙋 ' };
      $('wa-thread').innerHTML = `
        <div class="wa-thread-head">
          <strong>${esc(t.name || t.phone)}</strong> · ${esc(t.phone)}
          <span class="badge ${t.mode === 'human' ? 'alert' : 'ok'}">${t.mode === 'human' ? '🙋 humano' : '🤖 bot'}</span>
          ${t.mode === 'human' ? '<button type="button" class="btn-ghost" id="wa-resume">Reanudar bot</button>' : ''}
        </div>
        <div class="wa-msgs" id="wa-msgs">
          ${t.messages
            .map(
              (m) => `<div class="msg ${m.author === 'customer' ? 'assistant' : 'user'}">
              ${authorLabel[m.author] || ''}${esc(m.content)}${m.delivered === false ? ' ⚠️ no entregado' : ''}
              <br><small>${fmtDate(m.date)}</small></div>`
            )
            .join('')}
        </div>
        ${
          t.window_open
            ? `<form id="wa-compose">
                <textarea id="wa-text" rows="2" placeholder="Escribe tu respuesta…" aria-label="Respuesta"></textarea>
                <button type="submit" class="btn-cta">Enviar</button>
              </form>
              <p id="wa-send-msg" class="error" aria-live="polite"></p>`
            : '<p class="empty">🔒 Ventana de 24h cerrada — no se pueden enviar mensajes libres hasta que el cliente escriba de nuevo.</p>'
        }`;
      const msgs = $('wa-msgs');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
      if (draft && $('wa-text')) $('wa-text').value = draft;

      const resume = $('wa-resume');
      if (resume)
        resume.addEventListener('click', async () => {
          await apiFetch(`/wa/conversations/${phone}/resume-bot`, { method: 'POST' });
          openWaThread(phone);
          loadWaList();
        });

      const form = $('wa-compose');
      if (form)
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const text = $('wa-text').value.trim();
          if (!text) return;
          const btn = form.querySelector('button');
          btn.disabled = true;
          try {
            await apiFetch(`/wa/conversations/${phone}/reply`, {
              method: 'POST',
              body: JSON.stringify({ text }),
            });
            openWaThread(phone);
            loadWaList();
          } catch (err) {
            $('wa-send-msg').textContent =
              err.message === 'window_closed'
                ? 'La ventana de 24h se cerró — no se pudo enviar'
                : 'No se pudo enviar el mensaje, reintenta';
            btn.disabled = false;
          }
        });
    } catch (e) {
      if (e.message !== 'session') $('wa-thread').innerHTML = errCard('No pudimos cargar la conversación');
    }
  }

  /* ── Vista: Scout (feature 014) ── */
  const fmtPct = (n) => (n === null || n === undefined ? '—' : n.toFixed(1) + '%');

  // Estado de la tabla Scout (ordenamiento por columna)
  let scoutCands = [];
  let scoutSort = { key: null, dir: 1 }; // dir: 1 asc, -1 desc

  // valor para ordenar según la columna
  const scoutVal = (c, key) =>
    key === 'name' ? (c.name || '') : key === 'ai_score' ? (c.ai ? c.ai.score : null) : c[key];

  function scoutSorted() {
    if (!scoutSort.key) return scoutCands;
    const { key, dir } = scoutSort;
    return [...scoutCands].sort((a, b) => {
      const va = scoutVal(a, key);
      const vb = scoutVal(b, key);
      if (typeof va === 'string' || typeof vb === 'string') {
        return String(va).localeCompare(String(vb), 'es', { sensitivity: 'base' }) * dir;
      }
      // numérico: nulos siempre al final, sin importar la dirección
      const na = va === null || va === undefined;
      const nb = vb === null || vb === undefined;
      if (na && nb) return 0;
      if (na) return 1;
      if (nb) return -1;
      return (va - vb) * dir;
    });
  }

  function scoutTh(label, key, num) {
    const active = scoutSort.key === key;
    const arrow = active ? (scoutSort.dir === 1 ? ' ▲' : ' ▼') : '';
    return `<th class="sortable${num ? ' num' : ''}${active ? ' sorted' : ''}" data-sort="${key}" role="button" tabindex="0" aria-sort="${active ? (scoutSort.dir === 1 ? 'ascending' : 'descending') : 'none'}">${label}${arrow}</th>`;
  }

  function scoutTableHtml() {
    const rows = scoutSorted()
      .map(
        (c) => `<tr data-pid="${c.dropi_product_id}">
        <td>${esc(c.name)}<br><small>${esc(c.category || '—')} · ${esc(c.supplier || '')}</small>
          ${c.is_novelty ? '<span class="badge ok">🆕 novedad</span>' : ''}
          ${c.is_viable ? '' : '<span class="badge alert">margen ≤ 0</span>'}</td>
        <td class="num">${fmtCOP(c.cost_price)}</td>
        <td class="num">${c.suggested_price ? fmtCOP(c.suggested_price) : '—'}</td>
        <td class="num">${fmtPct(c.margin_pct)}</td>
        <td class="num">${c.stock_total}</td>
        <td class="num">${c.velocity_7d === null ? '—' : c.velocity_7d}</td>
        <td>${
          c.ai
            ? `<strong>${c.ai.score}</strong>/100<br><small class="scout-reason">${esc(c.ai.reason)}</small>`
            : '<span class="badge">sin evaluar</span>'
        }</td>
        <td class="scout-actions">
          <div class="scout-act-row">
            <button type="button" class="btn-add scout-add" data-add="${c.dropi_product_id}" data-name="${esc(c.name)}" title="Agregar a mis productos">➕ Agregar</button>
            <a class="btn-dropi scout-link" href="${esc(c.dropi_url)}" target="_blank" rel="noopener" title="Ver en Dropi">Dropi ↗</a>
          </div>
          <span class="scout-add-msg" data-msg="${c.dropi_product_id}"></span>
        </td>
        </tr>`
      )
      .join('');
    return `<table class="keep-cols scout-table">
      <thead><tr>${scoutTh('Producto', 'name', false)}${scoutTh('Costo', 'cost_price', true)}${scoutTh('Precio sug.', 'suggested_price', true)}${scoutTh('Margen', 'margin_pct', true)}${scoutTh('Stock', 'stock_total', true)}${scoutTh('Vel./día', 'velocity_7d', true)}${scoutTh('IA', 'ai_score', false)}<th>Acciones</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }

  function bindScoutTable() {
    document.querySelectorAll('#scout-table-wrap th.sortable').forEach((th) => {
      const sort = () => {
        const k = th.dataset.sort;
        if (scoutSort.key === k) scoutSort.dir *= -1;
        else scoutSort = { key: k, dir: 1 };
        $('scout-table-wrap').innerHTML = scoutTableHtml();
        bindScoutTable();
      };
      th.addEventListener('click', sort);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
    });
    document.querySelectorAll('#scout-table-wrap [data-add]').forEach((btn) =>
      btn.addEventListener('click', async () => {
        const pid = btn.dataset.add;
        const msg = document.querySelector(`[data-msg="${pid}"]`);
        btn.disabled = true;
        msg.textContent = '⏳ Importando…';
        msg.className = 'scout-add-msg';
        try {
          const r = await apiFetch('/scout/import/' + pid, { method: 'POST' });
          if (r.status === 'exists') {
            msg.textContent = '✓ Ya estaba en la tienda';
            msg.className = 'scout-add-msg ok';
          } else {
            const noImg = r.images_imported === false ? ' (sin fotos — agrégalas en el producto)' : '';
            msg.innerHTML = '✅ Publicado en la tienda' + noImg + (r.permalink ? ` · <a href="${esc(r.permalink)}" target="_blank" rel="noopener">ver</a>` : '');
            msg.className = 'scout-add-msg ok';
          }
          btn.textContent = '✓ Agregado';
        } catch (e) {
          msg.textContent = e.message.startsWith('woocommerce_error') ? 'Error de WooCommerce' : 'No se pudo agregar';
          msg.className = 'scout-add-msg err';
          btn.disabled = false;
        }
      })
    );
  }

  async function viewScout() {
    const period = sessionStorage.getItem('tm_scout_period') || '7d';
    const category = sessionStorage.getItem('tm_scout_cat') || '';
    const search = sessionStorage.getItem('tm_scout_search') || '';
    content().innerHTML = `
      <div class="toolbar">
        <input type="search" id="scout-search" placeholder="Buscar: ej. lampara solar, audifonos…" value="${esc(search)}" aria-label="Buscar productos">
        <select id="scout-cat" aria-label="Categoría"><option value="">Todas las categorías</option></select>
        <select id="scout-period" aria-label="Período de velocidad">
          <option value="today">Hoy</option>
          <option value="7d">Últimos 7 días</option>
          <option value="30d">Últimos 30 días</option>
        </select>
        <button type="button" class="btn-primary" id="scout-ingest">📥 Capturar catálogo</button>
        <button type="button" class="btn-primary" id="scout-score">🤖 Evaluar con IA</button>
        <span id="scout-run-msg" aria-live="polite"></span>
      </div>
      <div id="scout-body">Cargando…</div>
      <div id="scout-demand"></div>`;

    const runSearch = () => { sessionStorage.setItem('tm_scout_search', $('scout-search').value.trim()); viewScout(); };
    $('scout-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(); });
    $('scout-search').addEventListener('search', runSearch); // click en la "x" de limpiar

    const trigger = (btnId, path, runningMsg) => {
      $(btnId).addEventListener('click', async () => {
        $(btnId).disabled = true;
        $('scout-run-msg').textContent = 'Lanzando…';
        try {
          await apiFetch(path, { method: 'POST' });
          $('scout-run-msg').textContent = runningMsg + ' — consulta el estado en "Última ejecución" al recargar';
        } catch (e) {
          $('scout-run-msg').textContent =
            e.message === 'already_running' ? '⏳ Ya hay una ejecución en curso' : 'No se pudo lanzar';
          $(btnId).disabled = false;
        }
      });
    };
    trigger('scout-ingest', '/scout/ingest', '⏳ Captura en curso (varios minutos)');
    trigger('scout-score', '/scout/score', '🤖 Evaluación IA en curso — solo top candidatos, costo acotado');

    try {
      const q = new URLSearchParams({ period });
      if (category) q.set('category', category);
      if (search) q.set('search', search);
      const [data, runsData] = await Promise.all([
        apiFetch('/scout/ranking?' + q),
        apiFetch('/scout/runs?limit=3'),
      ]);

      const catSel = $('scout-cat');
      data.categories.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        catSel.appendChild(opt);
      });
      catSel.value = category;
      catSel.addEventListener('change', (e) => { sessionStorage.setItem('tm_scout_cat', e.target.value); viewScout(); });
      $('scout-period').value = period;
      $('scout-period').addEventListener('change', (e) => { sessionStorage.setItem('tm_scout_period', e.target.value); viewScout(); });

      const lastRun = runsData.runs[0];
      const runLine = lastRun
        ? `<p><small>Última ejecución (${esc(lastRun.kind)}): ${statusBadge(lastRun.status)} · ${lastRun.processed} procesados, ${lastRun.failed} fallidos · ${fmtDate(lastRun.started_at)}</small></p>`
        : '';

      if (!data.candidates.length) {
        $('scout-body').innerHTML =
          runLine +
          emptyState(
            data.computed_at
              ? 'Sin candidatos para este filtro'
              : 'Primera captura del catálogo pendiente — pulsa "Capturar catálogo" para empezar a acumular datos'
          );
        return;
      }

      scoutCands = data.candidates;
      scoutSort = { key: null, dir: 1 }; // orden del servidor (ranking) por defecto
      $('scout-body').innerHTML = `
        ${runLine}
        <div class="card"><h2>Ranking de candidatos (${data.candidates.length})</h2>
        <p><small>Velocidad de venta <strong>estimada</strong> por disminución de stock del proveedor — Dropi no publica ventas. Clic en un título para ordenar.</small></p>
        <div id="scout-table-wrap">${scoutTableHtml()}</div></div>`;
      bindScoutTable();
    } catch (e) {
      if (e.message !== 'session') $('scout-body').innerHTML = errCard('No pudimos cargar el ranking Scout');
    }
    loadScoutDemand();
  }

  async function loadScoutDemand() {
    try {
      const d = await apiFetch('/scout/demand');
      $('scout-demand').innerHTML = `
        <div class="card"><h2>Demanda insatisfecha
          <button type="button" class="btn-ghost" id="scout-demand-refresh">🔄 Analizar conversaciones</button></h2>
        <p><small>Productos que tus clientes pidieron en el chat web o WhatsApp y no están en tu catálogo.</small></p>
        ${
          d.terms.length
            ? `<table class="keep-cols">
                <thead><tr><th>Término</th><th>Menciones</th><th>Canales</th><th>Candidatos en Dropi</th></tr></thead>
                <tbody>${d.terms
                  .map(
                    (t) => `<tr>
                    <td><strong>${esc(t.term)}</strong></td>
                    <td>${t.mention_count}</td>
                    <td>${t.sample_channels.map((c) => (c === 'whatsapp' ? '💬' : '💻')).join(' ')}</td>
                    <td>${
                      t.dropi_candidates.length
                        ? t.dropi_candidates
                            .map(
                              (c) =>
                                `<a href="https://app.dropi.co/dashboard/product-details/${c.dropi_product_id}" target="_blank" rel="noopener">${esc(c.name)}</a>`
                            )
                            .join('<br>')
                        : '—'
                    }</td></tr>`
                  )
                  .join('')}</tbody>
              </table>`
            : emptyState(
                d.analyzed_at
                  ? 'Sin demanda insatisfecha detectada — tus clientes encuentran lo que buscan'
                  : 'Aún sin analizar — pulsa "Analizar conversaciones"'
              )
        }</div>`;
      $('scout-demand-refresh').addEventListener('click', async () => {
        $('scout-demand-refresh').disabled = true;
        try {
          await apiFetch('/scout/demand/refresh', { method: 'POST' });
          $('scout-demand-refresh').textContent = '⏳ Analizando… recarga en unos segundos';
        } catch (e) {
          $('scout-demand-refresh').textContent =
            e.message === 'already_running' ? '⏳ Ya hay un análisis en curso' : 'No se pudo lanzar';
          $('scout-demand-refresh').disabled = false;
        }
      });
    } catch (e) {
      if (e.message !== 'session') $('scout-demand').innerHTML = errCard('No pudimos cargar la demanda insatisfecha');
    }
  }

  /* ── Router ── */
  const routes = {
    dashboard: viewDashboard,
    orders: viewOrders,
    dropi: viewDropiOrders,
    customers: viewCustomers,
    products: viewProducts,
    ai: viewAI,
    whatsapp: viewWhatsApp,
    scout: viewScout,
  };

  function route() {
    if (!getToken()) { showLogin(); return; }
    const path = (location.hash || '#/dashboard').replace('#/', '') || 'dashboard';
    const [name, param] = path.split('/');
    // Ruta anidada: products/{id} → editor del producto
    if (name === 'products' && param) {
      document.querySelectorAll('#sidenav a').forEach((a) =>
        a.classList.toggle('active', a.dataset.nav === 'products')
      );
      viewProductEdit(param);
      return;
    }
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
