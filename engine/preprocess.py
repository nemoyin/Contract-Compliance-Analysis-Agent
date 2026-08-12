"""预处理流水线：PDF 解析 → 合同提取 → 匹配引擎 → 缓存写入"""
import os
import re
import logging
from typing import Callable, Optional
from engine.loader import load_standards, load_contracts_meta
from engine.llm import create_provider
from engine.models import MatchResult
from engine.pdf_extractor import extract_contract_from_pdf
from engine.matcher import rule_match, llm_match_batch
from engine.cache import CacheManager
from engine.pdf_parser import OCR_MIN_TEXT_LENGTH

logger = logging.getLogger(__name__)

# 进度回调类型: (step: str, message: str) -> None
ProgressCallback = Callable[[str, str], None]


def _check_if_ocr_needed(pdf_path: str) -> bool:
    """快速检测 PDF 是否需要 OCR（扫描件/图片型）"""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            sample = "".join(
                (page.extract_text() or "") for page in pdf.pages[:3]
            )
        usable = len(re.sub(r"\s", "", sample))
        return usable < OCR_MIN_TEXT_LENGTH
    except Exception:
        return False


def run_preprocessing(
    data_dir: str,
    config: dict,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    """执行完整预处理流水线

    Args:
        data_dir: 数据目录路径
        config: 完整配置字典
        on_progress: 可选进度回调 (step_key, message)

    Returns:
        {"contracts_loaded": int, "pdfs_processed": int,
         "clauses_extracted": int, "results_cached": int}
    """
    def _step(key: str, msg: str = ""):
        """发送进度更新"""
        if on_progress:
            on_progress(key, msg)
        logger.info(f"[{key}] {msg}")

    stats = {"contracts_loaded": 0, "pdfs_processed": 0,
             "clauses_extracted": 0, "results_cached": 0}

    provider = create_provider(config)
    standards_path = os.path.join(data_dir, "standards.xlsx")
    meta_path = os.path.join(data_dir, "contracts_meta.xlsx")
    contracts_dir = os.path.join(data_dir, "contracts")
    cache_dir = os.path.join(data_dir, "cache")

    os.makedirs(cache_dir, exist_ok=True)

    # ── 步骤 1/4: 加载规范标准和合同元数据 ──
    _step("step1", "正在加载规范标准...")
    standards = load_standards(standards_path)
    _step("step1", f"✅ 规范标准加载完成 — 共 {len(standards)} 条")

    _step("step1", "正在加载合同元数据...")
    contracts = load_contracts_meta(meta_path)
    stats["contracts_loaded"] = len(contracts)
    _step("step1", f"✅ 合同元数据加载完成 — 共 {len(contracts)} 份合同")

    # ── 步骤 2/4: 解析 PDF 合同 ──
    pdf_files = [f for f in os.listdir(contracts_dir)
                 if f.endswith(".pdf") and os.path.isfile(os.path.join(contracts_dir, f))]
    total_pdfs = len(pdf_files)
    _step("step2", f"📄 找到 {total_pdfs} 个 PDF 文件，开始解析...")

    # 预处理函数：去掉数字前缀用于文件名匹配
    def _clean_pdf_key(name: str) -> str:
        """去掉数字前缀和扩展名: '1.中央公园.pdf' → '中央公园'"""
        n = name.rsplit(".", 1)[0] if "." in name else name
        n = re.sub(r'^\d+\.?\s*', '', n)
        return n.strip().lower()

    # 建立来源文件索引
    source_index: dict[str, "Contract"] = {}
    for c in contracts:
        if c.source_pdf:
            key = _clean_pdf_key(c.source_pdf)
            source_index[key] = c

    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(contracts_dir, pdf_file)
        pdf_clean = _clean_pdf_key(pdf_file)

        matched = None

        # 策略1: 来源文件精确匹配
        matched = source_index.get(pdf_clean)

        # 策略2: 来源文件模糊匹配
        if matched is None:
            for key, c in source_index.items():
                if pdf_clean in key or key in pdf_clean:
                    matched = c
                    _step("step2", f"   🔗 模糊匹配: '{pdf_file}' → 来源 '{c.source_pdf}'")
                    break

        # 策略3: 物业名称匹配（兜底）
        if matched is None:
            for c in contracts:
                if c.property_name and (
                    c.property_name.strip().lower() in pdf_clean
                    or pdf_clean in c.property_name.strip().lower()
                ):
                    matched = c
                    break

        if matched is None:
            _step("step2", f"⚠️ [{i}/{total_pdfs}] {pdf_file} — 未匹配到合同元数据，跳过")
            continue

        # 预检测 PDF 类型（扫描件/文本型）
        ocr_needed = _check_if_ocr_needed(pdf_path)
        ocr_tag = " [OCR扫描件]" if ocr_needed else ""
        _step("step2", f"🔍 [{i}/{total_pdfs}] 正在解析: {pdf_file} → {matched.property_name}{ocr_tag}...")

        level, clauses = extract_contract_from_pdf(pdf_path, provider)
        matched.service_clauses = clauses
        matched.source_pdf = pdf_file
        if level:
            matched.service_level_declared = level

        stats["pdfs_processed"] += 1
        stats["clauses_extracted"] += len(clauses)
        _step("step2", f"   ✅ [{i}/{total_pdfs}] {matched.property_name} — 提取 {len(clauses)} 条服务条款{ocr_tag}")

    if stats["pdfs_processed"] == 0:
        _step("step2", "⚠️ 未成功处理任何 PDF 文件")

    # ── 步骤 3/4: 执行规则匹配 ──
    threshold = config.get("matching", {}).get("rule_confidence_threshold", 0.9)
    batch_size = config.get("matching", {}).get("llm_batch_size", 20)

    _step("step3", f"⚙️ 开始规则匹配（阈值={threshold}）...")

    all_pending = []
    all_results = {}

    for i, contract in enumerate(contracts, 1):
        if not contract.service_clauses:
            _step("step3", f"⚠️ [{i}/{len(contracts)}] {contract.property_name} — 无服务条款，跳过")
            continue
        rule_results, pending = rule_match(contract, standards, threshold)
        all_results[contract.id] = list(rule_results)
        all_pending.extend(pending)
        _step("step3", f"   [{i}/{len(contracts)}] {contract.property_name}: "
              f"{len(rule_results)} 条规则确定, {len(pending)} 条待 LLM 判定")

    rule_total = sum(len(v) for v in all_results.values())
    _step("step3", f"📊 规则阶段完成: {rule_total} 条确定, {len(all_pending)} 条待 LLM 语义判定")

    # ── 步骤 4/4: LLM 语义判定 ──
    if all_pending and provider:
        llm_batches = (len(all_pending) + batch_size - 1) // batch_size
        _step("step4", f"🤖 开始 LLM 语义判定，共 {len(all_pending)} 条，分 {llm_batches} 批...")

        for i in range(0, len(all_pending), batch_size):
            batch = all_pending[i:i + batch_size]
            batch_num = i // batch_size + 1
            _step("step4", f"🔄 LLM 第 {batch_num}/{llm_batches} 批 ({len(batch)} 条)...")
            llm_results = llm_match_batch(batch, provider)
            for result in llm_results:
                if result.contract_id in all_results:
                    all_results[result.contract_id].append(result)
            _step("step4", f"   ✅ 第 {batch_num}/{llm_batches} 批完成")
    elif all_pending and not provider:
        _step("step4", f"⚠️ LLM 不可用，{len(all_pending)} 条标记为不确定")
        for c, s, _ in all_pending:
            if c.id in all_results:
                all_results[c.id].append(MatchResult(
                    contract_id=c.id,
                    standard_item_id=s.id,
                    verdict="不确定",
                    evidence="LLM 不可用",
                    confidence=0.0,
                    method="llm",
                    matched_level=0,
                ))
    else:
        _step("step4", "✅ 无需 LLM 判定（规则已覆盖全部条款）")

    # ── 写入缓存 ──
    _step("step4", "💾 正在写入缓存...")
    cache_mgr = CacheManager(cache_dir)
    cache_mgr.save_contracts(contracts)
    cache_mgr.save_results(all_results)
    stats["results_cached"] = len(all_results)
    _step("step4", f"✅ 缓存写入完成 — {len(all_results)} 份合同结果已持久化")

    logger.info(f"预处理完成: {stats}")
    return stats
