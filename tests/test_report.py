"""测试报告导出"""
import os
import tempfile
import pytest
from engine.report import export_compliance_report, export_comparison
from engine.models import (
    ComplianceReport, ComparisonResult, Contract, MatchResult, StandardItem
)


@pytest.fixture
def sample_report():
    return ComplianceReport(
        contract_id="C001",
        total_rate=0.75,
        level_rates={1: 0.90, 2: 0.80, 3: 0.70, 4: 0.60, 5: 0.50},
        category_rates={"综合管理": 0.85, "保洁服务": 0.70},
        matched_count=150,
        total_count=200,
    )


@pytest.fixture
def sample_comparison():
    c_a = Contract(id="C001", property_name="A小区", location="x",
                   building_area=50000.0, property_type="住宅",
                   party_a="甲", party_b="乙",
                   residential_fee=3.2, commercial_fee=5.0, parking_fee=300.0)
    c_b = Contract(id="C002", property_name="B小区", location="x",
                   building_area=80000.0, property_type="住宅",
                   party_a="甲", party_b="丙",
                   residential_fee=3.3, commercial_fee=5.2, parking_fee=280.0)
    r_a = ComplianceReport("C001", 0.75, {1: 0.9}, {"综合管理": 0.85}, 150, 200)
    r_b = ComplianceReport("C002", 0.60, {1: 0.8}, {"综合管理": 0.70}, 120, 200)
    return ComparisonResult(c_a, c_b, "residential", r_a, r_b, [], [], [], "测试总结")


class TestExportCompliance:
    def test_creates_file(self, sample_report):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            export_compliance_report(sample_report, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)


class TestExportComparison:
    def test_creates_file(self, sample_comparison):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            export_comparison(sample_comparison, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)
