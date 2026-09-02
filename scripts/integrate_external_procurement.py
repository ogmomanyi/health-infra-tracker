from pathlib import Path

INDEX = Path("index.html")
TAB_MARKER = 'data-tab="external-procurement"'
HANDLER_MARKER = 'window.location.href = "procurement_intelligence/dashboard.html"'

TAB_HTML = '''                        <button class="tab-button" data-tab="external-procurement" type="button">
                            <i data-lucide="radio-tower"></i>
                            External Procurement
                        </button>
'''

HANDLER = '''                    if (state.activeTab === "external-procurement") {
                        window.location.href = "procurement_intelligence/dashboard.html";
                        return;
                    }
'''


def main():
    text = INDEX.read_text(encoding="utf-8")
    changed = False

    if TAB_MARKER not in text:
        anchor = '                        <button class="tab-button" data-tab="tenders" type="button">'
        if anchor not in text:
            raise SystemExit("Could not find Tenders tab anchor")
        text = text.replace(anchor, TAB_HTML + anchor, 1)
        changed = True

    if HANDLER_MARKER not in text:
        anchor = '''            document.querySelectorAll(".tab-button").forEach(button => {
                button.addEventListener("click", () => {
                    state.activeTab = button.dataset.tab;
'''
        replacement = anchor + HANDLER
        if anchor not in text:
            raise SystemExit("Could not find tab click handler anchor")
        text = text.replace(anchor, replacement, 1)
        changed = True

    INDEX.write_text(text, encoding="utf-8")
    print("dashboard integration migration completed" if changed else "dashboard already integrated")


if __name__ == "__main__":
    main()
