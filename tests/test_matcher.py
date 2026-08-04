"""测试规则匹配引擎"""
import pytest
from engine.matcher import rule_match, _keyword_match, _exclusion_check, _numeric_compare, _level_infer
from engine.models import StandardItem, Contract, ServiceClause, MatchResult


@pytest.fixture
def sample_standards():
    return [
        StandardItem(id="L1-ZH-001", level=1, category="综合管理",
                     requirement="设立物业服务办公室", is_new_vs_prev=False),
        StandardItem(id="L2-BJ-001", level=2, category="保洁服务",
                     requirement="每日清扫楼道一次", is_new_vs_prev=False),
        StandardItem(id="L3-ZX-001", level=3, category="公共秩序维护",
                     requirement="24小时值班巡逻", is_new_vs_prev=True),
        StandardItem(id="L4-LH-001", level=4, category="绿化养护",
                     requirement="每季度修剪草坪不少于4次", is_new_vs_prev=False),
        StandardItem(id="L5-SS-001", level=5, category="共用设施设备维护",
                     requirement="电梯每月维保不少于2次", is_new_vs_prev=True),
    ]


@pytest.fixture
def sample_contract():
    clauses = [
        ServiceClause(content="设立物业服务办公室，配备2名专职人员", category="综合管理", page=3),
        ServiceClause(content="每日清扫楼道及公共区域", category="保洁服务", page=5),
        ServiceClause(content="24小时安保值班，定时巡逻", category="公共秩序维护", page=6),
        ServiceClause(content="不含绿化养护服务", category="绿化养护", page=7),
        ServiceClause(content="电梯按厂家要求定期保养", category="共用设施设备维护", page=4),
    ]
    return Contract(
        id="C001", property_name="测试小区", location="某地", building_area=50000.0,
        property_type="住宅", party_a="甲方", party_b="乙方",
        residential_fee=3.2, commercial_fee=5.0, parking_fee=300.0,
        service_clauses=clauses, service_level_declared="按成都市住宅物业服务三级标准执行",
    )


class TestKeywordMatch:
    def test_exact_keyword_hit(self):
        assert _keyword_match("设立物业服务办公室", "设立物业服务办公室，配备2名专职人员")[0] >= 0.9

    def test_partial_keyword_hit(self):
        score, _ = _keyword_match("每日清扫楼道一次", "每日清扫楼道及公共区域")
        assert score >= 0.7

    def test_keyword_miss(self):
        score, _ = _keyword_match("提供游泳馆", "设立物业服务办公室")
        assert score < 0.5


class TestExclusionCheck:
    def test_exclusion_detected(self):
        assert _exclusion_check("不含绿化养护服务", "绿化养护") is True

    def test_no_exclusion(self):
        assert _exclusion_check("24小时安保值班", "公共秩序维护") is False


class TestNumericCompare:
    def test_frequency_match(self):
        assert _numeric_compare("每日清扫楼道一次", "每日清扫楼道")[0] >= 0.9

    def test_frequency_mismatch(self):
        score, _ = _numeric_compare("每日清扫楼道一次", "每周清扫楼道一次")
        assert score < 0.7

    def test_count_compare(self):
        score, _ = _numeric_compare("每月维保不少于2次", "每月维保1次")
        assert score < 0.7


class TestRuleMatch:
    def test_returns_results_and_pending(self, sample_standards, sample_contract):
        results, pending = rule_match(sample_contract, sample_standards, threshold=0.9)
        assert len(results) > 0
        # 确定的结果 confidence >= 0.9
        for r in results:
            assert r.confidence >= 0.9
            assert r.method == "rule"
        # pending 中的置信度 < 0.9
        for _, _, conf in pending:
            assert conf < 0.9

    def test_all_results_have_contract_id(self, sample_standards, sample_contract):
        results, _ = rule_match(sample_contract, sample_standards, threshold=0.9)
        for r in results:
            assert r.contract_id == "C001"

    def test_exclusion_marks_category_unmet(self, sample_standards, sample_contract):
        results, pending = rule_match(sample_contract, sample_standards, threshold=0.9)
        # 绿化养护标准条款应该因为"不含绿化"被标记为不满足
        green_results = [r for r in results if r.standard_item_id.startswith("L4-LH")]
        if green_results:
            assert green_results[0].verdict == "不满足"

    def test_level_declared_inference(self, sample_standards, sample_contract):
        results, _ = rule_match(sample_contract, sample_standards, threshold=0.9)
        # 合同声明三级标准，三级以下的规范条款应该高置信度满足
        low_level_results = [r for r in results if r.matched_level <= 3 and r.verdict == "满足"]
        assert len(low_level_results) > 0

    def test_returns_correct_types(self, sample_standards, sample_contract):
        results, pending = rule_match(sample_contract, sample_standards, threshold=0.9)
        for r in results:
            assert isinstance(r, MatchResult)
        for item in pending:
            assert isinstance(item[0], Contract) or isinstance(item[0], str)
