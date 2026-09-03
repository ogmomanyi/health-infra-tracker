from pathlib import Path

from procurement_intelligence.commercial_memory import build_summary, normalize_evidence


def test_normalize_evidence_derives_supplier_signal_and_outcome():
    rows = [
        {
            "evidence_id": "HQE-023",
            "product_name": "Thermo Fisher scientific equipment and consumables",
            "manufacturer_name": "Thermo Fisher Scientific",
            "product_family": "Life Science / Laboratory Equipment",
            "model": "",
            "category": "Laboratory Equipment",
            "evidence_type": "order_and_business_review",
            "supplier_email": "orders.em@thermofisher.com",
            "source_email_id": "email-1",
            "notes": "Historical PO/order correspondence plus business review evidence",
        }
    ]

    result = normalize_evidence(rows)

    assert len(result) == 1
    assert result[0]["supplier_company"] == "Thermo Fisher Scientific"
    assert result[0]["outcome"] == "ORDERED"
    assert result[0]["evidence_strength"] == "HIGH"
    assert result[0]["representation_signal"] == "TRANSACTIONAL"


def test_external_and_competitive_evidence_do_not_enter_summary():
    rows = normalize_evidence([
        {
            "evidence_id": "HQE-005",
            "product_name": "Centrifuge main PCB",
            "manufacturer_name": "Unknown",
            "product_family": "Centrifuge",
            "model": "20150350",
            "evidence_type": "procurement_request",
            "supplier_email": "KiharaRM@state.gov",
            "notes": "External procurement request; not evidence of current Faram representation",
        },
        {
            "evidence_id": "HQE-019",
            "product_name": "Cytation multimode reader",
            "manufacturer_name": "Agilent / BioTek",
            "product_family": "Cytation Multimode Reader",
            "model": "Cytation",
            "evidence_type": "tender_reference_only",
            "supplier_email": "viktoria.rumjantseva@moldev.com",
            "notes": "Competitive/reference evidence, not Faram representation",
        },
    ])

    summary = build_summary(rows)

    assert summary == []


def test_summary_joins_current_catalogue_status():
    memory = normalize_evidence([
        {
            "evidence_id": "HQE-016",
            "product_name": "SpectraMax i3x",
            "manufacturer_name": "Molecular Devices",
            "product_family": "Multimode Microplate Reader",
            "model": "i3x",
            "evidence_type": "tender_fit_and_pricing",
            "supplier_email": "viktoria.rumjantseva@moldev.com",
            "notes": "Explicit tender comparison",
        }
    ])
    catalogue = [{
        "manufacturer_name": "Molecular Devices",
        "product_family": "Multimode Microplate Reader",
        "principal_status": "active",
    }]

    summary = build_summary(memory, catalogue)

    assert len(summary) == 1
    assert summary[0]["current_catalogue_status"] == "CATALOGUE_MATCH"
    assert summary[0]["commercial_familiarity_score"] == "3"
