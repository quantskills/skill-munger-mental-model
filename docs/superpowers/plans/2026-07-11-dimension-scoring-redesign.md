# Dimension Scoring Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three scoring issues: redesign incentive dimension with four-signal model, fix auditor switch false-positive veto, and expose raw metric values in sub_scores.

**Architecture:** All changes are in `dimensions.py` (scoring logic), `analyze.py` (caller), and `tests/test_dimensions.py`. The data layer (`data.py`) is unchanged — all needed APIs already exist.

**Tech Stack:** Python 3.10+, pandas, pytest

## Global Constraints

- All scoring functions return `dict` with keys: `score`, `passed`, `flags`, `sub_scores`
- Scores are 0.0–100.0, clamped
- `_passed(score)` uses `config.pass_threshold()` (default 60.0)
- Tests run with: `cd munger-mental-model/scripts && python -m pytest tests/ -v`
- Existing test assertions for unrelated functions must not break

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `munger-mental-model/scripts/dimensions.py` | Modify | Scoring logic for all dimensions |
| `munger-mental-model/scripts/analyze.py` | Modify | Pass `pledge` to `score_incentive()` |
| `munger-mental-model/scripts/tests/test_dimensions.py` | Modify | All unit tests |

---

### Task 1: Fix Auditor Switch False-Positive Veto

**Files:**
- Modify: `munger-mental-model/scripts/dimensions.py:527-535`
- Modify: `munger-mental-model/scripts/tests/test_dimensions.py`

**Interfaces:**
- Consumes: `score_negative(audit, status, pledge, sh_change)` — existing signature unchanged
- Produces: Same return dict, but `agency_switch:normal_rotation` goes to `flags` not `veto_flags`

- [ ] **Step 1: Write the failing test for reputable-to-reputable rotation**

Add to `TestScoreNegative` in `tests/test_dimensions.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreNegative::test_negative_reputable_agency_rotation_no_veto -v`

Expected: FAIL — currently appends to `veto_flags`

- [ ] **Step 3: Fix the bug in dimensions.py**

In `score_negative()`, replace lines 533–535:

```python
            else:
                # Normal switch within reputable agencies - still flag it for visibility
                veto_flags.append("agency_switch")
                print(f"        ✓ 近3年换所但属正常轮换: {list(recent_agencies)} (均为知名大所且意见标准)")
```

With:

```python
            else:
                # Normal switch within reputable agencies — info flag only, NOT a veto
                flags.append("agency_switch:normal_rotation")
                print(f"        ✓ 近3年换所但属正常轮换: {list(recent_agencies)} (均为知名大所且意见标准)")
```

- [ ] **Step 4: Run all negative dimension tests**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreNegative -v`

Expected: ALL PASS

- [ ] **Step 5: Update the existing agency_switch test docstring for clarity**

The existing `test_negative_agency_switch_veto` uses "Agency A" / "Agency B" which are NOT in `_REPUTABLE_AGENCIES`, so it correctly tests the unknown-agency path. Update its docstring:

```python
def test_negative_agency_switch_veto(self):
    """Negative: switch to unknown (non-reputable) audit agency → veto."""
```

- [ ] **Step 6: Commit**

```bash
git add munger-mental-model/scripts/dimensions.py munger-mental-model/scripts/tests/test_dimensions.py
git commit -m "fix: auditor normal rotation no longer triggers veto

Switches between known reputable agencies (e.g., 信永中和→天健) are
recorded as info flags only. Veto remains for switches to unknown
firms or when opinion degrades post-switch."
```

---

### Task 2: Add Raw Values to Financial & Competition Sub-Scores

**Files:**
- Modify: `munger-mental-model/scripts/dimensions.py:129-133` (financial sub_scores)
- Modify: `munger-mental-model/scripts/dimensions.py:220-224` (competition sub_scores)
- Modify: `munger-mental-model/scripts/tests/test_dimensions.py`

**Interfaces:**
- Consumes: `score_financial(target, peers)`, `score_competition(target, peers)` — signatures unchanged
- Produces: Same return dict with additional keys in `sub_scores`

- [ ] **Step 1: Write failing test for financial raw values**

Add to `TestScoreFinancial`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreFinancial::test_financial_sub_scores_contain_raw_values -v`

Expected: FAIL — KeyError on `roe_value`

- [ ] **Step 3: Add raw values to score_financial sub_scores**

In `score_financial()`, replace the `sub_scores` dict (around line 129):

```python
    sub_scores = {
        "roe_vs_median": roe_score,
        "gm_vs_median": gm_score,
        "ocf_positive_and_vs_median": ocf_score,
        "roe_value": roe_val,
        "roe_median": roe_median,
        "gm_value": gm_val,
        "gm_median": gm_median,
        "ocf_value": ocf_val,
        "ocf_median": ocf_median,
    }
```

- [ ] **Step 4: Write failing test for competition raw values**

Add to `TestScoreCompetition`:

```python
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
```

- [ ] **Step 5: Add raw values to score_competition sub_scores**

In `score_competition()`, replace the `sub_scores` dict (around line 220):

```python
    sub_scores = {
        "roe_percentile": roe_percentile,
        "gm_percentile": gm_percentile,
        "concentration_bonus": concentration_bonus,
        "roe_value": roe_val,
        "gm_value": gm_val,
        "peer_count": len(peers),
        "valid_roe_count": valid_roe,
        "valid_gm_count": valid_gm,
    }
```

- [ ] **Step 6: Run all financial and competition tests**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreFinancial tests/test_dimensions.py::TestScoreCompetition -v`

Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add munger-mental-model/scripts/dimensions.py munger-mental-model/scripts/tests/test_dimensions.py
git commit -m "feat: expose raw metric values in financial & competition sub_scores

Adds roe_value, roe_median, gm_value, gm_median, ocf_value, ocf_median
to financial sub_scores. Adds roe_value, gm_value, peer_count,
valid_roe_count, valid_gm_count to competition sub_scores."
```

---

### Task 3: Redesign Incentive Dimension

**Files:**
- Modify: `munger-mental-model/scripts/dimensions.py:246-352` (replace `score_incentive`)
- Modify: `munger-mental-model/scripts/analyze.py:264` (pass `pledge` to `score_incentive`)
- Modify: `munger-mental-model/scripts/tests/test_dimensions.py` (rewrite `TestScoreIncentive`)

**Interfaces:**
- Consumes: `fetch_top_holders()` → DataFrame, `fetch_shareholder_change()` → DataFrame, `fetch_pledge()` → DataFrame
- Produces: `score_incentive(top_holders, sh_change, pledge) → dict` with new sub_scores structure

- [ ] **Step 1: Write failing tests for the new incentive model**

Replace the entire `TestScoreIncentive` class in `tests/test_dimensions.py`:

```python
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
        pledge = pd.DataFrame({"pledge_ratio": [0.0]})

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        # controller_clarity: top1=45%>20%, gap=3.0>=2 → 100
        # mgmt_trade: net buy → 100
        # pledge: 0% → 100
        # controlling_trade: no controlling rows → 50 (neutral)
        # weighted: 100*0.4 + 100*0.25 + 100*0.2 + 50*0.15 = 92.5
        assert result["score"] == 92.5
        assert result["passed"] is True
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
        pledge = pd.DataFrame({"pledge_ratio": [0.40]})

        result = dimensions.score_incentive(top_holders, sh_change, pledge)

        # pledge score = max(0, (1 - 0.40/0.50) * 100) = 20.0
        assert result["sub_scores"]["pledge_score"] == 20.0

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreIncentive -v`

Expected: FAIL — `score_incentive()` doesn't accept `pledge` parameter

- [ ] **Step 3: Replace score_incentive implementation**

Replace the entire `score_incentive` function in `dimensions.py` (lines 246–352) with:

```python
def score_incentive(top_holders: pd.DataFrame, sh_change: pd.DataFrame, pledge: pd.DataFrame) -> dict:
    """
    Score incentive dimension: four-signal composite model.

    Signals and weights:
    - Controller clarity (40%): clear single controller with gap to #2
    - Management trading (25%): net buy/sell by management
    - Pledge ratio (20%): controlling shareholder pledge level
    - Controlling shareholder trading (15%): net increase/decrease

    Args:
        top_holders: DataFrame with 'hold_percent_total' (or 'hold_ratio')
        sh_change: DataFrame with 'nature', 'net_change', 'holder_type', 'ratio_up_limit'
        pledge: DataFrame with 'pledge_ratio'

    Returns:
        dict with keys: score, passed, flags, sub_scores
    """
    flags = []

    # --- Signal 1: Controller Clarity (40%) ---
    controller_clarity_score = 0.0
    top1_ratio = 0.0
    top2_ratio = 0.0
    gap_ratio = 0.0

    if not top_holders.empty:
        # Get holding ratios in percent
        if "hold_percent_total" in top_holders.columns:
            ratios = top_holders["hold_percent_total"].sort_values(ascending=False).values
        elif "hold_ratio" in top_holders.columns:
            ratios = (top_holders["hold_ratio"] * 100.0).sort_values(ascending=False).values
        elif "hold_percent_float" in top_holders.columns:
            ratios = top_holders["hold_percent_float"].sort_values(ascending=False).values
        else:
            ratios = []

        if len(ratios) >= 1:
            top1_ratio = float(ratios[0])
        if len(ratios) >= 2:
            top2_ratio = float(ratios[1])

        if top2_ratio > 0:
            gap_ratio = top1_ratio / top2_ratio
        elif top1_ratio > 0:
            gap_ratio = float("inf")

        # Scoring tiers
        if top1_ratio >= 20.0 and gap_ratio >= 2.0:
            controller_clarity_score = 100.0
        elif top1_ratio >= 20.0 and gap_ratio >= 1.5:
            controller_clarity_score = 75.0
        elif top1_ratio >= 15.0 and gap_ratio >= 1.2:
            controller_clarity_score = 50.0
        else:
            controller_clarity_score = 25.0
    # else: empty top_holders → 0.0

    # --- Signal 2: Management Trading (25%) ---
    mgmt_trade_score = 50.0  # Default: neutral (no data)
    mgmt_net_change = 0.0
    mgmt_direction = "none"

    if not sh_change.empty and "nature" in sh_change.columns and "net_change" in sh_change.columns:
        mgmt_rows = sh_change[sh_change["nature"] == "管理层"]
        if not mgmt_rows.empty:
            mgmt_net_change = float(mgmt_rows["net_change"].sum())
            if mgmt_net_change > 0:
                mgmt_trade_score = 100.0
                mgmt_direction = "buy"
            elif mgmt_net_change < 0:
                mgmt_trade_score = 0.0
                mgmt_direction = "sell"
            # else: net zero → stays at 50 neutral

    # --- Signal 3: Pledge Ratio (20%) ---
    pledge_score = 80.0  # Default: no data → assume positive
    max_pledge_ratio = 0.0

    if not pledge.empty and "pledge_ratio" in pledge.columns:
        max_pledge_ratio = float(pledge["pledge_ratio"].max())
        # Formula: max(0, (1 - max_pledge / 0.50) * 100)
        pledge_score = max(0.0, (1.0 - max_pledge_ratio / 0.50) * 100.0)

    # --- Signal 4: Controlling Shareholder Trading (15%) ---
    controlling_trade_score = 50.0  # Default: neutral
    controlling_direction = "none"
    controlling_ratio_change = 0.0

    if not sh_change.empty and "holder_type" in sh_change.columns:
        controlling_rows = sh_change[sh_change["holder_type"] == "controlling"]
        if not controlling_rows.empty:
            if "net_change" in sh_change.columns:
                net = float(controlling_rows["net_change"].sum())
                if net > 0:
                    controlling_trade_score = 100.0
                    controlling_direction = "increase"
                elif net < 0:
                    # Check magnitude via ratio_up_limit
                    if "ratio_up_limit" in controlling_rows.columns:
                        controlling_ratio_change = float(controlling_rows["ratio_up_limit"].max())
                        if controlling_ratio_change >= 0.02:
                            controlling_trade_score = 0.0
                        else:
                            controlling_trade_score = 25.0
                    else:
                        controlling_trade_score = 25.0
                    controlling_direction = "decrease"

    # --- Weighted composite ---
    score = (
        controller_clarity_score * 0.40
        + mgmt_trade_score * 0.25
        + pledge_score * 0.20
        + controlling_trade_score * 0.15
    )
    score = max(0.0, min(100.0, score))

    sub_scores = {
        "controller_clarity_score": controller_clarity_score,
        "controller_clarity_detail": {
            "top1_ratio": top1_ratio,
            "top2_ratio": top2_ratio,
            "gap_ratio": gap_ratio if gap_ratio != float("inf") else 999.0,
        },
        "mgmt_trade_score": mgmt_trade_score,
        "mgmt_trade_detail": {
            "net_change": mgmt_net_change,
            "direction": mgmt_direction,
        },
        "pledge_score": pledge_score,
        "pledge_detail": {
            "max_pledge_ratio": max_pledge_ratio,
        },
        "controlling_trade_score": controlling_trade_score,
        "controlling_trade_detail": {
            "net_direction": controlling_direction,
            "ratio_change": controlling_ratio_change,
        },
    }

    print(f"    [DETAIL] 激励机制维度详细计算 (四信号模型):")
    print(f"      信号1 - 实控人明确性 (40%): {controller_clarity_score:.1f}")
    print(f"        第一大股东: {top1_ratio:.2f}%, 第二大股东: {top2_ratio:.2f}%, 差距倍数: {gap_ratio:.2f}")
    print(f"      信号2 - 管理层增减持 (25%): {mgmt_trade_score:.1f}")
    print(f"        净变动: {mgmt_net_change:.0f}, 方向: {mgmt_direction}")
    print(f"      信号3 - 质押比例 (20%): {pledge_score:.1f}")
    print(f"        最高质押率: {max_pledge_ratio:.4f}")
    print(f"      信号4 - 大股东增减持 (15%): {controlling_trade_score:.1f}")
    print(f"        方向: {controlling_direction}, 变动比例: {controlling_ratio_change:.4f}")
    print(f"      加权总分: {controller_clarity_score:.1f}×0.4 + {mgmt_trade_score:.1f}×0.25 + {pledge_score:.1f}×0.2 + {controlling_trade_score:.1f}×0.15 = {score:.2f}")

    return {
        "score": score,
        "passed": _passed(score),
        "flags": flags,
        "sub_scores": sub_scores,
    }
```

- [ ] **Step 4: Run incentive tests**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreIncentive -v`

Expected: ALL PASS

- [ ] **Step 5: Update analyze.py to pass pledge to score_incentive**

In `analyze.py`, find line 264:

```python
    dims_incentive = dimensions.score_incentive(top_holders, sh_change)
```

Replace with:

```python
    dims_incentive = dimensions.score_incentive(top_holders, sh_change, pledge)
```

Note: `pledge` is already fetched at line 290 for the negative dimension. We need to move the pledge fetch BEFORE the incentive scoring. Find the pledge fetch block (around line 287–300) and move it before the incentive scoring section.

The reordered flow in `analyze_symbol()` should be:

```python
    # Fetch pledge data (needed by both incentive and negative dimensions)
    print(f"\n[STEP 5a] Fetching pledge data...")
    try:
        pledge = data.fetch_pledge(symbol, end_date)
        print(f"  ✓ Pledge records: {len(pledge)}")
        if not pledge.empty:
            print(f"    {pledge.to_string()}")
    except Exception as e:
        print(f"  ⚠ Warning: Could not fetch pledge data for {symbol}: {e}")
        pledge = __import__('pandas').DataFrame()

    # Score incentive dimension (now uses pledge)
    dims_incentive = dimensions.score_incentive(top_holders, sh_change, pledge)
```

And later in the negative dimension section, remove the duplicate pledge fetch (use the already-fetched `pledge` variable).

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/dmiwu/work/PythonProject/PandaAIQuant/claude_code_skills/skill-munger-mental-model/munger-mental-model/scripts && python -m pytest tests/ -v`

Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add munger-mental-model/scripts/dimensions.py munger-mental-model/scripts/analyze.py munger-mental-model/scripts/tests/test_dimensions.py
git commit -m "feat: redesign incentive dimension with four-signal composite model

Replaces broken 30-70% sweet spot with:
- Controller clarity (40%): top1 ratio + gap to top2
- Management trading (25%): net buy/sell direction
- Pledge ratio (20%): linear penalty up to 50%
- Controlling shareholder trading (15%): increase/decrease

Signature change: score_incentive() now takes pledge DataFrame as 3rd arg.
analyze.py reordered to fetch pledge before incentive scoring."
```

---
