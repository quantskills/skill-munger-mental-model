"""
Tests for analyze.py orchestration layer with cross-validation logic.

Covers cross_validate, build_record, analyze_symbol, and main CLI.
"""

from __future__ import annotations

import pytest

import config


# Helper functions from plan Step 1
def _dim(
    score: float = 50.0,
    passed: bool | None = True,
    veto: bool = False,
    flags: list[str] | None = None,
    sub_scores: dict | None = None,
) -> dict:
    """Build a dimension result dict for testing."""
    return {
        "score": score,
        "passed": passed,
        "veto": veto,
        "flags": flags or [],
        "sub_scores": sub_scores or {},
    }


def _dims(
    fin: dict | None = None,
    comp: dict | None = None,
    incentive: dict | None = None,
    psych: dict | None = None,
    neg: dict | None = None,
) -> dict:
    """Build a dims dict (mapping DIM_KEYS to dimension results)."""
    return {
        "fin": fin or _dim(),
        "comp": comp or _dim(),
        "incentive": incentive or _dim(),
        "psych": psych or _dim(),
        "neg": neg or _dim(),
    }


class TestCrossValidate:
    """Tests for cross_validate function."""

    def test_all_pass_high_confidence(self):
        """All five dims passed=True → verdict=pass, high_confidence=True."""
        from analyze import cross_validate

        dims = _dims(
            fin=_dim(passed=True),
            comp=_dim(passed=True),
            incentive=_dim(passed=True),
            psych=_dim(passed=True),
            neg=_dim(passed=True),
        )
        result = cross_validate(dims)
        assert result["verdict"] == "pass"
        assert result["high_confidence"] is True
        assert result["radar_scores"] == [50.0, 50.0, 50.0, 50.0, 50.0]

    def test_veto_overrides_everything(self):
        """neg.veto=True → verdict=veto, high_confidence=False."""
        from analyze import cross_validate

        dims = _dims(
            fin=_dim(passed=True),
            comp=_dim(passed=True),
            incentive=_dim(passed=True),
            psych=_dim(passed=True),
            neg=_dim(passed=True, veto=True),
        )
        result = cross_validate(dims)
        assert result["verdict"] == "veto"
        assert result["high_confidence"] is False

    def test_one_dim_fail_not_high_confidence(self):
        """One dim failed (passed=False) → verdict=fail, high_confidence=False."""
        from analyze import cross_validate

        dims = _dims(
            fin=_dim(passed=True),
            comp=_dim(passed=False),
            incentive=_dim(passed=True),
            psych=_dim(passed=True),
            neg=_dim(passed=True),
        )
        result = cross_validate(dims)
        assert result["verdict"] == "fail"
        assert result["high_confidence"] is False

    def test_insufficient_data(self):
        """One dim with passed=None → verdict=insufficient_data, high_confidence=False."""
        from analyze import cross_validate

        dims = _dims(
            fin=_dim(passed=None),
            comp=_dim(passed=True),
            incentive=_dim(passed=True),
            psych=_dim(passed=True),
            neg=_dim(passed=True),
        )
        result = cross_validate(dims)
        assert result["verdict"] == "insufficient_data"
        assert result["high_confidence"] is False


class TestBuildRecord:
    """Tests for build_record function."""

    def test_build_record_fields(self):
        """build_record assembles all required fields per spec §6."""
        from analyze import build_record

        dims = _dims(
            fin=_dim(score=75.0, passed=True, flags=["flag1"], sub_scores={"sub1": 0.8}),
            comp=_dim(score=65.0, passed=True, flags=[], sub_scores={}),
            incentive=_dim(score=70.0, passed=True, flags=["flag2"], sub_scores={}),
            psych=_dim(score=55.0, passed=False, flags=[], sub_scores={}),
            neg=_dim(score=100.0, passed=True, veto=False, flags=[], sub_scores={}),
        )

        record = build_record(
            symbol="000001.SZ",
            trade_date="2026-06-30",
            dims=dims,
            update_time="2026-07-10 12:00:00",
        )

        # Check required spec §6 fields
        assert record["symbol"] == "000001.SZ"
        assert record["trade_date"] == "2026-06-30"
        assert isinstance(record["dim_scores"], dict)
        assert isinstance(record["dim_passed"], dict)
        assert isinstance(record["sub_scores"], dict)
        assert isinstance(record["veto_flags"], list)
        assert isinstance(record["data_flags"], list)
        assert isinstance(record["radar_scores"], list)
        assert record["high_confidence"] is False
        assert record["verdict"] == "fail"
        assert record["data_version"] == "real-v1"
        assert record["update_time"] == "2026-07-10 12:00:00"

        # Check dim_scores mapping
        assert record["dim_scores"]["fin"] == 75.0
        assert record["dim_scores"]["comp"] == 65.0
        assert record["dim_scores"]["incentive"] == 70.0
        assert record["dim_scores"]["psych"] == 55.0
        assert record["dim_scores"]["neg"] == 100.0

        # Check radar_scores order
        assert record["radar_scores"] == [75.0, 65.0, 70.0, 55.0, 100.0]


def test_radar_writes_png(tmp_path):
    """render(record, out_path) writes PNG file with radar chart."""
    from radar import render

    record = {
        "radar_scores": [80, 70, 60, 50, 100],
        "symbol": "000001.SZ",
    }
    out_path = str(tmp_path / "test_radar.png")
    result = render(record, out_path)

    # Check return value is the path
    assert result == out_path

    # Check PNG file was created with non-zero size
    import os
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0
