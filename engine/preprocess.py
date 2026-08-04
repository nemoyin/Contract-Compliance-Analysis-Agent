"""预处理流水线：PDF 解析 → 合同提取 → 匹配引擎 → 缓存写入"""
import os
import logging
from engine.loader import load_standards, load_contracts_meta
from engine.llm import create_provider
from engine.pdf_extractor import extract_contract_from_pdf
from engine.matcher import match_all_contracts
from engine.cache import CacheManager

logger = logging.getLogger(__name__)


def run_preprocessing(data_dir: str, config: dict) -> dict[str, int]:
    """执行完整预处理流水线

    Returns:
        {"contracts_loaded": int, "pdfs_processed": int,
         "clauses_extracted": int, "results_cached": int}
    """
    stats = {"contracts_loaded": 0, "pdfs_processed": 0,
             "clauses_extracted": 0, "results_cached": 0}

    provider = create_provider(config)
    standards_path = os.path.join(data_dir, "standards.xlsx")
    meta_path = os.path.join(data_dir, "contracts_meta.xlsx")
    contracts_dir = os.path.join(data_dir, "contracts")
    cache_dir = os.path.join(data_dir, "cache")

    os.makedirs(cache_dir, exist_ok=True)

    # 1. 加载标准
    logger.info("加载成都市五级规范...")
    standards = load_standards(standards_path)
    logger.info(f"已加载 {len(standards)} 条规范")

    # 2. 加载合同元数据
    logger.info("加载合同元数据...")
    contracts = load_contracts_meta(meta_path)
    stats["contracts_loaded"] = len(contracts)

    # 3. 处理 PDF
    pdf_files = [f for f in os.listdir(contracts_dir)
                 if f.endswith(".pdf") and os.path.isfile(os.path.join(contracts_dir, f))]
    logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")

    for pdf_file in pdf_files:
        pdf_path = os.path.join(contracts_dir, pdf_file)
        pdf_name = os.path.splitext(pdf_file)[0]

        # 匹配合同
        matched = None
        for c in contracts:
            if c.property_name in pdf_name or pdf_name in c.property_name:
                matched = c
                break

        if matched is None:
            logger.warning(f"PDF {pdf_file} 未匹配到合同元数据，跳过")
            continue

        logger.info(f"处理: {pdf_file} → {matched.property_name}")
        level, clauses = extract_contract_from_pdf(pdf_path, provider)
        matched.service_clauses = clauses
        matched.source_pdf = pdf_file
        if level:
            matched.service_level_declared = level

        stats["pdfs_processed"] += 1
        stats["clauses_extracted"] += len(clauses)

    # 4. 匹配引擎
    logger.info("开始匹配引擎...")
    threshold = config.get("matching", {}).get("rule_confidence_threshold", 0.9)
    batch_size = config.get("matching", {}).get("llm_batch_size", 20)
    all_results = match_all_contracts(contracts, standards, provider, threshold, batch_size)

    # 5. 写入缓存
    cache_mgr = CacheManager(cache_dir)
    cache_mgr.save_contracts(contracts)
    cache_mgr.save_results(all_results)
    stats["results_cached"] = len(all_results)

    logger.info(f"预处理完成: {stats}")
    return stats
