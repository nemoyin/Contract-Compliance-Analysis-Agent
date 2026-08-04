"""测试 Excel 数据加载"""
import os
import tempfile
import pytest
import pandas as pd
from engine.loader import load_standards, load_contracts_meta
from engine.models import StandardItem, Contract


@pytest.fixture
def sample_standards_path():
    """创建示例规范 Excel"""
    df = pd.DataFrame({
        "等级": [1, 1, 2, 3],
        "大类": ["综合管理", "保洁服务", "综合管理", "绿化养护"],
        "内容和要求": [
            "设立物业服务办公室",
            "每日清扫楼道一次",
            "24小时受理报修",
            "定期修剪草坪"
        ],
        "是否新增": ["否", "否", "是", "否"],
    })
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        df.to_excel(f.name, index=False)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def sample_contracts_meta_path():
    """创建示例合同元数据 Excel"""
    df = pd.DataFrame({
        "物业名称": ["测试小区A", "测试小区B"],
        "位置": ["天府大道1号", "天府大道2号"],
        "建筑面积": [50000, 80000],
        "物业类型": ["住宅", "商住"],
        "甲方": ["业委会A", "开发商B"],
        "乙方": ["物业公司A", "物业公司B"],
        "住宅物业费": [3.2, 2.8],
        "商业物业费": [5.0, 4.5],
        "车位费": [300, 250],
    })
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        df.to_excel(f.name, index=False)
        path = f.name
    yield path
    os.unlink(path)


class TestLoadStandards:
    def test_loads_all_rows(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        assert len(items) == 4

    def test_correct_levels(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        levels = [item.level for item in items]
        assert levels == [1, 1, 2, 3]

    def test_categories(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        cats = [item.category for item in items]
        assert "保洁服务" in cats
        assert "绿化养护" in cats

    def test_is_new_vs_prev_parsed(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        new_flags = [item.is_new_vs_prev for item in items]
        assert new_flags == [False, False, True, False]

    def test_requirement_content(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        assert items[0].requirement == "设立物业服务办公室"

    def test_generates_ids(self, sample_standards_path):
        items = load_standards(sample_standards_path)
        ids = [item.id for item in items]
        assert all(id.startswith("L") for id in ids)
        assert len(set(ids)) == 4  # unique


class TestLoadContractsMeta:
    def test_loads_all_contracts(self, sample_contracts_meta_path):
        contracts = load_contracts_meta(sample_contracts_meta_path)
        assert len(contracts) == 2

    def test_property_names(self, sample_contracts_meta_path):
        contracts = load_contracts_meta(sample_contracts_meta_path)
        names = [c.property_name for c in contracts]
        assert "测试小区A" in names
        assert "测试小区B" in names

    def test_fee_values(self, sample_contracts_meta_path):
        contracts = load_contracts_meta(sample_contracts_meta_path)
        assert contracts[0].residential_fee == 3.2
        assert contracts[0].commercial_fee == 5.0
        assert contracts[0].parking_fee == 300.0

    def test_empty_service_clauses(self, sample_contracts_meta_path):
        contracts = load_contracts_meta(sample_contracts_meta_path)
        for c in contracts:
            assert c.service_clauses == []

    def test_generates_ids(self, sample_contracts_meta_path):
        contracts = load_contracts_meta(sample_contracts_meta_path)
        ids = [c.id for c in contracts]
        assert len(set(ids)) == 2
