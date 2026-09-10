(() => {
  const params = new URLSearchParams(location.search);
  const opportunityId = params.get('id');
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const statusClass = status => ({PASS:'green', REVIEW:'pri', FAIL:'act', UNKNOWN:'neutral'}[status] || 'neutral');
  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(0) : '0';
  const render = fit => {
    const anchor = document.querySelector('#procurement');
    if (!anchor || document.querySelector('#technicalFitPanel')) return;
    const panel = document.createElement('section');
    panel.id = 'technicalFitPanel';
    panel.className = 'panel';
    const rows = fit.map(row => {
      const status = row.technical_status || 'UNKNOWN';
      const score = fmt(row.technical_score);
      const passed = Number(row.technical_passed || 0);
      const unknown = Number(row.technical_unknown || 0);
      const failed = Number(row.technical_failed || 0);
      const total = passed + unknown + failed;
      return `<tr><td><strong>${esc(row.product_name || row.faram_product_id || 'Faram candidate')}</strong><div class="mini">${esc(row.manufacturer_name || '')}</div></td><td><span class="tag ${statusClass(status)}">${esc(status)}</span></td><td>${esc(row.match_confidence || '—')}%</td><td>${score}%</td><td>${passed}/${total}</td><td>${esc(row.territory_fit || '—')}</td><td>${esc(row.technical_action || '')}</td></tr>`;
    }).join('');
    panel.innerHTML = `<div class="panel-head"><h2>Faram Product Fit</h2><span class="sub">Verified technical evidence; separate from commercial priority</span></div><div class="body">${rows ? `<div style="overflow:auto"><table class="data-table"><thead><tr><th>Product</th><th>Technical fit</th><th>Catalogue confidence</th><th>Technical score</th><th>Specs met</th><th>Territory</th><th>Recommended action</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="empty">No verified tender/product specification evidence is available for this opportunity yet. Do not infer compliance.</div>`}</div>`;
    anchor.closest('.panel')?.after(panel);
  };
  const load = async () => {
    if (!opportunityId) return;
    try {
      const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/technical-fit`);
      if (!response.ok) return;
      const payload = await response.json();
      render(Array.isArray(payload.technical_fit) ? payload.technical_fit : []);
    } catch (_) {
      // The core Opportunity Workspace remains functional if technical-fit data is unavailable.
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();
