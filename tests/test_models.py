"""测试数据模型"""
import pytest
from engine.models import (
    StandardItem, ServiceClause, Contract, MatchResult,
    ComplianceReport, ComparisonResult, ClusterResult,
    QualityGroup, PriceOutlier
)


class TestStandardItem:
    def test_create_standard_item(self):
        item = StandardItem(
            id="L3-C2-045",
            level=3,
            category="保洁服务",
            requirement="每日清扫楼道一次",
            is_new_vs_prev=True
        )
        assert item.level == 3
        assert item.category == "保洁服务"
        assert item.is_new_vs_prev is True

    def test_id_format(self):
        item = StandardItem(
            id="L1-C7-001",
            level=1,
            category="综合管理",
            requirement="测试",
            is_new_vs_prev=False
        )
        assert item.id.startswith("L1")


class TestContract:
    def test_create_contract_with_clauses(self):
        clauses = [
            ServiceClause(content="24小时安保值班", category="公共秩序维护", page=5),
            ServiceClause(content="每日清扫楼道", category="保洁服务", page=8),
        ]
        contract = Contract(
            id="C001",
            property_name="测试小区",
            location="天府新区天府大道1号",
            building_area=50000.0,
            property_type="住宅",
            party_a="业主委员会",
            party_b="某某物业公司",
            residential_fee=3.2,
            commercial_fee=5.0,
            parking_fee=300.0,
            service_level_declared="三级",
            service_clauses=clauses,
            source_pdf="test.pdf"
        )
        assert len(contract.service_clauses) == 2
        assert contract.residential_fee == 3.2

    def test_default_empty_clauses(self):
        contract = Contract(
            id="C002",
            property_name="空条款小区",
            location="某地",
            building_area=10000.0,
            property_type="住宅",
            party_a="甲方",
            party_b="乙方",
            residential_fee=2.5,
            commercial_fee=4.0,
            parking_fee=200.0,
        )
        assert contract.service_clauses == []
        assert contract.service_level_declared is None


class TestMatchResult:
    def test_rule_match(self):
        result = MatchResult(
            contract_id="C001",
            standard_item_id="L3-C2-045",
            verdict="满足",
            evidence="每日清扫楼道一次",
            confidence=0.95,
            method="rule",
            matched_level=3
        )
        assert result.method == "rule"
        assert result.verdict == "满足"

    def test_llm_match(self):
        result = MatchResult(
            contract_id="C001",
            standard_item_id="L3-C4-012",
            verdict="部分满足",
            evidence="定期打扫公共区域",
            confidence=0.75,
            method="llm",
            matched_level=2
        )
        assert result.method == "llm"
        assert result.verdict == "部分满足"


class TestComplianceReport:
    def test_rates_calculation(self):
        report = ComplianceReport(
            contract_id="C001",
            total_rate=0.75,
            level_rates={1: 0.90, 2: 0.80, 3: 0.70, 4: 0.60, 5: 0.50},
            category_rates={"保洁服务": 0.85, "综合管理": 0.70},
            matched_count=150,
            total_count=200,
        )
        assert 0 <= report.total_rate <= 1
        assert report.matched_count <= report.total_count
        assert len(report.level_rates) == 5


class TestClusterResult:
    def test_group_and_outlier(self):
        group = QualityGroup(
            group_id=1,
            contract_ids=["C001", "C002", "C003"],
            avg_satisfaction=0.72,
            avg_price=3.2,
            price_std=0.1
        )
        outlier = PriceOutlier(
            contract_id="C004",
            property_name="高价小区",
            fee=4.8,
            group_id=1,
            group_avg_fee=3.2,
            deviation_pct=50.0
        )
        result = ClusterResult(
            fee_type="residential",
            groups=[group],
            outliers=[outlier]
        )
        assert len(result.groups) == 1
        assert len(result.outliers) == 1
        assert result.outliers[0].deviation_pct == 50.0
