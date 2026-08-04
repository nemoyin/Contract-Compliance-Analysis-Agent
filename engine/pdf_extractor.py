"""LLM 驱动的合同条款提取器"""
import json
import logging
from typing import Optional
from engine.pdf_parser import parse_pdf, DocumentTree
from engine.llm import LLMProvider, LLMError
from engine.models import ServiceClause

logger = logging.getLogger(__name__)

LOCATE_PROMPT = """你是一个文档结构分析专家。以下是物业合同的章节目录。请找出包含"物业服务内容和标准"的章节。

目录结构：
{toc}

请返回 JSON：
{{"service_indices": [索引号列表], "reasoning": "判断依据"}}

注意：
- 服务条款通常出现在标题含"服务""管理""标准""维护""保洁""秩序""绿化"的章节
- 不要包含"总则""双方权利义务""费用""违约责任""附则"等章节
- 索引号是 [数字] 所示编号"""

EXTRACT_PROMPT = """你是一个物业合同数据提取专家。请从以下合同的服务条款章节中，逐条提取服务内容并归类。

合同文本：
{text}

请将每条服务归类到以下七大类之一：
1. 综合管理（办公、接待、档案、报修受理等）
2. 共用部位维护（建筑物本体、走廊、大堂等公共区域维护）
3. 共用设施设备维护（电梯、消防、供水、供电、安防等设备）
4. 公共秩序维护（安保、巡逻、门禁、车辆管理等）
5. 保洁服务（清扫、垃圾处理、消杀等）
6. 绿化养护（植物修剪、浇水、补种等）
7. 其他

返回 JSON：
{{"clauses": [{{"content": "条款原文", "category": "七选一", "page": 页码}}]}}

注意：
- 逐条提取，不要合并
- content 必须是合同原文，不要改写
- 费用条款（元/月·平方米之类）不提取
- page 编号从1开始，如无法判断填1"""


def locate_service_chapters(tree: DocumentTree, provider: LLMProvider) -> list[int]:
    """LLM 定位物业服务章节，返回章节索引列表"""
    if provider is None:
        return []
    try:
        toc = tree.to_toc()
        response = provider.chat([
            {"role": "user", "content": LOCATE_PROMPT.format(toc=toc)}
        ])
        result = _parse_json(response)
        return result.get("service_indices", [])
    except (LLMError, json.JSONDecodeError) as e:
        logger.warning(f"LLM 章节定位失败: {e}")
        return []


def extract_service_clauses(text: str, provider: LLMProvider) -> list[ServiceClause]:
    """LLM 从服务章节文本中提取结构化服务条款"""
    if provider is None:
        return []
    try:
        response = provider.chat([
            {"role": "user", "content": EXTRACT_PROMPT.format(text=text)}
        ])
        result = _parse_json(response)
        clauses = []
        for item in result.get("clauses", []):
            clauses.append(ServiceClause(
                content=str(item.get("content", "")).strip(),
                category=str(item.get("category", "其他")).strip(),
                page=int(item.get("page", 1)),
            ))
        return clauses
    except (LLMError, json.JSONDecodeError) as e:
        logger.warning(f"LLM 条款提取失败: {e}")
        return []


def extract_contract_from_pdf(
    pdf_path: str, provider: Optional[LLMProvider]
) -> tuple[Optional[str], list[ServiceClause]]:
    """完整的 PDF 合同提取流水线

    Returns:
        (service_level_declared, service_clauses)
    """
    try:
        tree = parse_pdf(pdf_path)
    except (IOError, ImportError) as e:
        logger.error(f"PDF 解析失败: {pdf_path} — {e}")
        return None, []

    if provider is None:
        return None, []

    # 步骤1: 定位服务章节
    indices = locate_service_chapters(tree, provider)
    if not indices:
        logger.warning(f"未找到服务章节: {pdf_path}")

    # 步骤2: 提取目标章节文本
    target_text = tree.get_chapter_text(indices) if indices else tree.full_text

    # 步骤3: 提取服务条款
    clauses = extract_service_clauses(target_text, provider)

    return None, clauses


def _parse_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，容忍 markdown 代码块包裹"""
    text = text.strip()
    if text.startswith("```"):
        # 移除 markdown 代码块标记
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)
