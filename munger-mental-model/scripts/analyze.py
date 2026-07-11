"""
Orchestration layer for Munger mental model analysis.

Provides cross-validation logic, record building, and CLI interface.
Implements the five-dimension scoring with one-vote veto mechanism.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import config
import data
import dimensions


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_, np.integer, np.floating)):
            return obj.item()
        return super().default(obj)


# Radar chart rendering (stub for now)
def _render_radar(symbol: str, radar_scores: list[float], output_path: str) -> None:
    """
    Render and save a 5-dimensional radar chart as PNG.

    Args:
        symbol: Stock symbol
        radar_scores: List of 5 scores [fin, comp, incentive, psych, neg]
        output_path: Path to save PNG file
    """
    # Stub implementation - in full version would use matplotlib/plotly
    pass


def cross_validate(dims: dict) -> dict:
    """
    Cross-validate dimensions and render final verdict with high_confidence flag.

    Args:
        dims: Dict mapping DIM_KEYS to dimension result dicts.
              Each dim dict has: score, passed, veto, flags, sub_scores

    Returns:
        dict with keys: high_confidence (bool), verdict (str), radar_scores (list[float])

    Logic (spec §5):
    - If dims["neg"]["veto"] → verdict "veto", high_confidence False
    - Elif any dim passed is None → verdict "insufficient_data", False
    - Elif all five passed is True → verdict "pass", True
    - Else → verdict "fail", False
    """
    # Check veto flag from negative dimension
    if dims["neg"].get("veto", False):
        return {
            "high_confidence": False,
            "verdict": "veto",
            "radar_scores": [dims[k]["score"] for k in config.DIM_KEYS],
        }

    # Check for any None (insufficient data)
    for key in config.DIM_KEYS:
        if dims[key]["passed"] is None:
            return {
                "high_confidence": False,
                "verdict": "insufficient_data",
                "radar_scores": [dims[k]["score"] for k in config.DIM_KEYS],
            }

    # Check if all passed
    all_passed = all(dims[k]["passed"] is True for k in config.DIM_KEYS)
    if all_passed:
        verdict = "pass"
        high_confidence = True
    else:
        verdict = "fail"
        high_confidence = False

    return {
        "high_confidence": high_confidence,
        "verdict": verdict,
        "radar_scores": [dims[k]["score"] for k in config.DIM_KEYS],
    }


def build_record(
    symbol: str,
    trade_date: str,
    dims: dict,
    update_time: str,
) -> dict:
    """
    Build full output record with all spec §6 fields.

    Args:
        symbol: Stock symbol
        trade_date: Trade date (YYYY-MM-DD)
        dims: Dimension results dict
        update_time: Update timestamp

    Returns:
        dict with spec §6 fields:
        - symbol, trade_date, dim_scores, dim_passed, sub_scores,
        - veto_flags, data_flags, radar_scores, high_confidence,
        - verdict, data_version, update_time
    """
    # Get cross-validation result
    xval = cross_validate(dims)

    # Collect all veto flags from negative dimension
    veto_flags = dims["neg"].get("veto_flags", [])

    # Collect all data flags from all dimensions
    data_flags = []
    for key in config.DIM_KEYS:
        data_flags.extend(dims[key].get("flags", []))

    # Build dim_scores and dim_passed dicts
    dim_scores = {k: dims[k]["score"] for k in config.DIM_KEYS}
    dim_passed = {k: dims[k]["passed"] for k in config.DIM_KEYS}

    # Collect all sub_scores
    sub_scores = {}
    for key in config.DIM_KEYS:
        sub_scores[key] = dims[key].get("sub_scores", {})

    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "dim_scores": dim_scores,
        "dim_passed": dim_passed,
        "sub_scores": sub_scores,
        "veto_flags": veto_flags,
        "data_flags": data_flags,
        "radar_scores": xval["radar_scores"],
        "high_confidence": xval["high_confidence"],
        "verdict": xval["verdict"],
        "data_version": config.DATA_VERSION,
        "update_time": update_time,
    }


def analyze_symbol(symbol: str, end_date: str | None, update_time: str) -> dict:
    """
    Analyze a single symbol: fetch data, score all 5 dimensions, build record.

    Args:
        symbol: Stock symbol
        end_date: Optional analysis date (YYYY-MM-DD or YYYYMMDD)
        update_time: Update timestamp string

    Returns:
        Full analysis record dict (from build_record)

    Flow:
    1. Fetch industry peers + fina for all (target + peers)
    2. Extract target row
    3. Score all 5 dimensions
    4. Build record

    If target row missing → all dims marked passed=None, build record with insufficient_data
    """
    print(f"\n{'='*70}")
    print(f"ANALYZING: {symbol} (end_date={end_date})")
    print(f"{'='*70}")

    # Fetch industry peers and financial data
    print(f"\n[STEP 1] Fetching industry peers...")
    try:
        peers = data.fetch_industry_peers(symbol, end_date)
        print(f"  ✓ Found {len(peers)} peers (including target)")
        print(f"    Peers: {peers[:5]}{'...' if len(peers) > 5 else ''}")
    except Exception as e:
        print(f"  ⚠ Warning: Could not fetch peers for {symbol}: {e}")
        peers = [symbol]

    # Fetch financial data for target + peers
    print(f"\n[STEP 2] Fetching financial data (ROE, 毛利率, 经营现金流)...")
    try:
        fina_df = data.fetch_fina(peers, end_date)
        print(f"  ✓ Fetched financial data for {len(fina_df)} companies")
        print(f"  Columns: {list(fina_df.columns)}")
        print(f"\n  Financial Data Summary:")
        print(f"  {fina_df[['symbol', 'roe', 'gross_profit', 'ocf']].to_string()}")
    except Exception as e:
        print(f"  ✗ Error: Could not fetch financial data for {symbol}: {e}")
        raise

    # Extract target row
    target_fina = fina_df[fina_df["symbol"] == symbol]

    # If target missing, mark all dims as insufficient_data
    if target_fina.empty:
        print(f"  ✗ Target {symbol} not found in financial data!")
        dims = {
            "fin": {"score": 0.0, "passed": None, "veto": False, "flags": [], "sub_scores": {}},
            "comp": {"score": 0.0, "passed": None, "veto": False, "flags": [], "sub_scores": {}},
            "incentive": {"score": 0.0, "passed": None, "veto": False, "flags": [], "sub_scores": {}},
            "psych": {"score": 0.0, "passed": None, "veto": False, "flags": [], "sub_scores": {}},
            "neg": {"score": 0.0, "passed": None, "veto": False, "veto_flags": [], "flags": [], "sub_scores": {}},
        }
        return build_record(symbol, end_date or "", dims, update_time)

    target_row = target_fina.iloc[0]
    peer_fina = fina_df[fina_df["symbol"] != symbol]

    # Prepare target dict for financial and competition scoring
    target_fin_dict = {
        "roe": target_row.get("roe", 0.0),
        "gross_profit": target_row.get("gross_profit", 0.0),
        "ocf": target_row.get("ocf", 0.0),
    }

    print(f"\n  Target Data ({symbol}):")
    print(f"    ROE: {target_fin_dict['roe']}")
    print(f"    Gross Profit Rate: {target_fin_dict['gross_profit']}")
    print(f"    Operating Cash Flow: {target_fin_dict['ocf']}")

    # Score financial dimension
    print(f"\n[STEP 3] Scoring Financial Dimension...")
    dims_fin = dimensions.score_financial(target_fin_dict, peer_fina)
    print(f"  Score: {dims_fin['score']:.2f}")
    print(f"  Passed: {dims_fin['passed']}")
    print(f"  Sub-scores: {dims_fin['sub_scores']}")

    # Score competition dimension
    print(f"\n[STEP 4] Scoring Competition Dimension...")
    dims_comp = dimensions.score_competition(target_fin_dict, peer_fina)
    print(f"  Score: {dims_comp['score']:.2f}")
    print(f"  Passed: {dims_comp['passed']}")
    print(f"  Sub-scores: {dims_comp['sub_scores']}")
    if dims_comp['flags']:
        print(f"  Flags: {dims_comp['flags']}")

    # Fetch and score incentive dimension
    print(f"\n[STEP 5] Fetching & Scoring Incentive Dimension...")
    try:
        top_holders = data.fetch_top_holders(symbol, end_date)
        sh_change = data.fetch_shareholder_change(symbol, end_date)
        print(f"  ✓ Top holders: {len(top_holders)} records")
        if not top_holders.empty:
            # Print available columns that contain holder information
            cols_to_print = [col for col in ['holder_name', 'hold_ratio', 'hold_percent_total', 'hold_percent_float'] if col in top_holders.columns]
            if cols_to_print:
                print(f"    {top_holders[cols_to_print].to_string()}")
            else:
                print(f"    Top 5 holders:")
                print(f"    {top_holders.head().to_string()}")
        print(f"  ✓ Shareholder changes: {len(sh_change)} records")
        if not sh_change.empty:
            print(f"    {sh_change.to_string()}")
    except Exception as e:
        print(f"  ⚠ Warning: Could not fetch incentive data for {symbol}: {e}")
        top_holders = __import__('pandas').DataFrame()
        sh_change = __import__('pandas').DataFrame()

    dims_incentive = dimensions.score_incentive(top_holders, sh_change)
    print(f"  Score: {dims_incentive['score']:.2f}")
    print(f"  Passed: {dims_incentive['passed']}")
    print(f"  Sub-scores: {dims_incentive['sub_scores']}")

    # Fetch and score psychology dimension
    print(f"\n[STEP 6] Fetching & Scoring Psychology Dimension...")
    try:
        activity = data.fetch_investor_activity(symbol, end_date)
        print(f"  ✓ Investor activity records: {len(activity)}")
        if not activity.empty:
            print(f"    {activity.head().to_string()}")
    except Exception as e:
        print(f"  ⚠ Warning: Could not fetch investor activity for {symbol}: {e}")
        activity = __import__('pandas').DataFrame()

    dims_psych = dimensions.score_psychology(activity)
    print(f"  Score: {dims_psych['score']:.2f}")
    print(f"  Passed: {dims_psych['passed']}")
    print(f"  Sub-scores: {dims_psych['sub_scores']}")

    # Fetch and score negative dimension
    print(f"\n[STEP 7] Fetching & Scoring Negative Dimension (Veto Check)...")
    try:
        audit = data.fetch_audit(symbol, end_date)
        status = data.fetch_status_change(symbol, end_date)
        pledge = data.fetch_pledge(symbol, end_date)
        print(f"  ✓ Audit records: {len(audit)}")
        if not audit.empty:
            print(f"    {audit.to_string()}")
        print(f"  ✓ Status changes: {len(status)}")
        if not status.empty:
            print(f"    {status.to_string()}")
        print(f"  ✓ Pledge records: {len(pledge)}")
        if not pledge.empty:
            print(f"    {pledge.to_string()}")
    except Exception as e:
        print(f"  ⚠ Warning: Could not fetch negative dimension data for {symbol}: {e}")
        audit = __import__('pandas').DataFrame()
        status = __import__('pandas').DataFrame()
        pledge = __import__('pandas').DataFrame()

    dims_neg = dimensions.score_negative(audit, status, pledge, sh_change)
    print(f"  Score: {dims_neg['score']:.2f}")
    print(f"  Passed: {dims_neg['passed']}")
    print(f"  Veto: {dims_neg['veto']}")
    if dims_neg['veto_flags']:
        print(f"  Veto Flags: {dims_neg['veto_flags']}")
    print(f"  Sub-scores: {dims_neg['sub_scores']}")

    # Assemble dims dict
    dims = {
        "fin": dims_fin,
        "comp": dims_comp,
        "incentive": dims_incentive,
        "psych": dims_psych,
        "neg": dims_neg,
    }

    # Build and return record
    trade_date = end_date or ""
    print(f"\n[STEP 8] Cross-validating & Building Final Record...")
    record = build_record(symbol, trade_date, dims, update_time)
    print(f"  Verdict: {record['verdict']}")
    print(f"  High Confidence: {record['high_confidence']}")
    print(f"  Radar Scores: {record['radar_scores']}")

    return record


def main() -> None:
    """
    CLI entry point for symbol analysis.

    Args:
        --symbol: Comma-separated list of symbols (e.g., "000001.SZ,600000.SH")
        --industry: L2 industry code (alternative to --symbol)
        --end-date: Optional analysis date (YYYY-MM-DD or YYYYMMDD)

    Flow:
    1. data.init() first
    2. For each symbol: analyze_symbol(), write per-symbol JSON, render radar PNG
    3. Collect high_confidence records
    4. Write high_confidence_list.csv if any
    5. Print summary
    """
    parser = argparse.ArgumentParser(
        description="Analyze stocks using Munger 5-dimension mental model"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        help="Comma-separated list of stock symbols (e.g., 000001.SZ,600000.SH)",
    )
    parser.add_argument(
        "--industry",
        type=str,
        help="L2 industry code (e.g., L2004001 for banks)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="Analysis date in YYYY-MM-DD or YYYYMMDD format (default: today)",
    )

    args = parser.parse_args()

    # Determine symbols to analyze
    if args.symbol:
        symbols = [s.strip() for s in args.symbol.split(",")]
    elif args.industry:
        symbols = data.fetch_industry_peers_by_code(args.industry)
    else:
        parser.error("Either --symbol or --industry is required")
        return

    # Initialize panda_data session
    print("Initializing panda_data session...")
    data.init()

    # Get current time for update_time field
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Analyze each symbol
    high_confidence_records = []
    results = []

    for symbol in symbols:
        print(f"Analyzing {symbol}...")
        try:
            record = analyze_symbol(symbol, args.end_date, update_time)
            results.append(record)

            if record["high_confidence"]:
                high_confidence_records.append(record)

            # Write per-symbol JSON report to production directory only
            import os
            # Get the absolute path to production directory
            script_dir = Path(__file__).parent.parent  # From scripts/ to munger-mental-model/
            prod_dir = script_dir / ".." / "munger-mental-model-production"
            prod_dir = prod_dir.resolve()  # Resolve to absolute path
            prod_dir.mkdir(parents=True, exist_ok=True)
            report_path = prod_dir / f"report_{symbol}.json"
            with open(report_path, "w") as f:
                json.dump(record, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
            print(f"  ✓ Wrote {report_path}")

            # Render radar chart (stub)
            radar_path = f"radar_{symbol}.png"
            _render_radar(symbol, record["radar_scores"], radar_path)

            # Print verdict
            verdict = record["verdict"]
            confidence = "HIGH" if record["high_confidence"] else "LOW"
            print(f"  Verdict: {verdict} ({confidence} confidence)")

        except Exception as e:
            print(f"  Error: {e}")
            continue

    # Write high_confidence_list.csv if any records
    if high_confidence_records:
        import csv
        csv_path = "high_confidence_list.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["symbol", "verdict", "fin", "comp", "incentive", "psych", "neg"],
            )
            writer.writeheader()
            for rec in high_confidence_records:
                writer.writerow({
                    "symbol": rec["symbol"],
                    "verdict": rec["verdict"],
                    "fin": rec["dim_scores"]["fin"],
                    "comp": rec["dim_scores"]["comp"],
                    "incentive": rec["dim_scores"]["incentive"],
                    "psych": rec["dim_scores"]["psych"],
                    "neg": rec["dim_scores"]["neg"],
                })
        print(f"\n✓ Wrote {csv_path} with {len(high_confidence_records)} high-confidence records")

    # Print summary
    total = len(results)
    high_conf = len(high_confidence_records)
    print(f"\nSummary: {total} analyzed, {high_conf} high-confidence")


if __name__ == "__main__":
    main()
