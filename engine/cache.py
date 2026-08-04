"""缓存管理：预处理结果持久化"""
import json
import os
import time
import logging
from typing import Any
from engine.models import MatchResult, Contract, ServiceClause

logger = logging.getLogger(__name__)


class CacheManager:
    """管理匹配结果和合同对象的文件缓存"""

    RESULTS_FILE = "merged_results.json"
    CONTRACTS_FILE = "contracts.json"
    METADATA_FILE = "metadata.json"

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def results_path(self) -> str:
        return os.path.join(self.cache_dir, self.RESULTS_FILE)

    @property
    def contracts_path(self) -> str:
        return os.path.join(self.cache_dir, self.CONTRACTS_FILE)

    @property
    def metadata_path(self) -> str:
        return os.path.join(self.cache_dir, self.METADATA_FILE)

    def is_valid(self) -> bool:
        """缓存是否有效"""
        return os.path.exists(self.results_path) and os.path.exists(self.metadata_path)

    def invalidate(self) -> None:
        """清除所有缓存"""
        for path in [self.results_path, self.contracts_path, self.metadata_path]:
            if os.path.exists(path):
                os.remove(path)
        logger.info("缓存已清除")

    def load_results(self) -> dict[str, list[MatchResult]]:
        """加载匹配结果缓存

        Returns:
            {contract_id: [MatchResult, ...]}
        """
        if not os.path.exists(self.results_path):
            return {}
        try:
            with open(self.results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"缓存文件损坏，无法加载结果: {self.results_path} — {e}")
            return {}
        results: dict[str, list[MatchResult]] = {}
        for cid, items in data.items():
            results[cid] = [_dict_to_match_result(item) for item in items]
        return results

    def save_results(self, results: dict[str, list[MatchResult]]) -> None:
        """保存匹配结果到缓存"""
        data = {}
        for cid, items in results.items():
            data[cid] = [_match_result_to_dict(item) for item in items]
        with open(self.results_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._write_metadata(len(results))
        logger.info(f"匹配结果已缓存: {len(results)} 个合同")

    def get_contracts(self) -> list[Contract]:
        """加载缓存的合同对象"""
        if not os.path.exists(self.contracts_path):
            return []
        try:
            with open(self.contracts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"缓存文件损坏，无法加载合同: {self.contracts_path} — {e}")
            return []
        return [_dict_to_contract(item) for item in data]

    def save_contracts(self, contracts: list[Contract]) -> None:
        """保存合同对象到缓存"""
        data = [_contract_to_dict(c) for c in contracts]
        with open(self.contracts_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"合同数据已缓存: {len(contracts)} 个")

    def get_metadata(self) -> dict[str, Any]:
        """获取缓存元数据"""
        if not os.path.exists(self.metadata_path):
            return {}
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"缓存文件损坏，无法加载元数据: {self.metadata_path} — {e}")
            return {}

    def _write_metadata(self, contract_count: int) -> None:
        meta = {
            "cached_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cached_at_ts": time.time(),
            "contract_count": contract_count,
        }
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def merge_results(self, new_results: dict[str, list[MatchResult]]) -> None:
        """增量合并新结果到现有缓存"""
        existing = self.load_results()
        existing.update(new_results)
        self.save_results(existing)


def _match_result_to_dict(r: MatchResult) -> dict:
    return {
        "contract_id": r.contract_id,
        "standard_item_id": r.standard_item_id,
        "verdict": r.verdict,
        "evidence": r.evidence,
        "confidence": r.confidence,
        "method": r.method,
        "matched_level": r.matched_level,
    }


def _dict_to_match_result(d: dict) -> MatchResult:
    return MatchResult(
        contract_id=d["contract_id"],
        standard_item_id=d["standard_item_id"],
        verdict=d["verdict"],
        evidence=d.get("evidence", ""),
        confidence=d.get("confidence", 0.0),
        method=d.get("method", "rule"),
        matched_level=d.get("matched_level", 0),
    )


def _contract_to_dict(c: Contract) -> dict:
    return {
        "id": c.id,
        "property_name": c.property_name,
        "location": c.location,
        "building_area": c.building_area,
        "property_type": c.property_type,
        "party_a": c.party_a,
        "party_b": c.party_b,
        "residential_fee": c.residential_fee,
        "commercial_fee": c.commercial_fee,
        "parking_fee": c.parking_fee,
        "service_level_declared": c.service_level_declared,
        "service_clauses": [{"content": s.content, "category": s.category, "page": s.page}
                           for s in c.service_clauses],
        "source_pdf": c.source_pdf,
    }


def _dict_to_contract(d: dict) -> Contract:
    clauses = [ServiceClause(content=s["content"], category=s["category"], page=s.get("page", 1))
               for s in d.get("service_clauses", [])]
    return Contract(
        id=d["id"],
        property_name=d["property_name"],
        location=d.get("location", ""),
        building_area=d.get("building_area", 0.0),
        property_type=d.get("property_type", "住宅"),
        party_a=d.get("party_a", ""),
        party_b=d.get("party_b", ""),
        residential_fee=d.get("residential_fee", 0.0),
        commercial_fee=d.get("commercial_fee", 0.0),
        parking_fee=d.get("parking_fee", 0.0),
        service_level_declared=d.get("service_level_declared"),
        service_clauses=clauses,
        source_pdf=d.get("source_pdf", ""),
    )
