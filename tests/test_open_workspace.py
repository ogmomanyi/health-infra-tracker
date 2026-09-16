from __future__ import annotations

from unittest.mock import patch

from scripts import open_workspace


def test_select_port_reuses_healthy_tracker():
    with patch.object(open_workspace, "tracker_health", return_value=True):
        assert open_workspace.select_port("127.0.0.1", 8765) == (8765, False)


def test_select_port_skips_unrelated_service():
    with (
        patch.object(open_workspace, "tracker_health", return_value=False),
        patch.object(open_workspace, "port_available", side_effect=[False, True]),
    ):
        assert open_workspace.select_port("127.0.0.1", 8765) == (8766, True)
