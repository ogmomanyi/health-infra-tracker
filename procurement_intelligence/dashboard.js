/* External Procurement Intelligence dashboard module. */
(function () {
    "use strict";

    const DATA_PATH = "data/procurement_events.csv";
    let events = [];
    let procurementButton = null;
    let procurementContent = null;
    let procurementActive = false;

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

    function addTab() {
        const tabs = document.querySelector(".tabs");
        if (!tabs || tabs.querySelector('[data-procurement-tab="true"]')) return;

        procurementButton = document.createElement("button");
        procurementButton.className = "tab-button";
        procurementButton.type = "button";
        procurementButton.setAttribute("data-procurement-tab", "true");
        procurementButton.textContent = "External Procurement";
        tabs.appendChild(procurementButton);
        procurementButton.addEventListener("click", showProcurementTab);
    }

    function createContent() {
        if (procurementContent) return procurementContent;

        const tableWrap = document.querySelector(".table-wrap");
        if (!tableWrap) return null;

        procurementContent = document.createElement("div");
        procurementContent.id = "externalProcurementContent";
        procurementContent.className = "hidden";
        procurementContent.innerHTML = `
            <div class="procurement-metrics" id="procurementMetrics"></div>
        `;

        tableWrap.parentElement.insertBefore(procurementContent, tableWrap);
        addStyles();
        return procurementContent;
    }

    function addStyles() {
        if (document.getElementById("external-procurement-styles")) return;

        const style = document.createElement("style");
        style.id = "external-procurement-styles";
        style.textContent = `
            .procurement-metrics {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                padding: 16px;
            }
            .procurement-metric {
                min-height: 92px;
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 8px;
                padding: 14px;
            }
            .procurement-metric .metric-label {
                color: var(--muted);
                font-size: 12px;
                text-transform: uppercase;
                font-weight: 700;
            }
            .procurement-metric .metric-value {
                margin-top: 14px;
                font-size: 26px;
                line-height: 1;
                font-weight: 800;
            }
            .procurement-status-confirmed { font-weight: 700; color: var(--green); }
            .procurement-status-possible { font-weight: 700; color: var(--blue); }
            .procurement-status-unmatched { color: var(--muted); }
            @media (max-width: 900px) {
                .procurement-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            @media (max-width: 560px) {
                .procurement-metrics { grid-template-columns: 1fr; }
            }
        `;
        document.head.appendChild(style);
    }

    function showProcurementTab(event) {
        event?.preventDefault();
        event?.stopPropagation();

        createContent();
        if (!procurementContent) return;

        procurementActive = true;
        procurementContent.classList.remove("hidden");
        procurementButton?.classList.add("active");

        document.querySelectorAll(".tab-button").forEach(button => {
            if (button !== procurementButton) {
                button.classList.remove("active");
            }
        });

        const tableWrap = document.querySelector(".table-wrap");
        tableWrap?.classList.remove("hidden");
        renderProcurementTable();
    }

    function showStandardTab() {
        if (!procurementContent || !procurementActive) return;

        procurementActive = false;
        procurementContent.classList.add("hidden");
        procurementButton?.classList.remove("active");
    }

    function renderMetrics() {
        const matched = events.filter(event =>
            ["POSSIBLE", "CONFIRMED"].includes(event.match_status)
        ).length;
        const confirmed = events.filter(
            event => event.match_status === "CONFIRMED"
        ).length;
        const closingSoon = events.filter(event => {
            const days = daysToClosing(event.closing_date);
            return days !== null && days >= 0 && days <= 7;
        }).length;

        document.getElementById("procurementMetrics").innerHTML = [
            ["External Tenders", events.length],
            ["Matched to IATI", matched],
            ["Confirmed Matches", confirmed],
            ["Closing ≤ 7 Days", closingSoon]
        ].map(([label, value]) => `
            <article class="procurement-metric">
                <div class="metric-label">${escapeHtml(label)}</div>
                <div class="metric-value">${value}</div>
            </article>
        `).join("");
    }

    function renderProcurementTable() {
        if (!procurementActive) return;

        createContent();
        renderMetrics();

        const tableHead = document.getElementById("tableHead");
        const tableBody = document.getElementById("tableBody");
        const tableMeta = document.getElementById("tableMeta");

        if (!tableHead || !tableBody) return;

        tableMeta.textContent = `${events.length} external procurement events`;
        tableHead.innerHTML = `
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
        `;

        if (!events.length) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="8">
                        <div class="empty-state">No external procurement events are available yet.</div>
                    </td>
                </tr>
            `;
            return;
        }

        const rows = [...events].sort((a, b) => {
            const confidence = numberValue(b.match_confidence) - numberValue(a.match_confidence);
            if (confidence !== 0) return confidence;
            return (daysToClosing(a.closing_date) ?? 9999) - (daysToClosing(b.closing_date) ?? 9999);
        });

        tableBody.innerHTML = rows.slice(0, 100).map(event => {
            const statusClass = event.match_status === "CONFIRMED"
                ? "procurement-status-confirmed"
                : event.match_status === "POSSIBLE"
                    ? "procurement-status-possible"
                    : "procurement-status-unmatched";

            return `
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
                    <td class="${statusClass}">${escapeHtml(event.match_status || "UNMATCHED")}</td>
                </tr>
            `;
        }).join("");
    }

    async function load() {
        try {
            const response = await fetch(DATA_PATH, { cache: "no-store" });
            if (!response.ok) {
                if (response.status === 404) {
                    events = [];
                    if (procurementActive) renderProcurementTable();
                    return;
                }
                throw new Error(`Procurement dataset returned ${response.status}`);
            }

            const text = await response.text();
            events = await new Promise((resolve, reject) => {
                if (!window.Papa) {
                    reject(new Error("PapaParse is not available"));
                    return;
                }
                window.Papa.parse(text, {
                    header: true,
                    skipEmptyLines: true,
                    complete: result => resolve(result.data || []),
                    error: reject
                });
            });

            if (procurementActive) renderProcurementTable();
        } catch (error) {
            console.warn("External procurement dashboard module:", error);
            events = [];
            if (procurementActive) renderProcurementTable();
        }
    }

    function boot() {
        addTab();
        createContent();

        /* Only hide procurement-specific content when returning to a standard tab.
           The existing dashboard controller remains responsible for the table. */
        document.querySelectorAll(".tab-button").forEach(button => {
            if (button === procurementButton) return;
            button.addEventListener("click", showStandardTab);
        });

        load();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
