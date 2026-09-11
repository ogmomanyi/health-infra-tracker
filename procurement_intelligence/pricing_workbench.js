(() => {
  const params = new URLSearchParams(location.search);
  const opportunityId = params.get('id');
  if (!opportunityId) return;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const val = id => document.getElementById(id)?.value.trim() ?? '';
  const checked = id => !!document.getElementById(id)?.checked;

  async function api(path, options={}) {
    const response = await fetch(path, {
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})}
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  function money(value, currency) {
    return value == null ? '—' : `${Number(value).toLocaleString(undefined,{maximumFractionDigits:2})} ${esc(currency || '')}`;
  }

  function statusClass(status) {
    if (status === 'READY_FOR_COMMERCIAL_APPROVAL') return 'green';
    if (status === 'NEGATIVE_GROSS_PROFIT') return 'act';
    if (status === 'HOLD_NO_BID') return 'act';
    return 'pri';
  }

  function panel() {
    if (document.getElementById('pricingWorkbench')) return;
    const anchor = document.getElementById('executionSummary')?.closest('.panel')
      || document.getElementById('bidDecisionGuidance')
      || document.querySelector('.panel');
    if (!anchor) return;

    const section = document.createElement('section');
    section.id = 'pricingWorkbench';
    section.className = 'panel';
    section.innerHTML = `
      <div class="panel-head"><h2>Commercial Pricing Workbench</h2><span class="tag neutral">Explicit inputs only</span></div>
      <div class="body">
        <div class="mini" style="margin-bottom:12px">Create named pricing cases from current supplier and cost inputs. Historical evidence is never used as current price, and canonical commercial priority is not recalculated.</div>
        <div id="pricingCases" class="empty">Loading pricing cases…</div>
        <div style="margin-top:18px"><strong>New pricing case</strong></div>
        <div class="form-grid" style="margin-top:10px">
          <label>Case name<input id="pcName" value="Base case"></label>
          <label>Supplier reference<input id="pcReference" placeholder="Supplier quote / RFQ reference"></label>
          <label>Supplier currency<input id="pcSupplierCurrency" value="USD"></label>
          <label>Supplier cost<input id="pcSupplierCost" type="number" step="any"></label>
          <label>Pricing currency<input id="pcPricingCurrency" value="KES"></label>
          <label>FX rate to pricing currency<input id="pcFx" type="number" step="any" placeholder="e.g. 130"></label>
          <label>Freight cost<input id="pcFreight" type="number" step="any" value="0"></label>
          <label>Clearing & tax cost<input id="pcClearing" type="number" step="any" value="0"></label>
          <label>Financing cost<input id="pcFinancing" type="number" step="any" value="0"></label>
          <label>Other costs<input id="pcOther" type="number" step="any" value="0"></label>
          <label>Selling price<input id="pcSellingPrice" type="number" step="any"></label>
          <label>Quote valid until<input id="pcValidUntil" type="date"></label>
          <label style="grid-column:1/-1">Payment terms<input id="pcPaymentTerms" placeholder="e.g. 50% advance / 50% on delivery"></label>
          <label style="grid-column:1/-1">Notes<textarea id="pcNotes"></textarea></label>
          <label style="grid-column:1/-1"><input id="pcComplete" type="checkbox"> Cost basis complete — freight, clearing/tax, financing and other costs have been explicitly confirmed (enter 0 where none applies)</label>
        </div>
        <div class="button-row"><button class="btn primary" id="savePricingCase">Save & evaluate pricing case</button></div>
        <div id="pricingStatus" class="status"></div>
      </div>`;
    anchor.after(section);
    document.getElementById('savePricingCase').addEventListener('click', save);
    load();
  }

  function renderCase(row) {
    const metrics = row.total_cost == null ? '' : `
      <div class="mini">Total cost: <b>${money(row.total_cost,row.pricing_currency)}</b> · Gross profit: <b>${money(row.gross_profit,row.pricing_currency)}</b> · Margin: <b>${row.margin_pct == null ? '—' : esc(row.margin_pct)+'%'}</b> · Markup: <b>${row.markup_pct == null ? '—' : esc(row.markup_pct)+'%'}</b></div>`;
    return `
      <div class="activity">
        <div><b>${esc(row.case_name || 'Pricing case')}</b> <span class="tag ${statusClass(row.pricing_status)}">${esc(row.pricing_status)}</span></div>
        <div class="mini">Supplier cost: ${money(row.supplier_cost,row.supplier_currency)} · Selling price: ${money(row.selling_price,row.pricing_currency)}${row.fx_rate_to_pricing_currency ? ` · FX: ${esc(row.fx_rate_to_pricing_currency)}` : ''}</div>
        ${metrics}
        <div class="mini" style="margin-top:5px">${esc(row.reason || '')}</div>
      </div>`;
  }

  async function load() {
    const box = document.getElementById('pricingCases');
    try {
      const data = await api(`/api/opportunities/${encodeURIComponent(opportunityId)}/pricing`);
      const rows = data.pricing_cases || [];
      box.className = '';
      box.innerHTML = rows.length ? rows.map(renderCase).join('') : '<div class="empty">No pricing cases recorded yet.</div>';
    } catch (error) {
      box.className = 'empty';
      box.textContent = `Unable to load pricing cases: ${error.message}`;
    }
  }

  function numeric(id) {
    const value = val(id);
    return value === '' ? null : Number(value);
  }

  async function save() {
    const status = document.getElementById('pricingStatus');
    try {
      status.textContent = 'Saving…';
      const result = await api(`/api/opportunities/${encodeURIComponent(opportunityId)}/pricing`, {
        method:'POST',
        body:JSON.stringify({
          case_name: val('pcName'),
          supplier_reference: val('pcReference'),
          supplier_currency: val('pcSupplierCurrency'),
          supplier_cost: numeric('pcSupplierCost'),
          pricing_currency: val('pcPricingCurrency'),
          fx_rate_to_pricing_currency: numeric('pcFx'),
          freight_cost: numeric('pcFreight'),
          clearing_and_tax_cost: numeric('pcClearing'),
          financing_cost: numeric('pcFinancing'),
          other_costs: numeric('pcOther'),
          selling_price: numeric('pcSellingPrice'),
          cost_basis_complete: checked('pcComplete'),
          payment_terms: val('pcPaymentTerms'),
          quote_valid_until: val('pcValidUntil'),
          notes: val('pcNotes'),
          created_by: 'opportunity-workspace'
        })
      });
      status.textContent = `${result.pricing_status}: ${result.reason}`;
      await load();
    } catch (error) {
      status.textContent = `Save failed: ${error.message}`;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel); else panel();
})();
