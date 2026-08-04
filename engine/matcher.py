"""条款匹配引擎 — 规则粗筛 + LLM 语义判定"""
import re
import logging
from typing import Optional
from engine.models import StandardItem, Contract, ServiceClause, MatchResult

logger = logging.getLogger(__name__)


def rule_match(
    contract: Contract,
    standard_items: list[StandardItem],
    threshold: float = 0.9,
) -> tuple[list[MatchResult], list[tuple[Contract, StandardItem, float]]]:
    """阶段1: 规则匹配

    Returns:
        (确定结果列表, 待LLM判定项列表[(contract, standard_item, confidence)])
    """
    results: list[MatchResult] = []
    pending: list[tuple[Contract, StandardItem, float]] = []

    all_text = " ".join(clause.content for clause in contract.service_clauses)
    declared_level = _parse_declared_level(contract.service_level_declared)

    for item in standard_items:
        # 规则1: 等级推断 — 合同声明了服务等级
        if declared_level and item.level <= declared_level:
            results.append(MatchResult(
                contract_id=contract.id,
                standard_item_id=item.id,
                verdict="满足",
                evidence=f"合同声明按{declared_level}级标准执行",
                confidence=0.95,
                method="rule",
                matched_level=declared_level,
            ))
            continue

        # 规则2: 反向排除检查
        excluded = False
        for clause in contract.service_clauses:
            if _exclusion_check(clause.content, item.requirement):
                results.append(MatchResult(
                    contract_id=contract.id,
                    standard_item_id=item.id,
                    verdict="不满足",
                    evidence=clause.content,
                    confidence=0.95,
                    method="rule",
                    matched_level=0,
                ))
                excluded = True
                break
        if excluded:
            continue

        # 规则3: 数值范围比较
        num_score, num_evidence = _numeric_compare(item.requirement, all_text)
        if num_score < 0.4:  # 明确不满足
            results.append(MatchResult(
                contract_id=contract.id, standard_item_id=item.id,
                verdict="不满足", evidence=num_evidence,
                confidence=0.92, method="rule", matched_level=0,
            ))
            continue

        # 规则4: 关键词匹配
        kw_score, kw_evidence = _keyword_match(item.requirement, all_text)
        if kw_score >= threshold:
            results.append(MatchResult(
                contract_id=contract.id, standard_item_id=item.id,
                verdict="满足", evidence=kw_evidence,
                confidence=kw_score, method="rule",
                matched_level=item.level,
            ))
        elif kw_score < 0.3:
            results.append(MatchResult(
                contract_id=contract.id, standard_item_id=item.id,
                verdict="不满足", evidence="合同中未找到相关内容",
                confidence=0.90, method="rule", matched_level=0,
            ))
        else:
            # 不确定，交给 LLM
            pending.append((contract, item, kw_score))

    return results, pending


def _extract_bigrams(text: str) -> list[str]:
    """从中文文本中提取连续2字词（bigram滑动窗口）"""
    chars = re.findall(r'[一-鿿]', text)
    return [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]


def _keyword_match(requirement: str, contract_text: str) -> tuple[float, str]:
    """关键词匹配打分"""
    # 使用 bigram 滑动窗口提取2字关键词
    keywords = _extract_bigrams(requirement)
    if not keywords:
        return 0.5, ""
    hits = sum(1 for kw in keywords if kw in contract_text)
    score = hits / len(keywords)
    # 找到包含最多关键词的句子作为 evidence
    evidence = _find_best_sentence(contract_text, keywords)
    return min(score, 1.0), evidence


def _exclusion_check(clause_text: str, requirement: str) -> bool:
    """检查合同条款是否明确排除了某类服务"""
    exclusion_patterns = [
        r'不含.*{cat}', r'不包含.*{cat}', r'不提供.*{cat}',
        r'无.*{cat}服务', r'由.*自行负责.*{cat}',
    ]
    # 提取需求中的核心类别词 — 使用bigram获取可匹配的短词
    cat_keywords = _extract_bigrams(requirement)
    for kw in cat_keywords[:3]:  # 取前3个关键词检查
        for pat in exclusion_patterns:
            if re.search(pat.format(cat=kw), clause_text):
                return True
    return False


def _numeric_compare(requirement: str, contract_text: str) -> tuple[float, str]:
    """数值/频率比较"""
    freq_map = {
        "每日": 365, "每天": 365, "每周": 52, "每月": 12,
        "每季度": 4, "每季": 4, "每年": 1, "每小时": 8760,
    }
    req_freq = None
    for word, val in freq_map.items():
        if word in requirement:
            req_freq = val
            break
    if req_freq is None:
        return 0.5, ""

    # 在合同文本中找相同频率词
    for word, val in freq_map.items():
        if word in contract_text:
            if val < req_freq:  # 频率不够
                return 0.3, f"规范要求{requirement}，合同仅{word}"

            # 频率匹配 — 进一步比较数量
            req_nums = re.findall(r'(\d+)', requirement)
            contract_nums = re.findall(r'(\d+)', contract_text)
            if req_nums and contract_nums:
                req_count = int(req_nums[-1])
                contract_count = int(contract_nums[-1])
                is_minimum = any(ind in requirement for ind in
                                 ['不少于', '不低于', '至少', '以上', '超过', '≥', '>='])
                if is_minimum:
                    if contract_count < req_count:
                        return 0.3, f"合同仅{word}{contract_count}次，规范要求不少于{req_count}次"
                else:
                    if contract_count < req_count:
                        return 0.3, f"规范要求{requirement}，合同仅{word}{contract_count}次"

            return 0.95, f"合同: {word}"
    return 0.5, ""


def _level_infer(declared: Optional[str]) -> Optional[int]:
    """解析合同声明的服务等级"""
    if not declared:
        return None
    m = re.search(r'([一二三四五1-5])级', str(declared))
    if m:
        level_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
        raw = m.group(1)
        return level_map.get(raw, int(raw) if raw.isdigit() else None)
    return None


def _parse_declared_level(declared: Optional[str]) -> Optional[int]:
    """解析合同声明的服务等级（别名）"""
    return _level_infer(declared)


def _find_best_sentence(text: str, keywords: list[str]) -> str:
    """找到包含最多关键词的句子"""
    sentences = re.split(r'[。；\n]', text)
    best = ""
    best_hits = 0
    for sent in sentences:
        hits = sum(1 for kw in keywords if kw in sent)
        if hits > best_hits:
            best_hits = hits
            best = sent.strip()
    return best[:200]
