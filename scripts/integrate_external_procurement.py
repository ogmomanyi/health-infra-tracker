from pathlib import Path

INDEX = Path("index.html")
MARKER = 'data-tab="external-procurement"'

TAB_HTML = '''                        <button class="tab-button" data-tab="external-procurement" type="button">
                            <i data-lucide="radio-tower"></i>
                            External Procurement
                        </button>
'''

STATE_ADD = '            externalProcurement: [],\n'
PATH_ADD = '            externalProcurement: "data/procurement_events.csv",\n'
LOAD_ADD = '                    fetchCsv(datasetPaths.externalProcurement)\n'


def main():
    text = INDEX.read_text(encoding="utf-8")
    changed = False

    if MARKER not in text:
        anchor = '                        <button class="tab-button" data-tab="tenders" type="button">'
        if anchor not in text:
            raise SystemExit("Could not find Tenders tab anchor")
        text = text.replace(anchor, TAB_HTML + anchor, 1)
        changed = True

    if 'externalProcurement: [],' not in text:
        anchor = '            tenders: [],\n'
        if anchor not in text:
            raise SystemExit("Could not find state tenders anchor")
        text = text.replace(anchor, anchor + STATE_ADD, 1)
        changed = True

    if 'externalProcurement: "data/procurement_events.csv"' not in text:
        anchor = '            tenders: "data/tender_predictions.csv",\n'
        if anchor not in text:
            raise SystemExit("Could not find dataset tenders anchor")
        text = text.replace(anchor, anchor + PATH_ADD, 1)
        changed = True

    if 'fetchCsv(datasetPaths.externalProcurement)' not in text:
        anchor = '                    fetchCsv(datasetPaths.tenders)\n'
        if anchor not in text:
            raise SystemExit("Could not find tenders load anchor")
        text = text.replace(anchor, anchor + ',' + LOAD_ADD.strip() + '\n', 1)
        changed = True

    if 'state.externalProcurement = sortByDate' not in text:
        anchor = '                state.tenders = sortByNumber(tenders, "tender_probability");\n'
        if anchor not in text:
            raise SystemExit("Could not find tenders state assignment")
        text = text.replace(anchor, anchor + '                state.externalProcurement = externalProcurement;\n', 1)
        changed = True

    INDEX.write_text(text, encoding="utf-8")
    print("dashboard integration migration completed" if changed else "dashboard already integrated")


if __name__ == "__main__":
    main()
