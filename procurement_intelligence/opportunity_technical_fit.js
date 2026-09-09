(() => {
  const fit = Array.isArray(window.__OPPORTUNITY_TECHNICAL_FIT__) ? window.__OPPORTUNITY_TECHNICAL_FIT__ : [];
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const statusClass = status => ({PASS:'green', REVIEW:'pri', FAIL:'act', UNKNOWN:'neutral'}[status] || 'neutral');
  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(0) : '0';
  const render = () => {
    const anchor = document.querySelector('#procurement');
    if (!anchor || document.querySelector('#technicalFitPanel')) return;
    const panel = document.createElement('section');
    panel.id = 'technicalFitPanel';
    panel.className = 'panel';
    const rows = fit.map(row => {
      const status = row.technical_status || 'UNKNOWN';
      const score = fmt(row.technical_score);
      const passed = row.technical_passed || '0';
      const unknown = row.technical_unknown || '0';
      const failed = row.technical_failed || '0';
      return `<tr><td><strong>${esc(row.product_name || row.faram_product_id || 'Faram candidate')}</strong><div class="mini">${esc(row.manufacturer_name || '')}</div></td><td><span class="tag ${statusClass(status)}">${esc(status)}</span></td><td>${esc(row.match_confidence || '—')}%</td><td>${score}%</td><td>${esc(passed)}/${esc(Number(passed)+Number(unknown)+Number(failed))}</td><td>${esc(row.territory_fit || '—')}</td><td>${esc(row.technical_action || '')}</td></tr>`;
    }).join('');
    panel.innerHTML = `<div class="panel-head"><h2>Faram Product Fit</h2><span class="sub">Verified technical evidence; separate from commercial priority</span></div><div class="body">${rows ? `<div style="overflow:auto"><table class="data-table"><thead><tr><th>Product</th><th>Technical fit</th><th>Catalogue confidence</th><th>Technical score</th><th>Specs met</th><th>Territory</th><th>Recommended action</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="empty">No verified tender/product specification evidence is available for this opportunity yet. Do not infer compliance.</div>`}</div>`;
    anchor.closest('.panel')?.after(panel);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render); else render();
})();
