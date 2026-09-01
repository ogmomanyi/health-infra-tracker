/* External Procurement Intelligence dashboard module. */
(function () {
    "use strict";

    const DATA_PATH = "data/procurement_events.csv";
    let events = [];
    let procurementPanel = null;
    let tableWrap = null;
    let procurementButton = null;

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

        procurementButton.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            showProcurementTab();
        });
    }

    function createPanel() {
        if (procurementPanel) return procurementPanel;

        tableWrap = document.querySelector(".table-wrap");
        if (!tableWrap) return null;

        procurementPanel = document.createElement("div");
        procurementPanel.id = "externalProcurementPanel";
        procurementPanel.className = "external-procurement-panel";
        procurementPanel.innerHTML = `
            <div class="panel-header">
                <div>
                    <h2 class="panel-title">External Procurement Intelligence</h2>
                    <span class="panel-meta" id="procurementMeta">
                        No external procurement events loaded
                    </span>
                </div>
                <button
                    class="icon-button"
                    id="procurementRefresh"
                    type="button"
                    title="Refresh procurement events"
                    aria-label="Refresh procurement events"
                >↻</button>
            </div>
            <div id="procurementMetrics" class="metric-grid procurement-metrics"></div>
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

        tableWrap.parentElement.insertBefore(procurementPanel, tableWrap);
        document
            .getElementById("procurementRefresh")
            .addEventListener("click", load);

        return procurementPanel;
    }

    function addStyles() {
        if (document.getElementById("external-procurement-styles")) return;

        const style = document.createElement("style");
        style.id = "external-procurement-styles";
        style.textContent = `
            .external-procurement-panel {
                padding: 0 0 18px;
            }
            .external-procurement-panel .panel-header {
                padding: 16px 18px;
                border-bottom: 1px solid var(--line);
            }
            .procurement-metrics {
                grid-template-columns: repeat(4, minmax(0, 1fr));
                margin: 16px;
            }
            .procurement-metrics .metric {
                min-height: 96px;
                box-shadow: none;
            }
            .external-procurement-panel .table-wrap {
                margin-top: 0;
            }
            @media (max-width: 900px) {
                .procurement-metrics {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (max-width: 560px) {
                .procurement-metrics {
                    grid-template-columns: 1fr;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function setActive(active) {
        document.querySelectorAll(".tab-button").forEach(button => {
            button.classList.remove("active");
        });

        if (!active) {
            return;
        }

        procurementButton?.classList.add("active");
    }

    function showProcurementTab() {
        createPanel();
        if (!procurementPanel || !tableWrap) return;

        tableWrap.classList.add("hidden");
        procurementPanel.classList.remove("hidden");
        setActive(true);
        render();
    }

    function showStandardTable() {
        if (!procurementPanel || !tableWrap) return;

        procurementPanel.classList.add("hidden");
        tableWrap.classList.remove("hidden");
        if (procurementButton) {
            procurementButton.classList.remove("active");
        }
    }

    function render() {
        const panel = createPanel();
        if (!panel) return;

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

        document.getElementById("procurementMeta").textContent =
            `${events.length} events · ${matched} matched · ${confirmed} confirmed`;

        document.getElementById("procurementMetrics").innerHTML = [
            ["External Tenders", events.length],
            ["Matched to IATI", matched],
            ["Confirmed Matches", confirmed],
            ["Closing ≤ 7 Days", closingSoon]
        ].map(([label, value]) => `
            <article class="metric">
                <div class="metric-label">${escapeHtml(label)}</div>
                <div class="metric-value">${value}</div>
            </article>
        `).join("");

        const tbody = document.getElementById("procurementBody");

        if (!events.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8">
                        <div class="empty-state">
                            No external procurement events are available yet.
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const rows = [...events].sort((a, b) => {
            const confidence =
                numberValue(b.match_confidence) -
                numberValue(a.match_confidence);

            if (confidence !== 0) return confidence;

            return (
                (daysToClosing(a.closing_date) ?? 9999) -
                (daysToClosing(b.closing_date) ?? 9999)
            );
        });

        tbody.innerHTML = rows.slice(0, 100).map(event => `
            <tr>
                <td>
                    <div class="primary">
                        ${escapeHtml(event.title || "Untitled tender")}
                    </div>
                    <div class="secondary">
                        ${escapeHtml(
                            event.tender_reference ||
                            event.procurement_event_id ||
                            ""
                        )}
                    </div>
                </td>
                <td>${escapeHtml(event.buyer || "Unknown buyer")}</td>
                <td>${escapeHtml(event.country || "")}</td>
                <td>
                    ${escapeHtml(
                        event.product_family ||
                        event.equipment_category ||
                        "Unspecified"
                    )}
                </td>
                <td>${escapeHtml(event.closing_date || "")}</td>
                <td>
                    ${escapeHtml(
                        event.matched_iati_identifier || "No match"
                    )}
                </td>
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
                throw new Error(
                    `Procurement dataset returned ${response.status}`
                );
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

            render();
        } catch (error) {
            console.warn(
                "External procurement dashboard module:",
                error
            );
            events = [];
            render();
        }
    }

    function watchStandardTabs() {
        document.querySelectorAll(".tab-button").forEach(button => {
            if (button === procurementButton) return;
            button.addEventListener("click", showStandardTable);
        });
    }

    function boot() {
        addStyles();
        addTab();
        createPanel();
        if (procurementPanel) {
            procurementPanel.classList.add("hidden");
        }
        watchStandardTabs();
        load();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
