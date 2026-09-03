# Tender Prediction Validation

The predictive layer estimates procurement timing from IATI activity evidence. The external procurement layer provides an independent validation signal.

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

## Metrics to calculate once observations accumulate

1. **External-evidence coverage** — share of predictions with any matched notice.
2. **Confirmation rate** — share of predictions with a confirmed notice.
3. **On-time validation rate** — share of confirmed, dated predictions validated within the tolerance.
4. **Median timing error** — median absolute difference between predicted and observed dates.
5. **Probability-band performance** — compare outcomes across prediction bands such as 50–69, 70–84 and 85–100.
6. **Category/country performance** — identify equipment categories and countries where the model is systematically early, late or over-confident.

Do not recalibrate tender probabilities until these measures expose a repeatable error pattern. The validation layer is intended to turn the current deterministic heuristic into an empirically calibratable model over time.
