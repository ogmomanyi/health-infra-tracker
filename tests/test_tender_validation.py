import unittest

from procurement_intelligence.tender_validation import validate_predictions


class TenderValidationTests(unittest.TestCase):
    def prediction(self, **overrides):
        row = {
            "iati_identifier": "IATI-1",
            "project_title": "Kenya laboratory strengthening",
            "country_codes": "KE",
            "tender_window": "2026-10-01",
            "tender_probability": "85",
            "tender_stage": "Likely procurement",
        }
        row.update(overrides)
        return row

    def event(self, **overrides):
        row = {
            "matched_iati_identifier": "IATI-1",
            "match_status": "CONFIRMED",
            "publication_date": "2026-09-15",
            "closing_date": "2026-10-15",
        }
        row.update(overrides)
        return row

    def test_confirmed_notice_inside_180_days_validates_prediction(self):
        rows = validate_predictions([self.prediction()], [self.event()])
        self.assertEqual(rows[0]["validation_status"], "VALIDATED_ON_TIME")
        self.assertEqual(rows[0]["nearest_observed_notice_date"], "2026-09-15")
        self.assertEqual(rows[0]["window_error_days"], 16)

    def test_confirmed_notice_far_from_prediction_is_not_validated(self):
        rows = validate_predictions(
            [self.prediction()],
            [self.event(publication_date="2025-01-01", closing_date="2025-02-01")],
        )
        self.assertEqual(rows[0]["validation_status"], "OBSERVED_OUTSIDE_WINDOW")

    def test_possible_match_is_signal_not_validation(self):
        rows = validate_predictions(
            [self.prediction()],
            [self.event(match_status="POSSIBLE")],
        )
        self.assertEqual(rows[0]["validation_status"], "POSSIBLE_EXTERNAL_SIGNAL")
        self.assertEqual(rows[0]["confirmed_notice_count"], 0)

    def test_unmatched_notice_does_not_validate(self):
        rows = validate_predictions(
            [self.prediction()],
            [self.event(match_status="UNMATCHED")],
        )
        self.assertEqual(rows[0]["validation_status"], "NO_EXTERNAL_EVIDENCE")
        self.assertEqual(rows[0]["external_notice_count"], 0)

    def test_missing_prediction_date_can_still_use_confirmed_notice(self):
        rows = validate_predictions(
            [self.prediction(tender_window="nan")],
            [self.event()],
        )
        self.assertEqual(rows[0]["validation_status"], "VALIDATED_NO_DATED_PREDICTION")


if __name__ == "__main__":
    unittest.main()
