/* External Procurement Intelligence dashboard module.
 * Loaded independently so the existing commercial tabs remain untouched.
 */
(function () {
    "use strict";

    const DATA_PATH = "data/procurement_events.csv";
    const TAB_ID = "procurement";
    let events = [];

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function numberValue(value) {
        const n = Number.parseFloat(value);
        return Number.isFinite(n) ? n : 0;
    }

    function daysToClosing(date) {
        if (!date) return null;
        const closing = new Date(date + "T23:59:59Z");
        if (Number.isNaN(closing.getTime())) return null;
        return Math.ceil((closing - new Date()) / 86400000);
    }

    function createPanel() {
        const existing = document.getElementById("externalProcurementPanel");
        if (existing) return existing;

        const tablePanel = document.querySelector(".table-wrap")?.parentElement;
        if (!tablePanel) return null;

        const panel = document.createElement("section");
        panel.id = "externalProcurementPanel";
        panel.className = "panel";
        panel.style.marginTop = "16px";
        panel.innerHTML = `
            <div class="panel-header">
                <div>
                    <h2 class="panel-title">External Procurement Intelligence</h2>
                    <span class="panel-meta" id="procurementMeta">No external procurement events loaded</span>
                </div>
                <button class="icon-button" id="procurementRefresh" type="button" title="Refresh procurement events" aria-label="Refresh procurement events">↻</button>
            </div>
            <div id="procurementMetrics" class="metric-grid" style="margin:0 0 14px;"></div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Tender</th>
                            <th>Buyer</th>
                            <th>Country</th>
                            <th>Equipment</th>
                            <th>Closing</th>
                            <th>IATI Match</th>
                            <th>Confidence</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="procurementBody"></tbody>
                </table>
            </div>
        `;

        tablePanel.parentElement.insertBefore(panel, tablePanel.nextSibling);
        document.getElementById("procurementRefresh").addEventListener("click", load);
        return panel;
    }

    function render() {
        const panel = createPanel();
        if (!panel) return;

        const matched = events.filter(e => ["POSSIBLE", "CONFIRMED"].includes(e.match_status)).length;
        const confirmed = events.filter(e => e.match_status === "CONFIRMED").length;
        const closingSoon = events.filter(e => {
            const days = daysToClosing(e.closing_date);
            return days !== null && days >= 0 && days <= 7;
        }).length;

        document.getElementById("procurementMeta").textContent = `${events.length} events · ${matched} matched · ${confirmed} confirmed`;
        document.getElementById("procurementMetrics").innerHTML = [
            ["External Tenders", events.length],
            ["Matched to IATI", matched],
            ["Confirmed Matches", confirmed],
            ["Closing ≤ 7 Days", closingSoon]
        ].map(([label, value]) => `
            <article class="metric" style="min-height:88px;box-shadow:none;">
                <div class="metric-label">${escapeHtml(label)}</div>
                <div class="metric-value">${value}</div>
            </article>
        `).join("");

        const tbody = document.getElementById("procurementBody");
        if (!events.length) {
            tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state">No external procurement events are available yet. The tab will populate when the procurement ingestion pipeline produces data.</div></td></tr>`;
            return;
        }

        const rows = [...events].sort((a, b) => {
            const confidence = numberValue(b.match_confidence) - numberValue(a.match_confidence);
            if (confidence !== 0) return confidence;
            return (daysToClosing(a.closing_date) ?? 9999) - (daysToClosing(b.closing_date) ?? 9999);
        });

        tbody.innerHTML = rows.slice(0, 100).map(event => `
            <tr>
                <td>
                    <div class="primary">${escapeHtml(event.title || "Untitled tender")}</div>
                    <div class="secondary">${escapeHtml(event.tender_reference || event.procurement_event_id || "")}</div>
                </td>
                <td>${escapeHtml(event.buyer || "Unknown buyer")}</td>
                <td>${escapeHtml(event.country || "")}</td>
                <td>${escapeHtml(event.product_family || event.equipment_category || "Unspecified")}</td>
                <td>${escapeHtml(event.closing_date || "")}</td>
                <td>${escapeHtml(event.matched_iati_identifier || "No match")}</td>
                <td>${numberValue(event.match_confidence).toFixed(1)}%</td>
                <td>${escapeHtml(event.match_status || "UNMATCHED")}</td>
            </tr>
        `).join("");
    }

    async function load() {
        try {
            const response = await fetch(DATA_PATH, { cache: "no-store" });
            if (!response.ok) {
                if (response.status === 404) {
                    events = [];
                    render();
                    return;
                }
                throw new Error(`Procurement dataset returned ${response.status}`);
            }

            const text = await response.text();
            events = await new Promise((resolve, reject) => {
                if (!window.Papa) return reject(new Error("PapaParse is not available"));
                window.Papa.parse(text, {
                    header: true,
                    skipEmptyLines: true,
                    complete: result => resolve(result.data || []),
                    error: reject
                });
            });
            render();
        } catch (error) {
            console.warn("External procurement dashboard module:", error);
            events = [];
            render();
        }
    }

    function boot() {
        createPanel();
        load();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
