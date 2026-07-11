# Dimension Scoring Redesign

**Date:** 2026-07-11
**Scope:** `munger-mental-model/scripts/dimensions.py`, `data.py`, `test_dimensions.py`

## Overview

Three changes to the Munger 5-dimension scoring system:

1. **Incentive dimension** — full redesign with four-signal composite model
2. **Auditor switch logic** — fix false-positive veto on normal rotation
3. **Sub-scores raw values** — expose underlying metrics in financial & competition dimensions

---

## Change 1: Incentive Dimension Redesign

### Current Problems

- `score_incentive()` uses a 30–70% "sweet spot" for top-10 holder concentration
- A-share companies commonly have 70–90%+ concentration (e.g., 贵州茅台), making the sweet spot unrealistic
- Score collapses to 0 for many high-quality companies

### New Model: Four-Signal Composite

Replace the existing `score_incentive(top_holders, sh_change)` function with a new scoring model:

| Signal | Weight | Source Data | Scoring Logic |
|--------|--------|-------------|---------------|
| 实控人明确性 | 40% | `top_holders` | See below |
| 管理层持股+增减持 | 25% | `sh_change` (nature="管理层") | See below |
| 大股东质押比例 | 20% | `pledge` (from `fetch_pledge`) | See below |
| 大股东增减持 | 15% | `sh_change` (holder_type="controlling") | See below |

#### Signal 1: 实控人明确性 (40%)

Measures whether the company has a clear controlling party.

**Inputs:** `top_holders` DataFrame — use `hold_percent_total` (or `hold_ratio × 100`)

**Logic:**
- `top1_ratio` = first shareholder's holding %
- `top2_ratio` = second shareholder's holding %
- `gap_ratio` = `top1_ratio / top2_ratio` (if top2 > 0, else treat as ∞)

**Scoring (0–100):**
- `top1_ratio >= 20%` AND `gap_ratio >= 2.0` → **100** (clear controller)
- `top1_ratio >= 20%` AND `gap_ratio >= 1.5` → **75** (likely controller)
- `top1_ratio >= 15%` AND `gap_ratio >= 1.2` → **50** (weak controller)
- `top1_ratio < 15%` OR `gap_ratio < 1.2` → **25** (dispersed/unclear)
- If `top_holders` is empty → **0** (no data)

**Rationale:** In A-shares, a clear single controller with meaningful gap to #2 is a positive governance signal. This replaces the broken "sweet spot" logic.

#### Signal 2: 管理层持股+增减持 (25%)

Measures management skin-in-the-game via trading activity.

**Inputs:** `sh_change` filtered to `nature == "管理层"`

**Logic:**
- Sum `net_change` for all management rows
- If net positive (net buy) → **100**
- If zero / no management rows → **50** (neutral, no data penalty)
- If net negative (net sell) → **0**

**Note:** Panda Data does not have a dedicated 股权激励计划 API, so we use management trading as the proxy signal. "No data" scores 50 (neutral) rather than 0 to avoid penalizing companies where management simply doesn't trade.

#### Signal 3: 大股东质押比例 (20%)

Measures financial stress of controlling shareholders.

**Inputs:** `pledge` DataFrame from `fetch_pledge()` — use `pledge_ratio` column

**Logic (based on max pledge ratio across all records):**
- `max_pledge == 0` → **100** (no pledge, ideal)
- `0 < max_pledge <= 0.30` → linear from 100 → 50
- `0.30 < max_pledge <= 0.50` → linear from 50 → 0
- `max_pledge > 0.50` → **0** (also triggers veto in negative dimension)
- No pledge data → **80** (assume positive — most companies don't pledge)

**Formula:** `score = max(0, 100 - (max_pledge / 0.50) * 100)`
Simplified: `score = max(0, (1 - max_pledge / 0.50) * 100)`

#### Signal 4: 大股东增减持 (15%)

Measures controlling shareholder conviction.

**Inputs:** `sh_change` filtered to controlling shareholders

**Logic:**
- Controlling shareholder net increase → **100**
- No change / no data → **50** (neutral)
- Controlling shareholder net decrease (but < 2% of float) → **25** (mild concern)
- Controlling shareholder net decrease (≥ 2% of float) → **0** (strong negative, also triggers veto)

### New Function Signature

```python
def score_incentive(
    top_holders: pd.DataFrame,
    sh_change: pd.DataFrame,
    pledge: pd.DataFrame,  # NEW parameter
) -> dict:
```

**Breaking change:** Adds `pledge` parameter. Caller (`analyze.py`) must pass the already-fetched pledge DataFrame.

### Return Value

```python
{
    "score": float,  # 0–100, weighted composite
    "passed": bool,
    "flags": [...],
    "sub_scores": {
        "controller_clarity_score": float,  # 0–100
        "controller_clarity_detail": {
            "top1_ratio": float,
            "top2_ratio": float,
            "gap_ratio": float,
        },
        "mgmt_trade_score": float,  # 0–100
        "mgmt_trade_detail": {
            "net_change": float,
            "direction": str,  # "buy" | "sell" | "none"
        },
        "pledge_score": float,  # 0–100
        "pledge_detail": {
            "max_pledge_ratio": float,
        },
        "controlling_trade_score": float,  # 0–100
        "controlling_trade_detail": {
            "net_direction": str,  # "increase" | "decrease" | "none"
            "ratio_change": float,
        },
    },
}
```

---

## Change 2: Auditor Switch Logic Fix

### Current Bug

In `score_negative()`, line 533–534:
```python
# Normal switch within reputable agencies - still flag it for visibility
veto_flags.append("agency_switch")
```

This incorrectly puts a "normal rotation" case into `veto_flags`, triggering the one-vote veto.

### Fix

Change the normal-rotation case to append to `flags` (info level) instead of `veto_flags`:

```python
# Normal switch within reputable agencies — log for visibility only
flags.append("agency_switch:normal_rotation")
```

**Veto conditions remain:**
- `agency_switch_to_unknown` — new agency not in `_REPUTABLE_AGENCIES` → veto
- `agency_switch_with_opinion_change` — non-standard opinion after switch → veto

**Non-veto (info only):**
- `agency_switch:normal_rotation` — known-reputable → known-reputable, standard opinions → flag only

### Test Impact

`test_negative_agency_switch_veto` uses "Agency A" / "Agency B" (not in `_REPUTABLE_AGENCIES`), so it actually tests the unknown-agency path correctly. The fix:
- Keep existing test as-is (it now covers `agency_switch_to_unknown`)
- Add a NEW test with agencies from `_REPUTABLE_AGENCIES` (e.g., 信永中和 → 天健) → assert NO veto, only `agency_switch:normal_rotation` in `flags`

---

## Change 3: Sub-Scores Raw Values

### Financial Dimension (`score_financial`)

Add to `sub_scores`:
```python
"roe_value": roe_val,
"roe_median": roe_median,
"gm_value": gm_val,
"gm_median": gm_median,
"ocf_value": ocf_val,
"ocf_median": ocf_median,
```

### Competition Dimension (`score_competition`)

Add to `sub_scores`:
```python
"roe_value": roe_val,
"gm_value": gm_val,
"peer_count": len(peers),
"valid_roe_count": valid_roe,
"valid_gm_count": valid_gm,
```

These additions are purely additive — existing `sub_scores` keys remain unchanged.

---

## Data Dependencies

| Function | Data Source | Already Fetched? |
|----------|------------|-----------------|
| `score_incentive` needs `pledge` | `fetch_pledge()` | Yes — already fetched in `analyze_symbol()` for negative dimension |
| All other data | Existing fetches | No change |

The `pledge` DataFrame is already fetched at line 290 of `analyze.py` for the negative dimension. We just need to pass it to `score_incentive()` as well.

---

## Migration Notes

- `score_incentive` signature changes (adds `pledge` param) — update caller in `analyze.py`
- Test `test_incentive_related_party_flag` needs rewrite for new model
- Test `test_negative_agency_switch_veto` needs split into two cases
- No changes to `config.py` (no new env vars needed)
- No changes to `data.py` (all data sources already exist)
