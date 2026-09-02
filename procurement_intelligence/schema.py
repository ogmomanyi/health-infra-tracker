from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ProcurementEvent:
    procurement_event_id: str
    source: str
    source_url: str
    tender_reference: str
    title: str
    buyer: str
    country: str
    publication_date: str
    closing_date: str
    equipment_category: str
    product_family: str
    estimated_value: Optional[float] = None
    currency: str = ""
    matched_iati_identifier: str = ""
    match_confidence: float = 0.0
    match_status: str = "UNMATCHED"
    project_reference: str = ""
    procurement_stage: str = ""
    procurement_priority: str = ""

    def to_dict(self):
        return asdict(self)
