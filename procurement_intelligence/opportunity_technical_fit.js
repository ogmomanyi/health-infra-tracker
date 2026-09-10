(() => {
  const params = new URLSearchParams(location.search);
  const opportunityId = params.get('id');
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const statusClass = status => ({PASS:'green', REVIEW:'pri', FAIL:'act', UNKNOWN:'neutral'}[status] || 'neutral');
  const postureClass = posture => ({PROCEED_TO_BID_REVIEW:'green', DO_NOT_BID:'act', TECHNICAL_REVIEW:'pri', REVIEW_ALTERNATIVE:'pri', HOLD:'neutral'}[posture] || 'neutral');
  const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(0) : '0';
  const days = value => { const n = Number(value); return Number.isFinite(n) ? n : null; };
  const guidance = (opportunity, fit) => {
    const statuses = fit.map(row => String(row.technical_status || 'UNKNOWN').toUpperCase());
    const reasons = [];
    if (fit.length && statuses.every(status => status === 'FAIL')) return {posture:'DO_NOT_BID', reasons:['TECHNICAL_FAILURE'], summary:'Technical failure identified; do not bid without an approved alternative.'};
    if (statuses.includes('FAIL')) reasons.push('TECHNICAL_FAILURE_ON_CANDIDATE');
    if (statuses.includes('REVIEW')) reasons.push('TECHNICAL_REVIEW_REQUIRED');
    if (statuses.includes('UNKNOWN') || !fit.length) reasons.push('TECHNICAL_EVIDENCE_GAP');
    const territory = fit.map(row => String(row.territory_fit || '').toUpperCase());
    if (territory.length && !territory.some(value => ['YES','TRUE','Y'].includes(value))) reasons.push('NO_CONFIRMED_TERRITORY_FIT');
    const closing = days(opportunity.days_to_closing);
    if (closing !== null && closing < 0) reasons.push('CLOSING_DATE_PASSED');
    else if (closing !== null && closing <= 7) reasons.push('CLOSING_WITHIN_7_DAYS');
    if (reasons.includes('CLOSING_DATE_PASSED')) return {posture:'HOLD', reasons, summary:'Closing date has passed; confirm procurement status before proceeding.'};
    if (reasons.some(code => ['TECHNICAL_REVIEW_REQUIRED','TECHNICAL_EVIDENCE_GAP','NO_CONFIRMED_TERRITORY_FIT'].includes(code))) return {posture:'TECHNICAL_REVIEW', reasons, summary:'Technical/compliance evidence requires review before a bid decision.'};
    if (reasons.includes('TECHNICAL_FAILURE_ON_CANDIDATE')) return {posture:'REVIEW_ALTERNATIVE', reasons, summary:'A candidate has a technical failure; assess an approved alternative before deciding.'};
    return {posture:'PROCEED_TO_BID_REVIEW', reasons, summary:'Available signals support proceeding to human bid/no-bid review.'};
  };
  const render = (opportunity, fit) => {
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
    const decision = guidance(opportunity, fit);
    const reasons = decision.reasons.length ? `<div class="mini" style="margin-top:8px">Signals: ${decision.reasons.map(esc).join(' · ')}</div>` : '';
    panel.innerHTML = `<div class="panel-head"><h2>Faram Product Fit</h2><span class="sub">Verified technical evidence; separate from commercial priority</span></div><div class="body"><div class="action"><strong>Decision posture: <span class="tag ${postureClass(decision.posture)}">${esc(decision.posture.replaceAll('_',' '))}</span></strong><div style="margin-top:6px">${esc(decision.summary)}</div>${reasons}<div class="mini" style="margin-top:8px">This is guidance only. The CRM bid/no-bid decision remains a human action.</div></div>${rows ? `<div style="overflow:auto;margin-top:14px"><table class="data-table"><thead><tr><th>Product</th><th>Technical fit</th><th>Catalogue confidence</th><th>Technical score</th><th>Specs met</th><th>Territory</th><th>Recommended action</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="empty">No verified tender/product specification evidence is available for this opportunity yet. Do not infer compliance.</div>`}</div>`;
    anchor.closest('.panel')?.after(panel);
  };
  const load = async () => {
    if (!opportunityId) return;
    try {
      const [fitResponse, opportunityResponse] = await Promise.all([
        fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/technical-fit`),
        fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}`)
      ]);
      if (!fitResponse.ok || !opportunityResponse.ok) return;
      const fitPayload = await fitResponse.json();
      const opportunity = await opportunityResponse.json();
      render(opportunity || {}, Array.isArray(fitPayload.technical_fit) ? fitPayload.technical_fit : []);
    } catch (_) {
      // The core Opportunity Workspace remains functional if technical-fit data is unavailable.
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();
