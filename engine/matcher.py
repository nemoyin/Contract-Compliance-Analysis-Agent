"""条款匹配引擎 — 规则粗筛 + LLM 语义判定"""
import re
import json as json_mod
import logging
from typing import Optional
from engine.llm import LLMProvider, LLMError
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
            # 只从频率关键词出现的邻域(±100字符)提取数字，避免误匹配费用、面积等无关数字
            idx = contract_text.find(word)
            context = contract_text[max(0, idx - 100):idx + 100]
            contract_nums = re.findall(r'(\d+)', context)
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


MATCH_BATCH_PROMPT = """你是物业合同合规审查专家。请依次判断以下<规范-合同>条款对是否满足。

{items}

判定标准：
- 满足：合同明确覆盖了规范要求的服务内容和频率
- 部分满足：覆盖了服务内容但频率/范围不足
- 不满足：合同未涉及或明确排除

请以 JSON 返回所有结果：
{{"results": [
  {{"index": 0, "verdict": "满足/部分满足/不满足", "evidence": "合同原文片段", "confidence": 0.0~1.0, "reasoning": "判定依据"}},
  ...
]}}"""


def llm_match_batch(
    pending: list[tuple[Contract, StandardItem, float]],
    provider: Optional[LLMProvider],
) -> list[MatchResult]:
    """阶段2: LLM 批量语义判定"""
    if not pending:
        return []

    if provider is None:
        return [
            MatchResult(
                contract_id=c.id, standard_item_id=s.id,
                verdict="不确定", evidence="LLM 不可用",
                confidence=0.0, method="llm", matched_level=0,
            )
            for c, s, _ in pending
        ]

    # 构建批量 Prompt
    item_lines = []
    for i, (contract, std_item, _) in enumerate(pending):
        contract_text = " ".join(cl.content for cl in contract.service_clauses[:20])
        item_lines.append(
            f"[{i}] 规范要求: {std_item.requirement}\n"
            f"    合同条款: {contract_text[:500]}"
        )
    items_text = "\n\n".join(item_lines)

    try:
        response = provider.chat([
            {"role": "user", "content": MATCH_BATCH_PROMPT.format(items=items_text)}
        ])
        result_data = json_mod.loads(_strip_markdown_code(response))
        llm_results = result_data.get("results", [])

        # 构建索引 → 结果的映射
        result_map: dict[int, dict] = {}
        for r in llm_results:
            result_map[r.get("index", -1)] = r

        results = []
        for i, (contract, std_item, _) in enumerate(pending):
            if i in result_map:
                r = result_map[i]
                results.append(MatchResult(
                    contract_id=contract.id,
                    standard_item_id=std_item.id,
                    verdict=str(r.get("verdict", "不确定")),
                    evidence=str(r.get("evidence", "")),
                    confidence=float(r.get("confidence", 0.5)),
                    method="llm",
                    matched_level=_infer_matched_level(std_item, r.get("verdict", "")),
                ))
            else:
                results.append(MatchResult(
                    contract_id=contract.id, standard_item_id=std_item.id,
                    verdict="不确定", evidence="LLM 未返回该条结果",
                    confidence=0.0, method="llm", matched_level=0,
                ))
        return results
    except (LLMError, json_mod.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM 批量判定失败: {e}")
        return [
            MatchResult(
                contract_id=c.id, standard_item_id=s.id,
                verdict="不确定", evidence=f"LLM 调用失败: {e}",
                confidence=0.0, method="llm", matched_level=0,
            )
            for c, s, _ in pending
        ]


def match_contract(
    contract: Contract,
    standard_items: list[StandardItem],
    provider: Optional[LLMProvider] = None,
    threshold: float = 0.9,
) -> list[MatchResult]:
    """完整的混合匹配流水线：规则 → LLM"""
    rule_results, pending = rule_match(contract, standard_items, threshold)
    llm_pending = [(c, s, conf) for c, s, conf in pending]
    llm_results = llm_match_batch(llm_pending, provider)
    return rule_results + llm_results


def match_all_contracts(
    contracts: list[Contract],
    standard_items: list[StandardItem],
    provider: Optional[LLMProvider] = None,
    threshold: float = 0.9,
    batch_size: int = 20,
) -> dict[str, list[MatchResult]]:
    """批量匹配所有合同，LLM 判定项跨合同合并批量调用"""
    # 第一阶段：对所有合同执行规则匹配
    all_pending: list[tuple[Contract, StandardItem, float]] = []
    all_results: dict[str, list[MatchResult]] = {}

    for contract in contracts:
        rule_results, pending = rule_match(contract, standard_items, threshold)
        all_results[contract.id] = list(rule_results)
        all_pending.extend(pending)

    logger.info(f"规则阶段完成: {sum(len(v) for v in all_results.values())} 条确定, "
                f"{len(all_pending)} 条待 LLM 判定")

    # 第二阶段：将 pending 分批送 LLM
    for i in range(0, len(all_pending), batch_size):
        batch = all_pending[i:i + batch_size]
        llm_results = llm_match_batch(batch, provider)
        # 将结果归入对应合同
        for result in llm_results:
            if result.contract_id in all_results:
                all_results[result.contract_id].append(result)

    return all_results


def _infer_matched_level(item: StandardItem, verdict: str) -> int:
    """根据判定结果推断实际达到的等级"""
    if verdict == "满足":
        return item.level
    return 0


def _strip_markdown_code(text: str) -> str:
    """去除 LLM 响应中的 markdown 代码块包裹"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
        else:
            text = "\n".join(lines[1:])
    return text
