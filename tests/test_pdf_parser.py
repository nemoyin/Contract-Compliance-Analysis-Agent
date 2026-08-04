"""测试 PDF 文本解析和文档树构建"""
import os
import tempfile
import pytest
from engine.pdf_parser import parse_pdf, DocumentTree, Chapter, _build_document_tree, _detect_heading


SAMPLE_CONTRACT_TEXT = """
第一章 总则

第一条 本合同双方当事人
甲方：某某业主委员会
乙方：某某物业管理有限公司

第二章 物业服务内容与标准

第二条 综合管理服务
1. 设立物业服务办公室，配备专职人员。
2. 24小时受理业主报修，一般维修4小时内完成。

第三条 保洁服务
1. 每日清扫楼道一次。
2. 每周清洗垃圾桶一次。

第三章 物业费用

第四条 物业服务费
住宅物业服务费为3.2元/月·平方米。
商业物业服务费为5.0元/月·平方米。

第四章 双方权利义务

第五条 甲方权利义务
甲方应按时缴纳物业服务费。
""".strip()


@pytest.fixture
def sample_text_path():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
        f.write(SAMPLE_CONTRACT_TEXT)
        path = f.name
    yield path
    os.unlink(path)


class TestHeadingDetection:
    def test_detects_chapter_pattern(self):
        assert _detect_heading("第一章 总则") == (1, "第一章 总则")
        assert _detect_heading("第十章 附则") == (1, "第十章 附则")

    def test_detects_article_pattern(self):
        assert _detect_heading("第一条 综合管理") == (2, "第一条 综合管理")
        assert _detect_heading("第二十条 违约责任") == (2, "第二十条 违约责任")

    def test_non_heading_returns_none(self):
        assert _detect_heading("本合同自双方签字之日起生效") is None
        assert _detect_heading("甲方：某某公司") is None

    def test_numeric_heading(self):
        assert _detect_heading("1. 服务内容") == (2, "1. 服务内容")
        assert _detect_heading("3.1 费用标准") == (2, "3.1 费用标准")


class TestDocumentTree:
    def test_builds_tree_from_text(self):
        chapters = _build_document_tree(SAMPLE_CONTRACT_TEXT)
        assert len(chapters) >= 3
        titles = [c.title for c in chapters]
        assert any("总则" in t for t in titles)
        assert any("服务" in t for t in titles)
        assert any("费用" in t for t in titles)

    def test_chapters_have_content(self):
        chapters = _build_document_tree(SAMPLE_CONTRACT_TEXT)
        for ch in chapters:
            assert len(ch.text) > 0


class TestParsePDF:
    def test_parse_txt_as_fallback(self, sample_text_path):
        """当不是 PDF 时，应回退为纯文本读取"""
        tree = parse_pdf(sample_text_path)
        assert isinstance(tree, DocumentTree)
        assert len(tree.chapters) >= 3
        assert len(tree.full_text) > 0

    def test_tree_structure(self, sample_text_path):
        tree = parse_pdf(sample_text_path)
        ch = tree.chapters[0]
        assert ch.title
        assert ch.level >= 1
        assert ch.text
        assert ch.summary
