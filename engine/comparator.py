"""三个分析模块的核心逻辑"""
import math
import logging
from typing import Optional, Any
from collections import defaultdict
from engine.models import (
    StandardItem, Contract, MatchResult, ComplianceReport,
    ComparisonResult, ClusterResult, QualityGroup, PriceOutlier,
)
from engine.llm import LLMProvider, LLMError

logger = logging.getLogger(__name__)

CATEGORIES = [
    "综合管理", "共用部位维护", "共用设施设备维护",
    "公共秩序维护", "保洁服务", "绿化养护", "其他",
]


def calc_compliance_rate(
    contract_id: str,
    results: list[MatchResult],
    standards: list[StandardItem],
) -> ComplianceReport:
    """计算单个合同的规范满足率"""
    total = len(results)
    satisfied = sum(1 for r in results if r.verdict == "满足")
    total_rate = satisfied / total if total > 0 else 0.0

    # 按等级分组
    level_items = defaultdict(lambda: {"total": 0, "satisfied": 0})
    for r, s in zip(results, standards):
        lv = s.level
        level_items[lv]["total"] += 1
        if r.verdict == "满足":
            level_items[lv]["satisfied"] += 1

    level_rates = {}
    for lv in sorted(level_items):
        d = level_items[lv]
        level_rates[lv] = d["satisfied"] / d["total"] if d["total"] > 0 else 0.0

    # 按大类分组
    cat_items = defaultdict(lambda: {"total": 0, "satisfied": 0})
    for r, s in zip(results, standards):
        cat = s.category
        cat_items[cat]["total"] += 1
        if r.verdict == "满足":
            cat_items[cat]["satisfied"] += 1

    category_rates = {}
    for cat in CATEGORIES:
        if cat in cat_items:
            d = cat_items[cat]
            category_rates[cat] = d["satisfied"] / d["total"] if d["total"] > 0 else 0.0
        else:
            category_rates[cat] = 0.0

    return ComplianceReport(
        contract_id=contract_id,
        total_rate=total_rate,
        level_rates=level_rates,
        category_rates=category_rates,
        matched_count=satisfied,
        total_count=total,
        details=list(results),
    )


def compare_two(
    contract_a: Contract,
    contract_b: Contract,
    fee_type: str,
    results: dict[str, list[MatchResult]],
    standards: list[StandardItem],
    config: dict[str, Any],
    provider: Optional[LLMProvider] = None,
) -> ComparisonResult:
    """同价不同质：两个合同的全维度对比"""
    a_results = results.get(contract_a.id, [])
    b_results = results.get(contract_b.id, [])
    a_report = calc_compliance_rate(contract_a.id, a_results, standards)
    b_report = calc_compliance_rate(contract_b.id, b_results, standards)

    # 差异条款
    a_only = []
    b_only = []
    both_missing = []
    for ra, rb, s in zip(a_results, b_results, standards):
        if ra.verdict == "满足" and rb.verdict != "满足":
            a_only.append(ra)
        elif rb.verdict == "满足" and ra.verdict != "满足":
            b_only.append(rb)
        elif ra.verdict != "满足" and rb.verdict != "满足":
            both_missing.append(ra)

    # LLM 生成总结
    summary = _generate_comparison_summary(
        contract_a, contract_b, a_report, b_report, a_only, b_only, provider
    )

    return ComparisonResult(
        contract_a=contract_a,
        contract_b=contract_b,
        fee_type=fee_type,
        a_report=a_report,
        b_report=b_report,
        a_only_items=a_only,
        b_only_items=b_only,
        both_missing=both_missing,
        summary=summary,
    )


def cluster_and_detect(
    contracts: list[Contract],
    results: dict[str, list[MatchResult]],
    standards: list[StandardItem],
    fee_type: str,
    config: dict[str, Any],
) -> ClusterResult:
    """同质不同价：聚类 + 价格异常检测"""
    similarity_threshold = config.get("quality_similarity", 0.95)
    outlier_std = config.get("price_outlier_std", 1.5)

    # 构建满足度向量
    vectors = {}
    reports = {}
    for c in contracts:
        r = results.get(c.id, [])
        vec = _build_satisfaction_vector(c.id, r, standards)
        vectors[c.id] = vec
        reports[c.id] = calc_compliance_rate(c.id, r, standards)

    # 简单聚类：贪婪分组
    visited: set[str] = set()
    groups: list[QualityGroup] = []
    contract_ids = [c.id for c in contracts]

    for cid in contract_ids:
        if cid in visited:
            continue
        group_members = [cid]
        visited.add(cid)
        for other in contract_ids:
            if other in visited:
                continue
            sim = _cosine_similarity(vectors[cid], vectors[other])
            if sim >= similarity_threshold:
                group_members.append(other)
                visited.add(other)
        groups.append(_build_quality_group(group_members, contracts, reports, fee_type))

    # 价格异常检测
    outliers = _detect_outliers(groups, contracts, fee_type, outlier_std)

    return ClusterResult(fee_type=fee_type, groups=groups, outliers=outliers)


def _build_satisfaction_vector(
    contract_id: str,
    results: list[MatchResult],
    standards: list[StandardItem],
) -> list[float]:
    """构建 13 维满足度向量: [总满足率, L1~L5, 7大类]"""
    report = calc_compliance_rate(contract_id, results, standards)
    vec = [report.total_rate]
    for lv in range(1, 6):
        vec.append(report.level_rates.get(lv, 0.0))
    for cat in CATEGORIES:
        vec.append(report.category_rates.get(cat, 0.0))
    return vec


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """余弦相似度"""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _build_quality_group(
    member_ids: list[str],
    contracts: list[Contract],
    reports: dict[str, ComplianceReport],
    fee_type: str,
) -> QualityGroup:
    """构建同质组对象"""
    fee_map = {
        "residential": lambda c: c.residential_fee,
        "commercial": lambda c: c.commercial_fee,
        "parking": lambda c: c.parking_fee,
    }
    get_fee = fee_map.get(fee_type, lambda c: c.residential_fee)

    members = [c for c in contracts if c.id in member_ids]
    fees = [get_fee(c) for c in members]
    avg_fee = sum(fees) / len(fees) if fees else 0.0
    avg_sat = sum(reports[cid].total_rate for cid in member_ids) / len(member_ids) if member_ids else 0.0

    if len(fees) > 1:
        variance = sum((f - avg_fee) ** 2 for f in fees) / (len(fees) - 1)
        price_std = math.sqrt(variance)
    else:
        price_std = 0.0

    return QualityGroup(
        group_id=len(member_ids),  # placeholder, will be numbered later
        contract_ids=member_ids,
        avg_satisfaction=avg_sat,
        avg_price=avg_fee,
        price_std=price_std,
    )


def _detect_outliers(
    groups: list[QualityGroup],
    contracts: list[Contract],
    fee_type: str,
    outlier_std: float,
) -> list[PriceOutlier]:
    """检测价格异常点"""
    fee_map = {
        "residential": lambda c: c.residential_fee,
        "commercial": lambda c: c.commercial_fee,
        "parking": lambda c: c.parking_fee,
    }
    get_fee = fee_map.get(fee_type, lambda c: c.residential_fee)
    contract_map = {c.id: c for c in contracts}

    outliers = []
    for group in groups:
        if len(group.contract_ids) < 2:
            continue
        for cid in group.contract_ids:
            c = contract_map.get(cid)
            if c is None:
                continue
            fee = get_fee(c)
            if group.price_std > 0:
                deviation = abs(fee - group.avg_price) / group.price_std
                if deviation >= outlier_std:
                    deviation_pct = ((fee - group.avg_price) / group.avg_price) * 100
                    outliers.append(PriceOutlier(
                        contract_id=cid,
                        property_name=c.property_name,
                        fee=fee,
                        group_id=group.group_id,
                        group_avg_fee=group.avg_price,
                        deviation_pct=round(deviation_pct, 1),
                    ))
    return outliers


SUMMARY_PROMPT = """你是一个物业合同分析专家。请基于以下两个合同的对比数据，生成一段简洁的分析总结（200字以内）。

合同A: {name_a}，费用: {fee_a}元/月·㎡，满足率: {rate_a}%
合同B: {name_b}，费用: {fee_b}元/月·㎡，满足率: {rate_b}%

合同A独有满足的条款数: {a_only_count}
合同B独有满足的条款数: {b_only_count}
双方都不满足的条款数: {both_missing_count}

请用自然语言总结两个合同的服务差异，重点指出哪个性价比更高。"""


def _generate_comparison_summary(
    contract_a: Contract, contract_b: Contract,
    a_report: ComplianceReport, b_report: ComplianceReport,
    a_only: list[MatchResult], b_only: list[MatchResult],
    provider: Optional[LLMProvider],
) -> str:
    """LLM 生成对比总结"""
    if provider is None:
        return _fallback_summary(contract_a, contract_b, a_report, b_report, a_only, b_only)
    try:
        prompt = SUMMARY_PROMPT.format(
            name_a=contract_a.property_name, fee_a=contract_a.residential_fee,
            rate_a=round(a_report.total_rate * 100, 1),
            name_b=contract_b.property_name, fee_b=contract_b.residential_fee,
            rate_b=round(b_report.total_rate * 100, 1),
            a_only_count=len(a_only), b_only_count=len(b_only),
            both_missing_count=len(a_report.details) - a_report.matched_count,
        )
        return provider.chat([{"role": "user", "content": prompt}])
    except LLMError:
        return _fallback_summary(contract_a, contract_b, a_report, b_report, a_only, b_only)


def _fallback_summary(
    contract_a: Contract, contract_b: Contract,
    a_report: ComplianceReport, b_report: ComplianceReport,
    a_only: list[MatchResult], b_only: list[MatchResult],
) -> str:
    """无 LLM 时的规则总结"""
    a_rate = round(a_report.total_rate * 100, 1)
    b_rate = round(b_report.total_rate * 100, 1)
    if a_rate > b_rate:
        better = contract_a.property_name
    elif b_rate > a_rate:
        better = contract_b.property_name
    else:
        better = "两者"
    return (
        f"{contract_a.property_name} 满足率 {a_rate}%，"
        f"{contract_b.property_name} 满足率 {b_rate}%。"
        f"合同A独有 {len(a_only)} 项满足，合同B独有 {len(b_only)} 项满足。"
        f"综合来看，{better}的性价比更高。"
    )
