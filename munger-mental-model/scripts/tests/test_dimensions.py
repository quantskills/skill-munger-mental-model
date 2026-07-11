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
            "roe": [15.0, 16.0, 17.0, 18.0, 19.0],
            "gross_profit": [0.35, 0.36, 0.37, 0.38, 0.39],
            "ocf": [500_000, 600_000, 700_000, 800_000, 900_000],
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
            "roe": [15.0, 16.0, 17.0, 18.0, 19.0],
            "gross_profit": [0.35, 0.36, 0.37, 0.38, 0.39],
            "ocf": [500_000, 600_000, 700_000, 800_000, 900_000],
        })
        result = dimensions.score_financial(target, peers)
        assert result["sub_scores"]["ocf_positive_and_vs_median"] == 0.0
        assert result["score"] < 100.0

    def test_financial_sub_scores_contain_raw_values(self):
        """Financial: sub_scores includes raw metric values and medians."""
        target = {"roe": 20.0, "gross_profit": 0.40, "ocf": 1_000_000}
        peers = pd.DataFrame({
            "roe": [15.0, 16.0, 17.0, 18.0, 19.0],
            "gross_profit": [0.35, 0.36, 0.37, 0.38, 0.39],
            "ocf": [500_000, 600_000, 700_000, 800_000, 900_000],
        })
        result = dimensions.score_financial(target, peers)
        ss = result["sub_scores"]

        assert ss["roe_value"] == 20.0
        assert ss["roe_median"] == 17.0
        assert ss["gm_value"] == 0.40
        assert ss["gm_median"] == 0.37
        assert ss["ocf_value"] == 1_000_000
        assert ss["ocf_median"] == 700_000


class TestScoreCompetition:
    """Tests for score_competition function."""

    def test_competition_low_confidence(self):
        """Competition: < 3 peers → low_confidence flag, passed=None (insufficient data)."""
        target = {"roe": 20.0, "gross_profit": 0.40}
        peers = pd.DataFrame({
            "roe": [15.0, 16.0],
            "gross_profit": [0.35, 0.36],
        })
        result = dimensions.score_competition(target, peers)
        assert any("low_confidence" in flag for flag in result["flags"])
        assert result["passed"] is None  # Insufficient data returns None

    def test_competition_sub_scores_contain_raw_values(self):
        """Competition: sub_scores includes raw metric values and peer counts."""
        target = {"roe": 20.0, "gross_profit": 0.40}
        peers = pd.DataFrame({
            "roe": [10.0, 12.0, 15.0, 18.0, 22.0],
            "gross_profit": [0.25, 0.30, 0.35, 0.38, 0.42],
        })
        result = dimensions.score_competition(target, peers)
        ss = result["sub_scores"]

        assert ss["roe_value"] == 20.0
        assert ss["gm_value"] == 0.40
        assert ss["peer_count"] == 5
        assert ss["valid_roe_count"] == 5
        assert ss["valid_gm_count"] == 5


class TestScoreIncentive:
    """Tests for redesigned score_incentive function (four-signal model)."""

    def test_incentive_clear_controller_full_score(self):
        """Incentive: clear controller (top1=45%, top2=15%, gap=3x) + no pledge + mgmt buy → high score."""
        top_holders = pd.DataFrame({
            "holder_name": ["大股东A", "股东B", "股东C"],
            "hold_percent_total": [45.0, 15.0, 10.0],
        })
        sh_change = pd.DataFrame({
            "nature": ["管理层", "管理层"],
            "net_change": [50_000, 20_000],
            "holder_type": ["management", "management"],
            "ratio_up_limit": [0.0, 0.0],
        })
        pledge = pd.DataFrame({"pledge_ratio": [0.0]})  # 0.0% (百分比形式)

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        # controller_clarity: top1=45%>20%, gap=3.0>=2 → 100
        # mgmt_trade: net buy → 100
        # pledge: 0% → 100
        # controlling_trade: no controlling rows → 50 (neutral)
        # weighted: 100*0.4 + 100*0.25 + 100*0.2 + 50*0.15 = 92.5
        assert result["score"] == 92.5
        assert result["passed"] == True
        assert result["sub_scores"]["controller_clarity_score"] == 100.0
        assert result["sub_scores"]["mgmt_trade_score"] == 100.0
        assert result["sub_scores"]["pledge_score"] == 100.0
        assert result["sub_scores"]["controlling_trade_score"] == 50.0

    def test_incentive_dispersed_ownership(self):
        """Incentive: dispersed ownership (top1=10%) → low controller clarity."""
        top_holders = pd.DataFrame({
            "holder_name": ["A", "B", "C", "D", "E"],
            "hold_percent_total": [10.0, 9.0, 8.0, 7.0, 6.0],
        })
        sh_change = pd.DataFrame()
        pledge = pd.DataFrame()

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        assert result["sub_scores"]["controller_clarity_score"] == 25.0

    def test_incentive_high_pledge_penalty(self):
        """Incentive: high pledge ratio (40%) → low pledge score."""
        top_holders = pd.DataFrame({
            "holder_name": ["大股东"],
            "hold_percent_total": [60.0],
        })
        sh_change = pd.DataFrame()
        pledge = pd.DataFrame({"pledge_ratio": [40.0]})

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        # pledge_ratio is in percentage form (40.0 = 40%)
        # convert to decimal: 40.0 / 100 = 0.40
        # pledge score = max(0, (1 - 0.40/0.50) * 100) = 20.0
        assert abs(result["sub_scores"]["pledge_score"] - 20.0) < 0.01

    def test_incentive_mgmt_sell(self):
        """Incentive: management net sell → mgmt_trade_score = 0."""
        top_holders = pd.DataFrame({
            "holder_name": ["大股东"],
            "hold_percent_total": [50.0],
        })
        sh_change = pd.DataFrame({
            "nature": ["管理层", "管理层"],
            "net_change": [-100_000, -50_000],
            "holder_type": ["management", "management"],
            "ratio_up_limit": [0.0, 0.0],
        })
        pledge = pd.DataFrame()

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        assert result["sub_scores"]["mgmt_trade_score"] == 0.0

    def test_incentive_no_data_neutral(self):
        """Incentive: empty DataFrames → neutral scores where applicable."""
        top_holders = pd.DataFrame()
        sh_change = pd.DataFrame()
        pledge = pd.DataFrame()

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        # controller_clarity: empty → 0
        # mgmt_trade: empty → 50 (neutral)
        # pledge: empty → 80 (assume no pledge)
        # controlling_trade: empty → 50 (neutral)
        # weighted: 0*0.4 + 50*0.25 + 80*0.2 + 50*0.15 = 36.0
        assert result["sub_scores"]["controller_clarity_score"] == 0.0
        assert result["sub_scores"]["mgmt_trade_score"] == 50.0
        assert result["sub_scores"]["pledge_score"] == 80.0
        assert result["sub_scores"]["controlling_trade_score"] == 50.0
        assert result["score"] == 36.0

    def test_incentive_controlling_shareholder_decrease(self):
        """Incentive: controlling shareholder net decrease < 2% → score 25."""
        top_holders = pd.DataFrame({
            "holder_name": ["大股东"],
            "hold_percent_total": [50.0],
        })
        sh_change = pd.DataFrame({
            "nature": ["大股东"],
            "net_change": [-100_000],
            "holder_type": ["controlling"],
            "ratio_up_limit": [0.01],
        })
        pledge = pd.DataFrame()

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        assert result["sub_scores"]["controlling_trade_score"] == 25.0

    def test_incentive_controlling_shareholder_increase(self):
        """Incentive: controlling shareholder net increase → score 100."""
        top_holders = pd.DataFrame({
            "holder_name": ["大股东"],
            "hold_percent_total": [50.0],
        })
        sh_change = pd.DataFrame({
            "nature": ["大股东"],
            "net_change": [200_000],
            "holder_type": ["controlling"],
            "ratio_up_limit": [0.0],
        })
        pledge = pd.DataFrame()

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        assert result["sub_scores"]["controlling_trade_score"] == 100.0


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
        "agency": ["Agency A"],
        "date": ["2025-06-30"],
        "quarter": ["2024q4"],
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
            "pledge_ratio": [10.0],  # 10% in percentage form
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
            "agency": ["Agency A"],
            "date": ["2025-06-30"],
            "quarter": ["2024q4"],
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
        """Negative: switch to unknown/small audit agency (not reputable) → veto with agency_switch_to_unknown flag."""
        audit = pd.DataFrame({
            "opinion": ["unqualified_opinion", "unqualified_opinion"],
            "audit_agency": ["Agency A", "Agency B"],
            "audit_date": ["2025-06-30", "2024-06-30"],
            "agency": ["Agency A", "Agency B"],
            "date": ["2025-06-30", "2024-06-30"],
            "quarter": ["2024q4", "2023q4"],
        })
        status = _empty(["status", "change_date"])
        pledge = _empty(["pledge_ratio"])
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["veto"] is True
        assert "agency_switch_to_unknown" in result["veto_flags"]

    def test_negative_reputable_agency_rotation_no_veto(self):
        """Negative: switch between reputable agencies (normal rotation) → NO veto, only info flag."""
        audit = pd.DataFrame({
            "opinion": ["unqualified_opinion", "unqualified_opinion", "unqualified_opinion"],
            "audit_agency": ["信永中和会计师事务所", "信永中和会计师事务所", "天健会计师事务所"],
            "agency": ["信永中和会计师事务所", "信永中和会计师事务所", "天健会计师事务所"],
            "audit_date": ["2023-04-20", "2024-04-18", "2025-04-15"],
            "date": ["2023-04-20", "2024-04-18", "2025-04-15"],
            "quarter": ["2022q4", "2023q4", "2024q4"],
        })
        status = _empty(["status", "change_date"])
        pledge = _empty(["pledge_ratio"])
        sh_change = _empty(["holder_type", "ratio_up_limit"])

        result = dimensions.score_negative(audit, status, pledge, sh_change)

        assert result["veto"] is False
        assert result["passed"] is True
        assert result["score"] == 100.0
        assert "agency_switch:normal_rotation" in result["flags"]
        assert all("agency_switch" not in vf for vf in result["veto_flags"])

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
        """Negative: max pledge_ratio > 50% (threshold) → veto."""
        audit = _clean_audit()
        status = _empty(["status", "change_date"])
        pledge = pd.DataFrame({
            "pledge_ratio": [60.0],  # 60% in percentage form, > 50% threshold
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
