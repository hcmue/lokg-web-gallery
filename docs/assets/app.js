'use strict';
/* Public GitHub Pages frontend: no password, token or database connection string. */
(function () {
  const $ = (id) => document.getElementById(id);
  const conf = window.LOKG_CONFIG || {};
  const LIMIT = Math.max(1, Math.min(30, Number(conf.RESULT_LIMIT) || 12));
  const base = String(conf.API_BASE_URL || '').trim().replace(/\/+$/, '');
  const configured = (/^https:\/\/[^/]+$/i.test(base) || (location.hostname.match(/^(localhost|127\.0\.0\.1)$/) && /^http:\/\/(localhost|127\.0\.0\.1):[0-9]+$/.test(base))) && !/REPLACE|YOUR-RENDER/i.test(base);
  const NAMES = {ecommerce: 'Thương mại điện tử', education: 'Giáo dục', business: 'Doanh nghiệp', news: 'Tin tức & Blog', landing: 'Landing page', dashboard: 'Dashboard', other: 'Mẫu giao diện'};
  let busy = false;
  let offset = 0;
  let total = 0;
  let fallback = [];
  let offline = !configured;
  let requestId = 0;
  const fmt = new Intl.NumberFormat('vi-VN');
  const modeSelect = $('mode');

  function safeURL(href) {
    try {
      const url = new URL(String(href || ''));
      if (url.protocol !== 'https:' || url.hostname !== 'hcmue.github.io') return null;
      return url.href;
    } catch { return null; }
  }
  function element(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  function status(text, type='') {
    const el = $('notice');
    $('noticeText').textContent = text;
    el.className = type ? 'notice ' + type : 'notice';
    el.hidden = !text;
    $('retryApi').hidden = !text || !configured;
  }
  function connection(online, message) {
    $('apiDot').className = 'service-dot ' + (online ? 'online' : 'offline');
    $('connectionStatus').textContent = online ? 'API Render đang kết nối' : 'Chế độ thư viện tĩnh';
    $('connectionDetail').textContent = message;
  }
  function normalize(text) {
    return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase();
  }
  function previewFrom(item) {
    if (item.local_preview) return item.local_preview;
    const u = safeURL(item.page_url);
    if (!u) return null;
    try {
      const p = new URL(u);
      if (!p.pathname.includes('/pages/') || !p.pathname.endsWith('.html')) return null;
      p.pathname = p.pathname.replace('/pages/', '/previews/').replace(/\.html$/, '.webp');
      p.search = ''; p.hash = '';
      return p.href;
    } catch { return null; }
  }
  function visitorToken() {
    try {
      let id = localStorage.getItem('lokg_anonymous_browser_id');
      if (/^[a-f0-9]{32}$/.test(id || '')) return id;
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      id = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
      localStorage.setItem('lokg_anonymous_browser_id', id);
      return id;
    } catch {
      return null; // Disabled storage => no attempt to identify a browser.
    }
  }
  async function api(path, options={}, timeoutMs=75000) {
    if (!configured) throw new Error('Chưa cấu hình URL dịch vụ Render trong docs/config.js.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(base + path, {
        mode:'cors', credentials:'omit', cache:'no-store',
        ...options, signal: controller.signal,
      });
      let data;
      try { data = await res.json(); } catch { data = {}; }
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'API trả HTTP ' + res.status);
      return data;
    } catch(e) {
      if(e.name === 'AbortError') throw new Error('Máy chủ Render phản hồi chậm hoặc chưa hoạt động.');
      throw e;
    } finally { clearTimeout(timer); }
  }
  function category(item) { return NAMES[item.category] || NAMES.other; }
  function card(item, isFallback) {
    const outer = element('article', 'result-card');
    const thumb = element('div', 'result-preview');
    const image = previewFrom(item);
    if (image) {
      const img = element('img');
      img.src = image; img.loading = 'lazy'; img.alt = 'Xem trước giao diện: ' + String(item.title || item.id);
      img.onerror = () => { img.remove(); thumb.prepend(element('div', 'fallback-preview', 'WEB UI')); };
      thumb.append(img);
    } else thumb.append(element('div', 'fallback-preview', 'WEB UI'));
    thumb.append(element('span','label-badge',category(item)));
    if (!isFallback && item.engine && item.engine !== 'browse') {
      thumb.append(element('span', 'score-badge', 'Điểm ' + Number(item.score || 0).toFixed(3)));
    }
    outer.append(thumb);
    const body = element('div', 'result-body');
    body.append(element('div','result-title',item.title || item.id || 'Giao diện Web'));
    const descr = String(item.description || 'Mẫu giao diện được tuyển chọn phục vụ học phần Thiết kế Web.');
    body.append(element('p','result-desc',descr.length > 100 ? descr.slice(0,98) + '…' : descr));
    const tags = element('div','tags');
    (item.tags || []).slice(0,4).forEach(t => tags.append(element('span','tag',t)));
    body.append(tags);
    const link = element('a','result-link');
    link.textContent = 'Xem giao diện';
    link.append(element('span','', '↗'));
    const safe = safeURL(item.page_url);
    if (safe) {
      link.href = safe; link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.addEventListener('click', () => {
        if (isFallback || !item.id || !configured) return;
        api('/api/analytics/click', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({item_id: String(item.id)}), keepalive:true,
        }, 12000).catch(() => {});
      });
    } else {
      link.href = '#thu-vien';
      link.setAttribute('aria-disabled','true');
      link.textContent = 'Đường dẫn không hợp lệ';
    }
    body.append(link);outer.append(body);return outer;
  }
  function appendResults(rows, isFallback) {
    const region = $('results');
    rows.forEach(r => region.append(card(r, isFallback)));
    $('emptyState').hidden = region.childElementCount > 0;
  }
  async function fetchOfflineCatalog() {
    if (fallback.length) return fallback;
    const res = await fetch('gallery-fallback.json', {cache:'force-cache'});
    if (!res.ok) throw new Error('Không tải được danh mục giao diện tĩnh.');
    fallback = await res.json();
    return fallback;
  }
  function offlineFilter(items,q) {
    const tokens = normalize(q).split(/\s+/).filter(w=>w.length>1);
    if (!tokens.length) return items;
    return items.map(item => {
      const hay = normalize([item.title,item.description,item.category,...(item.tags||[])].join(' '));
      const score = tokens.reduce((n,token) => n + (hay.includes(token) ? 1 : 0),0);
      return {item, score};
    }).filter(x => x.score > 0).sort((a,b) => b.score - a.score).map(x => x.item);
  }
  async function showOffline(reason) {
    offline = true;
    connection(false, 'Duyệt 72 giao diện không cần backend');
    status(reason || 'Đang hiển thị mẫu HTML tĩnh. Kết quả lọc ở đây KHÔNG phải truy hồi LOKG-IR.', '');
    await fetchOfflineCatalog();
    offset = 0;
    $('results').replaceChildren();
    const rows = offlineFilter(fallback, $('query').value.trim());
    total = rows.length;
    appendResults(rows.slice(0,LIMIT), true);
    offset = Math.min(LIMIT, total);
    $('resultsStatus').textContent = `${fmt.format(total)} mẫu · Danh mục tĩnh`;
    $('loadMore').hidden = offset >= total;
    $('resourcesCount').textContent = fmt.format(fallback.length);
  }
  async function performSearch(reset=true) {
    if (busy) return;
    const serial = ++requestId;
    busy = true;
    $('searchForm').querySelector('button[type=submit]').disabled = true;
    if (reset) { offset = 0; $('results').replaceChildren(); }
    $('resultsStatus').textContent = 'Đang tra cứu...';
    $('loadMore').hidden = true;
    const q = $('query').value.trim();
    try {
      if (offline) {
        await fetchOfflineCatalog();
        const rows = offlineFilter(fallback, q);
        total = rows.length;
        appendResults(rows.slice(offset, offset+LIMIT), true);
        offset = Math.min(total, offset + LIMIT);
        $('resultsStatus').textContent = `${fmt.format(total)} mẫu · Lọc từ khóa cục bộ`;
      } else {
        const params = new URLSearchParams({query:q,mode:modeSelect.value,limit:LIMIT,offset});
        const rows = await api('/api/search?' + params, {}, 75000);
        if (serial !== requestId) return;
        total = Number(rows.total) || 0;
        appendResults(rows.results || [], false);
        offset += (rows.results || []).length;
        $('resultsStatus').textContent = `${fmt.format(total)} kết quả · ${rows.mode.toUpperCase()} · ${rows.latency_ms} ms`;
        connection(true,'Truy hồi bằng metadata và đồ thị tri thức');
        status('');
        if (q && reset) refreshStats();
      }
      $('loadMore').hidden = offset >= total;
      $('resultsHeading').textContent = q ? 'Kết quả phù hợp' : 'Khám phá các mẫu Web';
      if(reset && q) history.replaceState({}, '', '?q=' + encodeURIComponent(q) + '#thu-vien');
      else if(reset && !q) history.replaceState({}, '', location.pathname + '#thu-vien');
    } catch(e) {
      // Render could be sleeping/offline. Keep the gallery functional.
      if (!offline) {
        try { await showOffline('Không kết nối được API: ' + e.message + '. Đang xem thư viện tĩnh; kết quả không dùng LOKG-IR.'); }
        catch { status('Không kết nối được API và danh mục tĩnh: ' + e.message, 'error'); $('resultsStatus').textContent='Không có dữ liệu'; }
      } else { status('Lỗi tải danh mục: ' + e.message, 'error'); $('resultsStatus').textContent='Không có dữ liệu'; }
    } finally {
      busy = false;
      $('searchForm').querySelector('button[type=submit]').disabled = false;
    }
  }
  async function loadMore() {
    if (busy) return;
    if (!offline) return performSearch(false);
    busy = true;
    try {
      const rows = offlineFilter(await fetchOfflineCatalog(), $('query').value.trim());
      appendResults(rows.slice(offset, offset+LIMIT), true);
      offset = Math.min(rows.length, offset+LIMIT);
      $('loadMore').hidden = offset >= rows.length;
    } finally { busy = false; }
  }
  async function refreshStats() {
    if(!configured) return;
    try {
      const data = await api('/api/stats/public', {}, 20000);
      if (data.enabled) {
        $('visitsCount').textContent=fmt.format(data.visits || 0);
        $('searchCount').textContent=fmt.format(data.searches || 0);
      }
    } catch { /* Not essential to search. */ }
  }
  async function trackVisit() {
    if(!configured) return;
    try {
      const visitorId = visitorToken();
      await api('/api/analytics/visit',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({visitor_id:visitorId}),
      }, 75000);
      refreshStats();
    } catch { /* Analytics must not prevent using the gallery. */ }
  }
  function configureLinks() {
    const admin = $('adminLink'); const docs = $('apiDocsLink');
    if(configured) {
      admin.href = base + '/admin'; docs.href = base + '/api/docs';
    } else {
      admin.hidden = true; docs.hidden = true;
    }
  }
  async function init() {
    configureLinks();
    const params = new URLSearchParams(location.search);
    const incoming = params.get('q');
    if (incoming) $('query').value = incoming.slice(0,300);
    $('searchForm').addEventListener('submit',event => { event.preventDefault(); performSearch(true); });
    modeSelect.addEventListener('change',() => performSearch(true));
    $('loadMore').addEventListener('click',loadMore);
    $('retryApi').addEventListener('click', () => { offline=false;status('');performSearch(true).then(refreshStats); });
    document.querySelectorAll('[data-query]').forEach(btn => btn.addEventListener('click',() => {
      $('query').value = btn.dataset.query;performSearch(true);
      document.getElementById('thu-vien').scrollIntoView({behavior:'smooth'});
    }));
    if (!configured) {
      try { await showOffline('Chưa cấu hình địa chỉ Render trong docs/config.js. Trang vẫn cho phép xem các giao diện tĩnh; tính năng LOKG-IR sẽ hoạt động sau khi kết nối API.'); }
      catch (e) { status('Không đọc được danh mục mẫu: ' + e.message, 'error'); }
      return;
    }
    connection(false,'Đang kết nối Render; lần khởi động đầu có thể chậm');
    // Search and visit can run in parallel; Render Free may need to wake up.
    trackVisit();
    try {
      await performSearch(true);
      if(!offline){
        const meta=await api('/api/meta',{},12000);
        $('resourcesCount').textContent=fmt.format(meta.total || 0);
        refreshStats();
        if((meta.total || 0) === 0) status('API đã kết nối nhưng chưa có học liệu. Hãy chạy scripts/seed_catalog.py và push data/catalog.yaml, sau đó nhấn /admin → Tải lại dữ liệu.');
      }
    } catch { /* Error handled by performSearch. */ }
  }
  init();
})();
