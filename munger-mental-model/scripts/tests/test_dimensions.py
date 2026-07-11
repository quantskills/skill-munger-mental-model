"""
Tests for dimensions.py dimension scoring functions.
Verifies financial, competition, incentive, and psychology dimension scorers.
"""

from __future__ import annotations

import pytest
import pandas as pd
from datetime import datetime

import config
import dimensions


class TestScoreFinancial:
    """Tests for score_financial function."""

    def test_financial_all_above_median(self):
        """Financial: ROE, GM, OCF all above median → score 100, passed=True."""
        target = {"roe": 20.0, "gross_profit": 0.40, "ocf": 1_000_000}
        peers = pd.DataFrame({
            "roe": [15.0, 16.0, 17.0],
            "gross_profit": [0.35, 0.36, 0.37],
            "ocf": [500_000, 600_000, 700_000],
        })
        result = dimensions.score_financial(target, peers)
        assert result["score"] == 100.0
        assert result["passed"] is True
        assert "roe_vs_median" in result["sub_scores"]
        assert "gm_vs_median" in result["sub_scores"]
        assert "ocf_positive_and_vs_median" in result["sub_scores"]

    def test_financial_negative_ocf(self):
        """Financial: Negative OCF → ocf_positive_and_vs_median=0, score < 100."""
        target = {"roe": 20.0, "gross_profit": 0.40, "ocf": -100_000}
        peers = pd.DataFrame({
            "roe": [15.0, 16.0, 17.0],
            "gross_profit": [0.35, 0.36, 0.37],
            "ocf": [500_000, 600_000, 700_000],
        })
        result = dimensions.score_financial(target, peers)
        assert result["sub_scores"]["ocf_positive_and_vs_median"] == 0.0
        assert result["score"] < 100.0


class TestScoreCompetition:
    """Tests for score_competition function."""

    def test_competition_low_confidence(self):
        """Competition: < 3 peers → low_confidence flag, passed=False."""
        target = {"roe": 20.0, "gross_profit": 0.40}
        peers = pd.DataFrame({
            "roe": [15.0, 16.0],
            "gross_profit": [0.35, 0.36],
        })
        result = dimensions.score_competition(target, peers)
        assert "low_confidence" in result["flags"]
        assert result["passed"] is False


class TestScoreIncentive:
    """Tests for score_incentive function."""

    def test_incentive_related_party_flag(self):
        """Incentive: Always includes 'related_party: data_unavailable' flag."""
        top_holders = pd.DataFrame({
            "holder_name": ["Alice", "Bob"],
            "hold_ratio": [0.40, 0.30],
        })
        sh_change = pd.DataFrame({
            "nature": ["管理层", "管理层"],
            "net_change": [10_000, -5_000],
            "pledge_ratio": [0.0, 0.0],
            "freeze_ratio": [0.0, 0.0],
        })
        result = dimensions.score_incentive(top_holders, sh_change)
        assert "related_party: data_unavailable" in result["flags"]


class TestScorePsychology:
    """Tests for score_psychology function."""

    def test_psychology_qa_sentiment_flag(self):
        """Psychology: Always includes 'qa_sentiment: not_available' flag."""
        activity = pd.DataFrame({
            "activity_date": [
                "2025-01-01", "2025-02-01", "2025-03-01",
                "2025-04-01", "2025-05-01", "2025-06-01",
            ],
            "num_investors": [10, 12, 15, 11, 13, 14],
            "num_institutes": [5, 6, 7, 6, 7, 8],
        })
        result = dimensions.score_psychology(activity)
        assert "qa_sentiment: not_available" in result["flags"]

    def test_psychology_empty_activity(self):
        """Psychology: Empty activity DataFrame → score 0."""
        activity = pd.DataFrame({
            "activity_date": [],
            "num_investors": [],
            "num_institutes": [],
        })
        result = dimensions.score_psychology(activity)
        assert result["score"] == 0.0


def _clean_audit() -> pd.DataFrame:
    """Helper: Return a standard audit opinion row."""
    return pd.DataFrame({
        "opinion": ["unqualified_opinion"],
        "audit_agency": ["Agency A"],
        "audit_date": ["2025-06-30"],
    })


def _empty(cols: list[str]) -> pd.DataFrame:
    """Helper: Return an empty DataFrame with given columns."""
    return pd.DataFrame({col: [] for col in cols})


class TestScoreNegative:
    """Tests for score_negative function."""

    def test_negative_clean_pass(self):
        """Negative: clean audit + no status/pledge/agency switch → passed=True, veto=False."""
        audit = _clean_audit()
        status = _empty(["status", "change_date"])
        pledge = pd.DataFrame({
            "pledge_ratio": [0.10],
        })
        sh_change = pd.DataFrame({
            "holder_type": ["controlling"],
            "ratio_up_limit": [0.01],
        })

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 100.0
        assert result["passed"] is True
        assert result["veto"] is False
        assert result["veto_flags"] == []
        assert result["flags"] == []
        assert result["sub_scores"]["veto_count"] == 0

    def test_negative_nonstandard_audit_veto(self):
        """Negative: nonstandard audit opinion → veto."""
        audit = pd.DataFrame({
            "opinion": ["qualified_opinion"],
            "audit_agency": ["Agency A"],
            "audit_date": ["2025-06-30"],
        })
        status = _empty(["status", "change_date"])
        pledge = _empty(["pledge_ratio"])
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "nonstandard_audit:qualified_opinion" in result["veto_flags"]

    def test_negative_agency_switch_veto(self):
        """Negative: multiple distinct audit agencies → veto."""
        audit = pd.DataFrame({
            "opinion": ["unqualified_opinion", "unqualified_opinion"],
            "audit_agency": ["Agency A", "Agency B"],
            "audit_date": ["2025-06-30", "2024-06-30"],
        })
        status = _empty(["status", "change_date"])
        pledge = _empty(["pledge_ratio"])
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "agency_switch" in result["veto_flags"]

    def test_negative_status_change_veto(self):
        """Negative: status row present (ST or delisting) → veto."""
        audit = _clean_audit()
        status = pd.DataFrame({
            "status": ["ST"],
            "change_date": ["2025-06-30"],
        })
        pledge = _empty(["pledge_ratio"])
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "status_change:ST_or_delisting" in result["veto_flags"]

    def test_negative_high_pledge_veto(self):
        """Negative: max pledge_ratio > 0.50 → veto."""
        audit = _clean_audit()
        status = _empty(["status", "change_date"])
        pledge = pd.DataFrame({
            "pledge_ratio": [0.60],
        })
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "high_pledge" in result["veto_flags"]

    def test_negative_large_controlling_sell_veto(self):
        """Negative: controlling shareholder 减持 with ratio_up_limit > 0.02 → veto + hostile_takeover flag."""
        audit = _clean_audit()
        status = _empty(["status", "change_date"])
        pledge = _empty(["pledge_ratio"])
        sh_change = pd.DataFrame({
            "holder_type": ["controlling"],
            "ratio_up_limit": [0.03],
        })

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "large_controlling_sell" in result["veto_flags"]
        assert "hostile_takeover: weak_proxy" in result["flags"]
