# Task 1 Report: Fix Auditor Switch False-Positive Veto

## Implementation Summary

Fixed the bug where agency rotation between reputable audit firms incorrectly triggered a veto in the negative dimension scorer. The solution ensures that normal regulatory rotation between known reputable agencies only adds an info flag to `flags`, not to `veto_flags`.

### Changes Made

**File: `munger-mental-model/scripts/dimensions.py`**
- Line 545: Changed `veto_flags.append("agency_switch")` to `flags.append("agency_switch:normal_rotation")`
- Impact: Normal rotation between reputable agencies (both from `_REPUTABLE_AGENCIES`) with standard opinions is now flagged as informational only, not as a veto condition

**File: `munger-mental-model/scripts/tests/test_dimensions.py`**
1. Updated `_clean_audit()` helper to include required columns: `agency`, `date`, `quarter`
2. Updated `test_negative_nonstandard_audit_veto()` audit fixture to include required columns
3. Updated `test_negative_agency_switch_veto()` audit fixture to include required columns and updated assertion to check for `agency_switch_to_unknown` (the actual veto flag returned when switching to unknown firms)
4. Updated `test_negative_agency_switch_veto()` docstring for clarity
5. Added new test `test_negative_reputable_agency_rotation_no_veto()` that verifies:
   - Switching between reputable agencies (信永中和→天健) does NOT trigger veto
   - Score remains 100.0 with passed=True
   - `agency_switch:normal_rotation` flag is present in `flags`
   - No `agency_switch` flags appear in `veto_flags`

## Test Results

**Command:** `cd munger-mental-model/scripts && python -m pytest tests/test_dimensions.py::TestScoreNegative -v`

**Output:**
```
============================= test session starts ==============================
tests/test_dimensions.py::TestScoreNegative::test_negative_clean_pass PASSED [ 14%]
tests/test_dimensions.py::TestScoreNegative::test_negative_nonstandard_audit_veto PASSED [ 28%]
tests/test_dimensions.py::TestScoreNegative::test_negative_agency_switch_veto PASSED [ 42%]
tests/test_dimensions.py::TestScoreNegative::test_negative_reputable_agency_rotation_no_veto PASSED [ 57%]
tests/test_dimensions.py::TestScoreNegative::test_negative_status_change_veto PASSED [ 71%]
tests/test_dimensions.py::TestScoreNegative::test_negative_high_pledge_veto PASSED [ 85%]
tests/test_dimensions.py::TestScoreNegative::test_negative_large_controlling_sell_veto PASSED [100%]

============================== 7 passed in 0.55s ===============================
```

All 7 TestScoreNegative tests pass, including the new reputable agency rotation test.

## Scoring Logic Verification

The fix maintains the correct three-level veto logic for agency switches:

1. **Unknown/Small Firm Switch** (VETO): When switching to a firm NOT in `_REPUTABLE_AGENCIES` → adds `agency_switch_to_unknown` to veto_flags
2. **Opinion Degradation** (VETO): When opinion becomes non-standard after a switch → adds `agency_switch_with_opinion_change` to veto_flags  
3. **Normal Rotation** (INFO ONLY): When both firms are reputable AND opinion remains standard → adds `agency_switch:normal_rotation` to flags (not veto_flags)

The existing test `test_negative_agency_switch_veto` correctly tests path #1 (unknown firm), and the new test `test_negative_reputable_agency_rotation_no_veto` correctly tests path #3 (normal rotation).

## Observations

- All existing TestScoreNegative tests continue to pass
- The fix aligns the implementation with the documented intent: only veto when switching to unknown/unreliable firms or when opinion degrades
- Normal regulatory rotation between two reputable big accounting firms (国内前20大所 + 四大本土化品牌) is no longer incorrectly flagged as a red flag
- Test data properly includes all required columns (agency, date, quarter) needed by the score_negative logic

## Concerns

None. The fix is minimal, targeted, and all tests pass.

## Final Status

DONE

**Commit Hash:** 6f78dc8
