"""测试 PDF 合同提取器"""
import json
import pytest
from unittest.mock import MagicMock
from engine.pdf_extractor import (
    locate_service_chapters, extract_service_clauses,
    extract_contract_from_pdf, LOCATE_PROMPT, EXTRACT_PROMPT
)
from engine.pdf_parser import DocumentTree, Chapter
from engine.models import ServiceClause


@pytest.fixture
def sample_tree():
    chapters = [
        Chapter(title="第一章 总则", level=1, text="甲方乙方信息...", summary="合同双方基本信息"),
        Chapter(title="第二条 综合管理", level=2, text="设立办公室，24小时值班。每日巡查。",
                summary="综合管理服务内容"),
        Chapter(title="第三条 保洁服务", level=2, text="每日清扫楼道。每周清洗垃圾桶。",
                summary="保洁服务标准和频次"),
        Chapter(title="第三章 物业费用", level=1, text="住宅物业费3.2元...", summary="费用标准"),
    ]
    return DocumentTree(chapters=chapters, full_text="full text")


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.chat.return_value = "mocked response"
    return provider


class TestLocateServiceChapters:
    def test_returns_indices(self, sample_tree, mock_provider):
        # 模拟 LLM 返回包含 [1, 2] 的 JSON
        mock_provider.chat.return_value = '{"service_indices": [1, 2], "reasoning": "found"}'
        indices = locate_service_chapters(sample_tree, mock_provider)
        assert indices == [1, 2]

    def test_handles_malformed_json(self, sample_tree, mock_provider):
        mock_provider.chat.return_value = 'not valid json at all'
        indices = locate_service_chapters(sample_tree, mock_provider)
        assert indices == []  # fallback gracefully

    def test_prompt_includes_toc(self, sample_tree, mock_provider):
        mock_provider.chat.return_value = '{"service_indices": [1]}'
        locate_service_chapters(sample_tree, mock_provider)
        call_args = mock_provider.chat.call_args[0][0]
        prompt_text = call_args[0]["content"]
        assert "第一章 总则" in prompt_text
        assert "综合管理" in prompt_text


class TestExtractServiceClauses:
    def test_extracts_clauses(self, mock_provider):
        mock_provider.chat.return_value = json.dumps({
            "clauses": [
                {"content": "每日清扫楼道一次", "category": "保洁服务", "page": 5},
                {"content": "24小时安保值班", "category": "公共秩序维护", "page": 6},
            ]
        })
        clauses = extract_service_clauses("服务章节文本内容...", mock_provider)
        assert len(clauses) == 2
        assert clauses[0].content == "每日清扫楼道一次"
        assert clauses[0].category == "保洁服务"

    def test_handles_empty_response(self, mock_provider):
        mock_provider.chat.return_value = '{"clauses": []}'
        clauses = extract_service_clauses("一些文本", mock_provider)
        assert clauses == []

    def test_prompt_includes_text(self, mock_provider):
        mock_provider.chat.return_value = '{"clauses": []}'
        extract_service_clauses("测试服务内容", mock_provider)
        call_args = mock_provider.chat.call_args[0][0]
        assert "测试服务内容" in call_args[0]["content"]


class TestExtractContractFromPdf:
    def test_full_pipeline(self, sample_tree, mock_provider, monkeypatch):
        import engine.pdf_extractor as mod
        monkeypatch.setattr(mod, "parse_pdf", lambda p: sample_tree)

        mock_provider.chat.side_effect = [
            '{"service_indices": [1]}',   # locate
            json.dumps({"clauses": [{"content": "24小时值班", "category": "公共秩序维护", "page": 3}]}),
        ]

        level, clauses = extract_contract_from_pdf("test.pdf", mock_provider)
        assert len(clauses) == 1
        assert clauses[0].content == "24小时值班"

    def test_llm_unavailable_returns_empty(self, sample_tree, monkeypatch):
        import engine.pdf_extractor as mod
        monkeypatch.setattr(mod, "parse_pdf", lambda p: sample_tree)

        level, clauses = extract_contract_from_pdf("test.pdf", None)
        assert level is None
        assert clauses == []
