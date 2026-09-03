# Tender Prediction Validation

The predictive layer estimates procurement timing from IATI activity evidence. The external procurement layer now provides an independent validation signal.

## Flow

```text
IATI activities
    -> tender_predictions.csv

External official procurement notices
    -> procurement_events.csv
    -> evidence-only IATI matching

Both
    -> tender_prediction_validation.csv
```

## Validation rules

- Only `CONFIRMED` and `POSSIBLE` IATI matches are considered external evidence.
- `CONFIRMED` notices can validate a dated prediction.
- A confirmed notice within 180 days of the predicted tender date is `VALIDATED_ON_TIME`.
- A confirmed notice more than 180 days away is `OBSERVED_OUTSIDE_WINDOW`.
- `POSSIBLE` matches are reported as `POSSIBLE_EXTERNAL_SIGNAL` and never treated as confirmed validation.
- Predictions with no external match remain `NO_EXTERNAL_EVIDENCE`.
- Predictions without a date can still record `VALIDATED_NO_DATED_PREDICTION` when a confirmed external notice exists.

The 180-day tolerance is deliberately broad for the first production validation pass. It should be tightened only after enough observed notices exist to measure empirical prediction error.

## Run

```bash
python -m procurement_intelligence.tender_validation
```

Output:

- `data/tender_prediction_validation.csv`

This is a validation dataset, not a replacement for the existing `tender_predictions.csv` model output.
