(() => {
  const params = new URLSearchParams(location.search);
  const opportunityId = params.get('id');
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const tone = guidance => ({PROCEED_TO_BID_REVIEW:'green',HOLD_FOR_TECHNICAL_REVIEW:'pri',DO_NOT_BID_TECHNICAL_FAILURE:'act',HOLD_FOR_TERRITORY_REVIEW:'pri',HOLD_FOR_CATALOGUE_REVIEW:'pri'}[guidance] || 'neutral');
  const render = data => {
    if (document.querySelector('#bidDecisionGuidance')) return;
    const anchor = document.querySelector('#technicalFitPanel') || document.querySelector('#procurement')?.closest('.panel');
    if (!anchor) return;
    const panel = document.createElement('section'); panel.id = 'bidDecisionGuidance'; panel.className = 'panel';
    const technical = data.bid_decision?.technical || {};
    const commercial = data.commercial_preparation || {};
    const reasons = (data.bid_decision?.reasons || []).map(reason => `<li>${esc(reason)}</li>`).join('');
    const actions = (commercial.preparation_actions || []).map(action => `<li>${esc(action)}</li>`).join('');
    panel.innerHTML = `<div class="panel-head"><h2>Bid / No-Bid Intelligence</h2><span class="tag ${tone(data.bid_decision?.guidance)}">${esc(data.bid_decision?.guidance_label || 'REVIEW REQUIRED')}</span></div><div class="body"><div class="grid"><div><strong>Commercial priority</strong><div class="mini">${esc(data.bid_decision?.commercial_account_priority_tier || '—')} · ${esc(data.bid_decision?.commercial_account_priority_score ?? '—')}</div></div><div><strong>Technical fit</strong><div class="mini">${esc(technical.status || 'UNKNOWN')} · ${esc(technical.pass || 0)} pass · ${esc(technical.review || 0)} review · ${esc(technical.fail || 0)} fail · ${esc(technical.unknown || 0)} unknown</div></div><div><strong>Territory</strong><div class="mini">${esc(data.bid_decision?.territory_fit || 'UNKNOWN')}</div></div><div><strong>Human decision</strong><div class="mini">${esc(data.bid_decision?.human_bid_decision || 'PENDING')} — guidance does not set this</div></div></div>${reasons ? `<div style="margin-top:14px"><strong>Decision signals</strong><ul>${reasons}</ul></div>` : ''}${actions ? `<div style="margin-top:14px"><strong>Commercial preparation</strong><ul>${actions}</ul></div>` : ''}<div class="mini" style="margin-top:12px"><strong>Pricing posture:</strong> ${esc(commercial.pricing_guidance || 'Obtain current supplier pricing; historical evidence is context, not current price.')}</div><div class="mini" style="margin-top:8px">This is decision support only. The bid/no-bid decision remains a human CRM action, and canonical commercial priority is unchanged.</div></div>`;
    anchor.after(panel);
  };
  const load = async () => {
    if (!opportunityId) return;
    try { const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/decision-guidance`); if (!response.ok) return; render(await response.json()); } catch (_) {}
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();
