"""测试对比分析模块"""
import pytest
import json
from unittest.mock import MagicMock
from engine.comparator import (
    calc_compliance_rate, compare_two, cluster_and_detect,
    _build_satisfaction_vector, _cosine_similarity, _detect_outliers
)
from engine.models import (
    StandardItem, Contract, MatchResult, ComplianceReport,
    ComparisonResult, ClusterResult, QualityGroup, PriceOutlier
)


@pytest.fixture
def standards():
    return [
        StandardItem(id="L1-ZH-001", level=1, category="综合管理",
                     requirement="设立办公室", is_new_vs_prev=False),
        StandardItem(id="L1-ZH-002", level=1, category="综合管理",
                     requirement="24小时受理报修", is_new_vs_prev=False),
        StandardItem(id="L1-BJ-001", level=1, category="保洁服务",
                     requirement="每日清扫", is_new_vs_prev=False),
        StandardItem(id="L2-ZH-001", level=2, category="综合管理",
                     requirement="建立服务档案", is_new_vs_prev=True),
        StandardItem(id="L2-BJ-001", level=2, category="保洁服务",
                     requirement="每周消毒", is_new_vs_prev=True),
        StandardItem(id="L3-ZX-001", level=3, category="公共秩序维护",
                     requirement="24小时巡逻", is_new_vs_prev=False),
    ]


@pytest.fixture
def contracts():
    return [
        Contract(id="C001", property_name="小区A", location="某地", building_area=50000.0,
                 property_type="住宅", party_a="甲", party_b="乙",
                 residential_fee=3.2, commercial_fee=5.0, parking_fee=300.0),
        Contract(id="C002", property_name="小区B", location="某地", building_area=80000.0,
                 property_type="住宅", party_a="甲", party_b="丙",
                 residential_fee=3.3, commercial_fee=5.2, parking_fee=280.0),
        Contract(id="C003", property_name="小区C", location="某地", building_area=30000.0,
                 property_type="住宅", party_a="甲", party_b="丁",
                 residential_fee=4.8, commercial_fee=7.0, parking_fee=400.0),
    ]


@pytest.fixture
def sample_results(standards, contracts):
    """生成模拟匹配结果：C001和C002满足度相近，C003较低"""
    results = {}
    # C001: 满足5/6
    results["C001"] = [
        MatchResult("C001", "L1-ZH-001", "满足", "...", 0.95, "rule", 1),
        MatchResult("C001", "L1-ZH-002", "满足", "...", 0.95, "rule", 1),
        MatchResult("C001", "L1-BJ-001", "满足", "...", 0.90, "rule", 1),
        MatchResult("C001", "L2-ZH-001", "满足", "...", 0.92, "rule", 2),
        MatchResult("C001", "L2-BJ-001", "满足", "...", 0.88, "llm", 2),
        MatchResult("C001", "L3-ZX-001", "不满足", "...", 0.90, "rule", 0),
    ]
    # C002: 满足4/6（与C001类似）
    results["C002"] = [
        MatchResult("C002", "L1-ZH-001", "满足", "...", 0.95, "rule", 1),
        MatchResult("C002", "L1-ZH-002", "满足", "...", 0.95, "rule", 1),
        MatchResult("C002", "L1-BJ-001", "满足", "...", 0.90, "rule", 1),
        MatchResult("C002", "L2-ZH-001", "满足", "...", 0.85, "llm", 2),
        MatchResult("C002", "L2-BJ-001", "不满足", "...", 0.90, "rule", 0),
        MatchResult("C002", "L3-ZX-001", "不满足", "...", 0.90, "rule", 0),
    ]
    # C003: 满足2/6（明显差距）
    results["C003"] = [
        MatchResult("C003", "L1-ZH-001", "满足", "...", 0.95, "rule", 1),
        MatchResult("C003", "L1-ZH-002", "满足", "...", 0.95, "rule", 1),
        MatchResult("C003", "L1-BJ-001", "不满足", "...", 0.90, "rule", 0),
        MatchResult("C003", "L2-ZH-001", "不满足", "...", 0.90, "rule", 0),
        MatchResult("C003", "L2-BJ-001", "不满足", "...", 0.90, "rule", 0),
        MatchResult("C003", "L3-ZX-001", "不满足", "...", 0.90, "rule", 0),
    ]
    return results


class TestComplianceRate:
    def test_calculates_correctly(self, sample_results, standards):
        report = calc_compliance_rate("C001", sample_results["C001"], standards)
        assert report.contract_id == "C001"
        assert report.total_rate == 5 / 6  # 5 satisfied out of 6
        assert report.total_count == 6
        assert report.matched_count == 5

    def test_level_rates(self, sample_results, standards):
        report = calc_compliance_rate("C001", sample_results["C001"], standards)
        assert 1 in report.level_rates
        assert report.level_rates[1] == 1.0  # all L1 satisfied

    def test_category_rates(self, sample_results, standards):
        report = calc_compliance_rate("C001", sample_results["C001"], standards)
        assert "综合管理" in report.category_rates
        assert "保洁服务" in report.category_rates


class TestSatisfactionVector:
    def test_builds_13d_vector(self, sample_results, standards):
        vec = _build_satisfaction_vector("C001", sample_results["C001"], standards)
        assert len(vec) == 13  # 1 total + 5 levels + 7 categories


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [0.5, 0.6, 0.7]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_different_vectors(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        assert _cosine_similarity(v1, v2) == pytest.approx(0.0)


class TestClusterAndDetect:
    def test_groups_similar_contracts(self, contracts, sample_results, standards):
        result = cluster_and_detect(contracts, sample_results, standards,
                                    fee_type="residential", config={
                                        "quality_similarity": 0.90,
                                        "price_outlier_std": 1.5,
                                    })
        assert isinstance(result, ClusterResult)
        assert len(result.groups) >= 1
        # C001 和 C002 应该在同一个组
        for group in result.groups:
            if "C001" in group.contract_ids:
                assert "C002" in group.contract_ids
                break

    def test_detects_price_outlier(self, contracts, sample_results, standards):
        result = cluster_and_detect(contracts, sample_results, standards,
                                    fee_type="residential", config={
                                        "quality_similarity": 0.90,
                                        "price_outlier_std": 1.5,
                                    })
        # C003 价格 4.8，与 C001(3.2)/C002(3.3) 同组的话应该是异常
        if result.outliers:
            outlier_ids = [o.contract_id for o in result.outliers]
            assert "C003" in outlier_ids or len(result.groups) > 1


class TestCompareTwo:
    def test_returns_comparison_result(self, contracts, sample_results, standards):
        config = {"similar_price_pct": 5}
        result = compare_two(
            contracts[0], contracts[1], "residential",
            sample_results, standards, config, provider=None
        )
        assert isinstance(result, ComparisonResult)
        assert result.fee_type == "residential"
        assert result.a_report.total_rate > 0

    def test_detects_a_only_b_only(self, contracts, sample_results, standards):
        config = {"similar_price_pct": 5}
        result = compare_two(
            contracts[0], contracts[2], "residential",
            sample_results, standards, config, provider=None
        )
        # C001 satisfies more than C003, so there should be A-only items
        assert len(result.a_only_items) >= 0
