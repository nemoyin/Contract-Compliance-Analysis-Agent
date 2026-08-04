"""测试缓存管理"""
import json
import os
import tempfile
import time
import pytest
from engine.cache import CacheManager
from engine.models import MatchResult, Contract, ServiceClause


@pytest.fixture
def temp_cache_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def cache_mgr(temp_cache_dir):
    return CacheManager(temp_cache_dir)


class TestCacheManager:
    def test_new_cache_is_invalid(self, cache_mgr):
        assert cache_mgr.is_valid() is False

    def test_save_and_load_results(self, cache_mgr):
        results = {
            "C001": [
                MatchResult(contract_id="C001", standard_item_id="L1-001",
                           verdict="满足", evidence="xxx", confidence=0.95,
                           method="rule", matched_level=1),
                MatchResult(contract_id="C001", standard_item_id="L1-002",
                           verdict="不满足", evidence="yyy", confidence=0.9,
                           method="rule", matched_level=0),
            ]
        }
        cache_mgr.save_results(results)
        assert cache_mgr.is_valid() is True

        loaded = cache_mgr.load_results()
        assert "C001" in loaded
        assert len(loaded["C001"]) == 2

    def test_save_and_load_contracts(self, cache_mgr):
        contracts = [
            Contract(id="C001", property_name="测试", location="某地",
                     building_area=10000.0, property_type="住宅",
                     party_a="甲", party_b="乙", residential_fee=3.0,
                     commercial_fee=5.0, parking_fee=200.0,
                     service_clauses=[
                         ServiceClause(content="24小时值班", category="公共秩序维护", page=3)
                     ]),
        ]
        cache_mgr.save_contracts(contracts)
        loaded = cache_mgr.get_contracts()
        assert len(loaded) == 1
        assert loaded[0].property_name == "测试"
        assert len(loaded[0].service_clauses) == 1

    def test_invalidate(self, cache_mgr):
        results = {"C001": []}
        cache_mgr.save_results(results)
        assert cache_mgr.is_valid() is True
        cache_mgr.invalidate()
        assert cache_mgr.is_valid() is False

    def test_metadata(self, cache_mgr):
        results = {"C001": []}
        cache_mgr.save_results(results)
        meta = cache_mgr.get_metadata()
        assert "cached_at" in meta
        assert "contract_count" in meta
        assert meta["contract_count"] == 1
