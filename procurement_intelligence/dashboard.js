/* External Procurement Intelligence dashboard module. */
(function () {
    "use strict";
    const DATA_PATH = "data/procurement_events.csv";
    let events = [];
    let button = null;
    let panel = null;

    const esc = value => String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");

    function addTab() {
        const tabs = document.querySelector(".tabs");
        if (!tabs || tabs.querySelector("[data-procurement-tab]")) return;
        button = document.createElement("button");
        button.className = "tab-button";
        button.type = "button";
        button.dataset.procurementTab = "true";
        button.textContent = "External Procurement";
        tabs.appendChild(button);
        button.addEventListener("click", show);
    }

    function ensurePanel() {
        if (panel) return panel;
        const tableWrap = document.querySelector(".table-wrap");
        if (!tableWrap) return null;
        panel = document.createElement("section");
        panel.id = "externalProcurementContent";
        panel.className = "hidden";
        panel.innerHTML = '<div id="procurementMetrics"></div><div id="procurementTable"></div>';
        tableWrap.parentElement.insertBefore(panel, tableWrap);
        return panel;
    }

    function show(event) {
        event.preventDefault();
        ensurePanel();
        if (!panel) return;
        document.querySelectorAll(".tab-button").forEach(el => el.classList.remove("active"));
        button.classList.add("active");
        panel.classList.remove("hidden");
        render();
    }

    function hide() {
        if (panel) panel.classList.add("hidden");
        if (button) button.classList.remove("active");
    }

    function render() {
        const matched = events.filter(e => ["POSSIBLE", "CONFIRMED"].includes(e.match_status)).length;
        const confirmed = events.filter(e => e.match_status === "CONFIRMED").length;
        const unmatched = events.filter(e => e.match_status === "UNMATCHED" || !e.match_status).length;
        const closingSoon = events.filter(e => {
            if (!e.closing_date) return false;
            const days = (new Date(e.closing_date) - new Date()) / 86400000;
            return days >= 0 && days <= 7;
        }).length;
        document.getElementById("procurementMetrics").innerHTML = `
            <div class="procurement-metrics">
              <div><b>External tenders</b><strong>${events.length}</strong></div>
              <div><b>IATI matches</b><strong>${matched}</strong></div>
              <div><b>Confirmed</b><strong>${confirmed}</strong></div>
              <div><b>UNMATCHED</b><strong>${unmatched}</strong></div>
              <div><b>Closing ≤7 days</b><strong>${closingSoon}</strong></div>
            </div>`;
        const rows = [...events].sort((a, b) => Number(b.match_confidence || 0) - Number(a.match_confidence || 0));
        document.getElementById("procurementTable").innerHTML = `
          <div class="table-wrap"><table><thead><tr><th>Source</th><th>Tender</th><th>Buyer</th><th>Country</th><th>Stage</th><th>Product</th><th>Closing</th><th>IATI</th><th>Confidence</th><th>Status</th></tr></thead>
          <tbody>${rows.slice(0, 100).map(e => `<tr><td>${esc(e.source)}</td><td>${esc(e.title)}</td><td>${esc(e.buyer)}</td><td>${esc(e.country)}</td><td>${esc(e.procurement_stage || "—")}</td><td>${esc(e.product_family || e.equipment_category)}</td><td>${esc(e.closing_date)}</td><td>${esc(e.matched_iati_identifier || "—")}</td><td>${esc(e.match_confidence)}%</td><td>${esc(e.match_status || "UNMATCHED")}</td></tr>`).join("")}</tbody></table></div>`;
    }

    async function load() {
        try {
            const response = await fetch(DATA_PATH, { cache: "no-store" });
            if (!response.ok) return;
            const text = await response.text();
            Papa.parse(text, { header: true, skipEmptyLines: true, complete: result => { events = result.data || []; if (panel && !panel.classList.contains("hidden")) render(); } });
        } catch (error) {
            console.warn("External procurement data unavailable:", error);
        }
    }

    function boot() {
        addTab();
        ensurePanel();
        document.querySelectorAll(".tab-button").forEach(el => {
            if (el !== button) el.addEventListener("click", hide);
        });
        const style = document.createElement("style");
        style.textContent = ".procurement-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}.procurement-metrics>div{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}.procurement-metrics b{display:block;color:var(--muted);font-size:12px;text-transform:uppercase}.procurement-metrics strong{display:block;font-size:26px;margin-top:10px}@media(max-width:900px){.procurement-metrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.procurement-metrics{grid-template-columns:repeat(2,1fr)}}";
        document.head.appendChild(style);
        load();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
