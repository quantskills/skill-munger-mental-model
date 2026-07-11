"""
Dimension scoring functions for Munger mental model analysis.

Provides scorers for financial, competition, incentive, and psychology dimensions.
Each scorer returns a standardized result dict with score, passed, flags, and sub_scores.
"""

from __future__ import annotations

import pandas as pd

import config


# Standard audit opinions (no veto)
_STANDARD_OPINIONS = {"unqualified_opinion", "no_audit_performed"}

# Known reputable audit agencies (国内前20大所 + 四大本土化品牌).
# A switch TO one of these is not a red flag; a switch TO an unknown small firm is.
_REPUTABLE_AGENCIES = {
    "普华永道中天会计师事务所",
    "安永华明会计师事务所",
    "毕马威华振会计师事务所",
    "德勤华永会计师事务所",
    "立信会计师事务所",
    "天健会计师事务所",
    "信永中和会计师事务所",
    "大信会计师事务所",
    "瑞华会计师事务所",
    "致同会计师事务所",
    "天职国际会计师事务所",
    "容诚会计师事务所",
    "中审众环会计师事务所",
    "中汇会计师事务所",
    "大华会计师事务所",
    "中兴财光华会计师事务所",
    "广东正中珠江会计师事务所",
    "精诚会计师事务所",
    "中喜会计师事务所",
    "众华会计师事务所",
}


def _passed(score: float) -> bool:
    """
    Check if score meets the pass threshold.

    Args:
        score: Score value (0.0–100.0)

    Returns:
        bool: True if score >= pass_threshold(), False otherwise
    """
    return score >= config.pass_threshold()


def _median(series: pd.Series) -> float:
    """
    Compute median of a pandas Series, handling empty cases.

    Args:
        series: pandas Series of numeric values

    Returns:
        float: Median value, or 0.0 if series is empty
    """
    if series.empty:
        return 0.0
    return series.median()


def score_financial(target: dict, peers: pd.DataFrame) -> dict:
    """
    Score financial dimension: ROE, GM, OCF vs peers.

    Args:
        target: Dict with keys 'roe', 'gross_profit', 'ocf'
        peers: DataFrame with columns 'roe', 'gross_profit', 'ocf'

    Returns:
        dict with keys: score, passed, flags, sub_scores
        sub_scores contains: roe_vs_median, gm_vs_median, ocf_positive_and_vs_median

    Note: If insufficient valid data points (< 5 per metric), passed=None (insufficient_data)
    """
    # Check data validity: need at least 5 valid data points per metric
    valid_roe = peers["roe"].notna().sum()
    valid_gm = peers["gross_profit"].notna().sum()
    valid_ocf = peers["ocf"].notna().sum()

    flags = []
    if valid_roe < 5:
        flags.append("insufficient_data:roe")
    if valid_gm < 5:
        flags.append("insufficient_data:gross_profit")
    if valid_ocf < 5:
        flags.append("insufficient_data:ocf")

    # If all metrics have insufficient data, mark as insufficient_data verdict
    if len(flags) == 3:
        print(f"    [DETAIL] 财务维度详细计算:")
        print(f"      ⚠ 数据不足: ROE有效数据{valid_roe}, GM有效数据{valid_gm}, OCF有效数据{valid_ocf}")
        return {
            "score": 0.0,
            "passed": None,  # Mark as insufficient
            "flags": flags,
            "sub_scores": {},
        }

    roe_median = _median(peers["roe"])
    gm_median = _median(peers["gross_profit"])
    ocf_median = _median(peers["ocf"])

    # Handle None values: treat as 0
    roe_val = target.get("roe") or 0.0
    gm_val = target.get("gross_profit") or 0.0
    ocf_val = target.get("ocf") or 0.0

    # ROE vs median: 1 if target >= median, else 0
    roe_score = 1.0 if roe_val >= roe_median else 0.0

    # GM vs median: 1 if target >= median, else 0
    # Only count if valid data exists
    gm_score = 1.0 if (valid_gm > 0 and gm_val >= gm_median) else 0.0

    # OCF positive AND vs median: 1 if OCF > 0 AND target >= median, else 0
    ocf_score = 1.0 if (valid_ocf > 0 and ocf_val > 0 and ocf_val >= ocf_median) else 0.0

    sub_scores = {
        "roe_vs_median": roe_score,
        "gm_vs_median": gm_score,
        "ocf_positive_and_vs_median": ocf_score,
    }

    # Score is mean of sub_scores × 100
    mean_score = (roe_score + gm_score + ocf_score) / 3.0
    score = mean_score * 100.0

    print(f"    [DETAIL] 财务维度详细计算:")
    print(f"      有效数据点: ROE={valid_roe}, GM={valid_gm}, OCF={valid_ocf}")
    print(f"      同行中位数 - ROE: {roe_median:.4f}, GM: {gm_median:.4f}, OCF: {ocf_median:.4f}")
    print(f"      目标指标   - ROE: {roe_val:.4f}, GM: {gm_val:.4f}, OCF: {ocf_val:.4f}")
    print(f"      ROE vs 中位数:    {roe_val:.4f} >= {roe_median:.4f} ? {roe_score} ✓" if roe_score else f"      ROE vs 中位数:    {roe_val:.4f} >= {roe_median:.4f} ? {roe_score} ✗")
    print(f"      GM vs 中位数:     {gm_val:.4f} >= {gm_median:.4f} ? {gm_score} ✓" if gm_score else f"      GM vs 中位数:     {gm_val:.4f} >= {gm_median:.4f} ? {gm_score} ✗" + (f" (仅{valid_gm}个有效数据)" if valid_gm > 0 else " (无有效数据)"))
    print(f"      OCF (正数且>中位数): {ocf_val:.4f} > 0 AND {ocf_val:.4f} >= {ocf_median:.4f} ? {ocf_score} ✓" if ocf_score else f"      OCF (正数且>中位数): {ocf_val:.4f} > 0 AND {ocf_val:.4f} >= {ocf_median:.4f} ? {ocf_score} ✗" + (f" (仅{valid_ocf}个有效数据)" if valid_ocf > 0 else " (无有效数据)"))
    print(f"      平均分: ({roe_score} + {gm_score} + {ocf_score}) / 3 = {mean_score:.4f}")
    print(f"      最终分数: {mean_score:.4f} × 100 = {score:.2f}")
    if flags:
        print(f"      ⚠ 数据质量标记: {flags}")

    return {
        "score": score,
        "passed": _passed(score),
        "flags": flags,
        "sub_scores": sub_scores,
    }


def score_competition(target: dict, peers: pd.DataFrame) -> dict:
    """
    Score competition dimension: ROE/GM percentile + concentration bonus.

    Args:
        target: Dict with keys 'roe', 'gross_profit'
        peers: DataFrame with columns 'roe', 'gross_profit'

    Returns:
        dict with keys: score, passed, flags, sub_scores
        Includes low_confidence flag if < 3 peers or insufficient valid data
    """
    flags = []

    # Check low confidence: fewer than 3 peers
    if len(peers) < 3:
        flags.append("low_confidence:few_peers")

    # Check data validity: need at least 5 valid data points per metric
    valid_roe = peers["roe"].notna().sum()
    valid_gm = peers["gross_profit"].notna().sum()

    if valid_roe < 5:
        flags.append("insufficient_data:roe")
    if valid_gm < 5:
        flags.append("insufficient_data:gross_profit")

    # If we don't have enough ROE data for meaningful percentile, mark as insufficient
    if valid_roe < 5 and valid_gm < 5:
        print(f"    [DETAIL] 竞争力维度详细计算:")
        print(f"      ⚠ 数据不足: ROE有效数据{valid_roe}, GM有效数据{valid_gm}")
        return {
            "score": 0.0,
            "passed": None,  # Mark as insufficient
            "flags": flags,
            "sub_scores": {},
        }

    # Handle None values: treat as 0
    roe_val = target.get("roe") or 0.0
    gm_val = target.get("gross_profit") or 0.0

    # ROE percentile (40%): only count valid data points
    roe_percentile = 0.0
    if valid_roe > 0:
        valid_peers_roe = peers["roe"].dropna()
        roe_percentile = (valid_peers_roe < roe_val).sum() / len(valid_peers_roe) * 100.0

    # GM percentile (40%): only count valid data points
    gm_percentile = 0.0
    if valid_gm > 0:
        valid_peers_gm = peers["gross_profit"].dropna()
        gm_percentile = (valid_peers_gm < gm_val).sum() / len(valid_peers_gm) * 100.0

    # Concentration bonus: up to 20 (always 0 in this simple implementation)
    concentration_bonus = 0.0

    # Weighted score
    score = (roe_percentile * 0.4) + (gm_percentile * 0.4) + concentration_bonus
    score = min(100.0, max(0.0, score))  # Clamp to 0-100

    sub_scores = {
        "roe_percentile": roe_percentile,
        "gm_percentile": gm_percentile,
        "concentration_bonus": concentration_bonus,
    }

    print(f"    [DETAIL] 竞争力维度详细计算:")
    print(f"      同行数量: {len(peers)}")
    print(f"      有效数据点: ROE={valid_roe}, GM={valid_gm}")
    if len(peers) < 3:
        print(f"      ⚠ 警告: 同行少于3家，信心度降低")
    print(f"      ROE百分位: {valid_roe}个有效数据中排名前 {(peers['roe'].dropna() < roe_val).sum() if valid_roe > 0 else 0} = {roe_percentile:.2f}%")
    print(f"      GM百分位:  {valid_gm}个有效数据中排名前 {(peers['gross_profit'].dropna() < gm_val).sum() if valid_gm > 0 else 0} = {gm_percentile:.2f}%")
    print(f"      集中度加分: {concentration_bonus:.2f}")
    print(f"      加权分数: {roe_percentile:.2f} × 0.4 + {gm_percentile:.2f} × 0.4 + {concentration_bonus:.2f} = {score:.2f}")
    if flags:
        print(f"      ⚠ 标记: {flags}")

    return {
        "score": score,
        "passed": _passed(score) if "insufficient_data" not in str(flags) else None,
        "flags": flags,
        "sub_scores": sub_scores,
    }


def score_incentive(top_holders: pd.DataFrame, sh_change: pd.DataFrame) -> dict:
    """
    Score incentive dimension: concentration + pledge/freeze penalty + exec trades.

    Args:
        top_holders: DataFrame with columns 'holder_name', 'hold_ratio'
        sh_change: DataFrame with columns 'nature', 'net_change', 'pledge_ratio', 'freeze_ratio'

    Returns:
        dict with keys: score, passed, flags, sub_scores
        Always appends 'related_party: data_unavailable' flag
    """
    # Concentration: top 10 holders' total ratio (0-1)
    # API returns hold_percent_total (%) instead of hold_ratio (0-1)
    concentration = 0.0
    if not top_holders.empty:
        if "hold_ratio" in top_holders.columns:
            concentration = top_holders["hold_ratio"].sum()
        elif "hold_percent_total" in top_holders.columns:
            # hold_percent_total is in %, convert to ratio (0-1)
            concentration = top_holders["hold_percent_total"].sum() / 100.0
        elif "hold_percent_float" in top_holders.columns:
            # Fallback to float ratio
            concentration = top_holders["hold_percent_float"].sum() / 100.0
    concentration = min(1.0, concentration)  # Clamp to 1.0

    # Sweet spot 30–70%: full score; outside → linear falloff
    if 0.30 <= concentration <= 0.70:
        concentration_score = 100.0
    else:
        # Linear falloff from 0.30 and 0.70
        if concentration < 0.30:
            concentration_score = (concentration / 0.30) * 100.0
        else:  # concentration > 0.70
            concentration_score = ((1.0 - concentration) / 0.30) * 100.0
        concentration_score = max(0.0, concentration_score)

    # Pledge/freeze penalty: -20 if any pledge or freeze > 0
    pledge_freeze_penalty = 0.0
    if not sh_change.empty:
        has_pledge = "pledge_ratio" in sh_change.columns and (sh_change["pledge_ratio"] > 0).any()
        has_freeze = "freeze_ratio" in sh_change.columns and (sh_change["freeze_ratio"] > 0).any()
        if has_pledge or has_freeze:
            pledge_freeze_penalty = -20.0

    # Executive buy/sell: +10 for net buy, -10 for net sell
    exec_trade_score = 0.0
    if not sh_change.empty and "nature" in sh_change.columns and "net_change" in sh_change.columns:
        mgmt_change = sh_change[sh_change["nature"] == "管理层"]["net_change"].sum() if len(sh_change[sh_change["nature"] == "管理层"]) > 0 else 0
        if mgmt_change > 0:
            exec_trade_score = 10.0
        elif mgmt_change < 0:
            exec_trade_score = -10.0

    score = concentration_score + pledge_freeze_penalty + exec_trade_score
    score = max(0.0, min(100.0, score))  # Clamp to 0-100

    sub_scores = {
        "concentration": concentration,
        "concentration_score": concentration_score,
        "pledge_freeze_penalty": pledge_freeze_penalty,
        "exec_trade_score": exec_trade_score,
    }

    flags = ["related_party: data_unavailable"]

    print(f"    [DETAIL] 激励机制维度详细计算:")
    print(f"      前十大股东持股比例: {concentration:.4f} ({concentration*100:.2f}%)")
    if 0.30 <= concentration <= 0.70:
        print(f"      ✓ 处于甜蜜区间 [30%-70%] → 集中度得分: {concentration_score:.2f}")
    else:
        if concentration < 0.30:
            print(f"      ✗ 集中度过低 < 30% → 线性衰减")
        else:
            print(f"      ✗ 集中度过高 > 70% → 线性衰减")
        print(f"        集中度得分: {concentration_score:.2f}")

    # Detailed pledge/freeze penalty status
    pledge_freeze_detail = "无质押/冻结"
    if not sh_change.empty:
        has_pledge = "pledge_ratio" in sh_change.columns and (sh_change["pledge_ratio"] > 0).any()
        has_freeze = "freeze_ratio" in sh_change.columns and (sh_change["freeze_ratio"] > 0).any()
        if has_pledge or has_freeze:
            pledge_freeze_detail = "存在质押/冻结"

    print(f"      股权质押/冻结处罚: {pledge_freeze_penalty:.2f}" + (" ⚠ " + pledge_freeze_detail if pledge_freeze_penalty < 0 else " ✓ " + pledge_freeze_detail))

    # Detailed exec trade status
    exec_trade_detail = "无管理层交易"
    if not sh_change.empty and "nature" in sh_change.columns and "net_change" in sh_change.columns:
        mgmt_rows = sh_change[sh_change["nature"] == "管理层"]
        if not mgmt_rows.empty:
            mgmt_change = mgmt_rows["net_change"].sum() if len(mgmt_rows) > 0 else 0
            if mgmt_change > 0:
                exec_trade_detail = "管理层增持"
            elif mgmt_change < 0:
                exec_trade_detail = "管理层减持"

    print(f"      管理层增减持: {exec_trade_score:.2f}" + (" ✓ " + exec_trade_detail if exec_trade_score > 0 else " ✗ " + exec_trade_detail if exec_trade_score < 0 else " - " + exec_trade_detail))
    print(f"      总分: {concentration_score:.2f} + {pledge_freeze_penalty:.2f} + {exec_trade_score:.2f} = {score:.2f}")

    return {
        "score": score,
        "passed": _passed(score),
        "flags": flags,
        "sub_scores": sub_scores,
    }


def score_psychology(activity: pd.DataFrame) -> dict:
    """
    Score psychology dimension: meeting count + distinct institutes.

    Args:
        activity: DataFrame with columns 'activity_date', 'num_investors', 'num_institutes'

    Returns:
        dict with keys: score, passed, flags, sub_scores
        Score = (meeting_count / 12 × 50) + (institute_count / 12 × 50), capped 0–100
        Always appends 'qa_sentiment: not_available' flag

    Note: The base formula is updated to use more reasonable thresholds:
    - meeting_count: 60 meetings/year for 50 points (1 per week)
    - institute_count: 60 unique institutes/year for 50 points
    """
    if activity.empty:
        print(f"    [DETAIL] 心理学维度详细计算:")
        print(f"      ⚠ 无投资者活动记录")
        return {
            "score": 0.0,
            "passed": _passed(0.0),
            "flags": ["qa_sentiment: not_available"],
            "sub_scores": {
                "meeting_count": 0,
                "institute_count": 0,
                "meeting_score": 0.0,
                "institute_score": 0.0,
            },
        }

    # Count distinct activity dates (meetings) and distinct institutes
    meeting_count = len(activity)
    # API returns one row per institute per meeting; count distinct non-null institutes
    institute_count = 0
    if "institute" in activity.columns:
        institute_count = activity["institute"].dropna().nunique()
    elif "investor_or_analyst_detail" in activity.columns:
        # Some API versions provide investor/analyst names; count distinct
        institute_count = activity["investor_or_analyst_detail"].dropna().nunique()
    elif "participant" in activity.columns:
        institute_count = activity["participant"].dropna().nunique()
    elif "num_institutes" in activity.columns:
        institute_count = int(activity["num_institutes"].sum())
    elif "num_investors" in activity.columns:
        institute_count = int(activity["num_investors"].sum())

    # IMPROVED FORMULA: Use more reasonable thresholds
    # Old formula: meeting_count / 12 × 50 (满分需要12次调研，显然太低)
    # New formula: Use 60 as the base (1 meeting per week × 52 weeks ≈ 52-60/year)
    # Score = min(meeting_count / 60, 1.0) × 50 + min(institute_count / 60, 1.0) × 50

    meeting_score = min(meeting_count / 60.0, 1.0) * 50.0
    institute_score = min(institute_count / 60.0, 1.0) * 50.0

    score = meeting_score + institute_score
    score = max(0.0, min(100.0, score))  # Clamp to 0-100

    sub_scores = {
        "meeting_count": meeting_count,
        "institute_count": institute_count,
        "meeting_score": meeting_score,
        "institute_score": institute_score,
    }

    flags = ["qa_sentiment: not_available"]

    print(f"    [DETAIL] 心理学维度详细计算:")
    print(f"      调研会议次数: {meeting_count}")
    print(f"      参与机构数: {institute_count}")
    print(f"      调研得分: min({meeting_count} / 60, 1.0) × 50 = {meeting_score:.2f}")
    print(f"      机构得分: min({institute_count} / 60, 1.0) × 50 = {institute_score:.2f}")
    print(f"      总分: {meeting_score:.2f} + {institute_score:.2f} = {score:.2f}")
    print(f"      说明: 基准为60次/年(周频活跃)，超过基准按100分计")

    return {
        "score": score,
        "passed": _passed(score),
        "flags": flags,
        "sub_scores": sub_scores,
    }


def score_negative(audit: pd.DataFrame, status: pd.DataFrame, pledge: pd.DataFrame, sh_change: pd.DataFrame) -> dict:
    """
    Score negative dimension: audit opinion, status, pledge, shareholder changes.

    One-vote veto: ANY of these conditions triggers veto (score=0, passed=False, veto=True):
    - Latest audit opinion not in standard opinions
    - Multiple distinct audit agencies (agency switch)
    - Any status row (ST or delisting)
    - Max pledge_ratio > config.pledge_max()
    - Controlling shareholder 减持 with ratio_up_limit > 0.02

    Args:
        audit: DataFrame with columns 'opinion', 'audit_agency', 'audit_date'
        status: DataFrame with columns 'status', 'change_date'
        pledge: DataFrame with column 'pledge_ratio'
        sh_change: DataFrame with columns 'holder_type', 'ratio_up_limit'

    Returns:
        dict with keys: score, passed, veto, veto_flags, flags, sub_scores
        - score: 0.0 if any veto condition, else 100.0
        - passed: False if veto, else True
        - veto: True if any condition triggered, else False
        - veto_flags: list of triggered veto reasons
        - flags: list of data markers (e.g., hostile_takeover marker)
        - sub_scores: {"veto_count": len(veto_flags)}
    """
    veto_flags = []
    flags = []

    print(f"    [DETAIL] 负面因素维度详细计算 (一票否决制):")

    # Check 1: Latest audit opinion not in standard opinions
    print(f"      检查1: 审计意见是否为标准意见...")
    if not audit.empty:
        latest_audit = audit.iloc[0]  # Assume sorted by date, most recent first
        opinion = latest_audit["opinion"]
        if opinion not in _STANDARD_OPINIONS:
            veto_flags.append(f"nonstandard_audit:{opinion}")
            print(f"        ✗ 非标准审计意见: {opinion} → 一票否决")
        else:
            print(f"        ✓ 标准审计意见: {opinion}")
    else:
        print(f"        ⚠ 无审计数据")

    # Check 2: Suspicious audit agency switch within recent 3 years.
    # Normal regulatory rotation is NOT a red flag. We only veto if BOTH:
    #   (a) a switch occurred in the last 3 annual reports, AND
    #   (b) the new agency is NOT in the known-reputable list OR
    #       the opinion changed to non-standard after the switch.
    print(f"      检查2: 近3年是否发生可疑审计师变更...")
    agency_col = None
    if not audit.empty and "agency" in audit.columns:
        agency_col = "agency"
    elif not audit.empty and "audit_agency" in audit.columns:
        agency_col = "audit_agency"

    if agency_col:
        annual = (
            audit[
                audit["quarter"].str.endswith("q4") &
                audit[agency_col].notna()
            ]
            .sort_values("date")
            .copy()
        )
        recent3 = annual.tail(3)
        recent_agencies = recent3[agency_col].dropna().unique()
        switched_recently = len(recent_agencies) > 1

        if switched_recently:
            # Check (b1): new agency is unknown/small
            latest_agency = recent3.iloc[-1][agency_col]
            is_reputable = any(
                known in latest_agency for known in _REPUTABLE_AGENCIES
            )
            # Check (b2): non-standard opinion appeared after the switch
            switch_date = None
            for i in range(1, len(recent3)):
                if recent3.iloc[i][agency_col] != recent3.iloc[i - 1][agency_col]:
                    switch_date = recent3.iloc[i]["date"]
                    break
            opinion_degraded = False
            if switch_date is not None:
                post_switch = audit[audit["date"] >= switch_date]
                opinion_degraded = post_switch["opinion"].notna().any() and (
                    ~post_switch["opinion"].isin(_STANDARD_OPINIONS)
                ).any()

            if not is_reputable:
                veto_flags.append("agency_switch_to_unknown")
                print(f"        ✗ 近3年换所 → 新事务所 '{latest_agency}' 非知名大所 → 一票否决")
            elif opinion_degraded:
                veto_flags.append("agency_switch_with_opinion_change")
                print(f"        ✗ 近3年换所 → 换所后出现非标意见 → 一票否决")
            else:
                # Normal switch within reputable agencies - still flag it for visibility
                veto_flags.append("agency_switch")
                print(f"        ✓ 近3年换所但属正常轮换: {list(recent_agencies)} (均为知名大所且意见标准)")
        else:
            all_agencies = annual[agency_col].dropna().unique()
            if len(all_agencies) > 1:
                print(f"        ✓ 近3年审计师稳定: {list(recent_agencies)} (历史曾换所属正常轮换)")
            else:
                print(f"        ✓ 审计师从未变更: {list(recent_agencies)}")
    else:
        print(f"        ⚠ 无审计师数据")

    # Check 3: Any status row (ST or delisting)
    print(f"      检查3: 是否存在ST/退市状态...")
    if not status.empty:
        veto_flags.append("status_change:ST_or_delisting")
        print(f"        ✗ 发现ST/退市记录 → 一票否决")
    else:
        print(f"        ✓ 无ST/退市状态")

    # Check 4: Max pledge_ratio > pledge_max()
    print(f"      检查4: 股权质押比例是否过高...")
    if not pledge.empty and "pledge_ratio" in pledge.columns:
        max_pledge = pledge["pledge_ratio"].max()
        if max_pledge > config.pledge_max():
            veto_flags.append("high_pledge")
            print(f"        ✗ 最高质押比例: {max_pledge:.4f} > {config.pledge_max():.4f} → 一票否决")
        else:
            print(f"        ✓ 最高质押比例: {max_pledge:.4f} <= {config.pledge_max():.4f}")
    else:
        print(f"        ⚠ 无质押数据")

    # Check 5: Controlling shareholder 减持 with ratio_up_limit > 0.02
    print(f"      检查5: 大股东是否大额减持...")
    if not sh_change.empty and "holder_type" in sh_change.columns and "ratio_up_limit" in sh_change.columns:
        controlling = sh_change[sh_change["holder_type"] == "controlling"]
        if not controlling.empty:
            for _, row in controlling.iterrows():
                if row["ratio_up_limit"] > 0.02:
                    veto_flags.append("large_controlling_sell")
                    flags.append("hostile_takeover: weak_proxy")
                    print(f"        ✗ 大股东减持比例: {row['ratio_up_limit']:.4f} > 0.02 → 一票否决")
                    break
            if "large_controlling_sell" not in veto_flags:
                print(f"        ✓ 大股东减持比例正常")
        else:
            print(f"        ⚠ 无大股东减持数据")
    else:
        print(f"        ⚠ 无股东变化数据")

    # Determine veto status
    veto = len(veto_flags) > 0

    # Set score and passed
    score = 0.0 if veto else 100.0
    passed = False if veto else True

    print(f"      一票否决总数: {len(veto_flags)}")
    if veto_flags:
        print(f"      一票否决原因: {veto_flags}")
    print(f"      最终分数: {score:.2f} (veto={veto})")

    return {
        "score": score,
        "passed": passed,
        "veto": veto,
        "veto_flags": veto_flags,
        "flags": flags,
        "sub_scores": {"veto_count": len(veto_flags)},
    }
