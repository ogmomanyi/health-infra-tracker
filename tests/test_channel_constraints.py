from pathlib import Path

from procurement_intelligence import channel_constraints


def test_match_requires_same_manufacturer_and_country(tmp_path: Path):
    path = tmp_path / "constraints.csv"
    path.write_text(
        "constraint_id,manufacturer_name,country,channel_status,channel_holder,product_scope,evidence_source,evidence_reference,evidence_date,confidence,recommended_action,notes\n"
        "CC-001,DiaSys,Kenya,APPOINTED_DISTRIBUTOR_IDENTIFIED,Keton Consulting Limited,DiaSys products,OUTLOOK,email,2026-09-04,HIGH,DO_NOT_POSITION_AS_DIRECT_DISTRIBUTOR,note\n",
        encoding="utf-8",
    )
    rows = channel_constraints.load(path)
    matched = channel_constraints.match(
        {"country": "KE"},
        [{"manufacturer_name": "DiaSys", "technical_status": "PASS"}],
        rows,
    )
    assert len(matched) == 1
    assert matched[0]["constraint_id"] == "CC-001"


def test_match_does_not_cross_manufacturer_or_country():
    rows = [{
        "constraint_id": "CC-001",
        "manufacturer_name": "DiaSys",
        "country": "Kenya",
        "channel_holder": "Keton Consulting Limited",
    }]
    assert channel_constraints.match(
        {"country": "Uganda"},
        [{"manufacturer_name": "DiaSys"}],
        rows,
    ) == []
    assert channel_constraints.match(
        {"country": "Kenya"},
        [{"manufacturer_name": "Molecular Devices"}],
        rows,
    ) == []
