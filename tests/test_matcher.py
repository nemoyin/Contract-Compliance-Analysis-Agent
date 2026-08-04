"""测试规则匹配引擎"""
import json
from unittest.mock import MagicMock
import pytest
from engine.matcher import rule_match, _keyword_match, _exclusion_check, _numeric_compare, _level_infer
from engine.matcher import llm_match_batch, match_contract, match_all_contracts
from engine.llm import LLMProvider
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


class TestLLMMatchBatch:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock(spec=LLMProvider)
        return provider

    @pytest.fixture
    def sample_pending(self, sample_standards, sample_contract):
        # 人为构造2条不确定项
        return [
            (sample_contract, sample_standards[2], 0.6),  # 24小时值班
            (sample_contract, sample_standards[3], 0.55),  # 修剪草坪
        ]

    def test_returns_match_results(self, sample_pending, mock_provider):
        mock_provider.chat.return_value = json.dumps({
            "results": [
                {"index": 0, "verdict": "满足", "evidence": "24小时安保值班", "confidence": 0.85, "reasoning": "合同有24小时值班"},
                {"index": 1, "verdict": "部分满足", "evidence": "合同未明确修剪频次", "confidence": 0.70, "reasoning": "绿化条款不明确"},
            ]
        })
        results = llm_match_batch(sample_pending, mock_provider)
        assert len(results) == 2
        assert results[0].method == "llm"
        assert results[0].verdict == "满足"

    def test_empty_pending_returns_empty(self, mock_provider):
        results = llm_match_batch([], mock_provider)
        assert results == []

    def test_provider_none_returns_uncertain(self, sample_pending):
        results = llm_match_batch(sample_pending, None)
        assert len(results) == 2
        for r in results:
            assert r.verdict == "不确定"
            assert r.method == "llm"

    def test_handles_partial_response(self, sample_pending, mock_provider):
        # LLM 只返回了1条结果（少了1条）
        mock_provider.chat.return_value = json.dumps({
            "results": [
                {"index": 0, "verdict": "满足", "evidence": "xxx", "confidence": 0.9, "reasoning": "ok"},
            ]
        })
        results = llm_match_batch(sample_pending, mock_provider)
        # 返回了结果的那条，缺的标记为不确定
        assert len(results) == 2
        verdicts = {r.standard_item_id: r.verdict for r in results}
        assert any(v == "不确定" for v in verdicts.values())


class TestMatchContract:
    def test_combines_rule_and_llm(self, sample_standards, sample_contract):
        """端到端测试，使用真实规则匹配（无LLM）"""
        results = match_contract(sample_contract, sample_standards, provider=None, threshold=0.9)
        assert len(results) == len(sample_standards)
        methods = {r.method for r in results}
        assert "rule" in methods  # 规则阶段至少产生了一些结果

    def test_all_verdicts_valid(self, sample_standards, sample_contract):
        results = match_contract(sample_contract, sample_standards, provider=None, threshold=0.9)
        valid = {"满足", "部分满足", "不满足", "不确定"}
        for r in results:
            assert r.verdict in valid
