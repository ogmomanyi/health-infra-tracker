PYTHON ?= python3
DATA_DIR ?= data
DATABASE ?= data/iati_intelligence.db
PORT ?= 8765

.PHONY: intelligence test serve mock clean-pyc

intelligence:
	$(PYTHON) run_intelligence_pipeline.py

test:
	$(PYTHON) -m pytest -q

serve:
	$(PYTHON) -m http.server $(PORT)

mock:
	$(PYTHON) iati_tracker.py --mock --output-dir /tmp/iati_tracker_mock --database /tmp/iati_tracker_mock.db --state-file /tmp/iati_tracker_mock_state.json --snapshot-dir /tmp/iati_tracker_mock_history
	$(PYTHON) run_intelligence_pipeline.py --data-dir /tmp/iati_tracker_mock --database /tmp/iati_tracker_mock.db

clean-pyc:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
