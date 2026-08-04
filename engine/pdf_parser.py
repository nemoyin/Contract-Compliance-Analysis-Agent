"""PDF 文本提取 + 文档树构建"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chapter:
    """文档树中的一个章节"""
    title: str
    level: int          # 1=章, 2=条/节
    text: str           # 章节全文
    summary: str        # 首段摘要（前200字）


@dataclass
class DocumentTree:
    """PDF 文档的结构化树"""
    chapters: list[Chapter]
    full_text: str

    def to_toc(self) -> str:
        """生成目录摘要，供 LLM 定位章节使用"""
        lines = []
        for i, ch in enumerate(self.chapters):
            indent = "  " * (ch.level - 1)
            lines.append(f"{indent}[{i}] {ch.title} — {ch.summary}")
        return "\n".join(lines)

    def get_chapter_text(self, indices: list[int]) -> str:
        """按索引获取指定章节的合并文本"""
        texts = []
        for i in indices:
            if 0 <= i < len(self.chapters):
                texts.append(f"## {self.chapters[i].title}\n{self.chapters[i].text}")
        return "\n\n".join(texts)


def parse_pdf(filepath: str) -> DocumentTree:
    """解析 PDF 文件，返回文档树。

    优先用 pdfplumber 提取并分析字体构建树；
    若失败则回退为纯文本解析。
    """
    text = _extract_text(filepath)
    chapters = _build_document_tree(text)
    return DocumentTree(chapters=chapters, full_text=text)


def _extract_text(filepath: str) -> str:
    """从 PDF 或纯文本文件提取全文"""
    ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""
    if ext == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            return "\n\n".join(pages)
        except ImportError:
            raise ImportError("pdfplumber 未安装。请运行: pip install pdfplumber")
        except Exception as e:
            raise IOError(f"PDF 解析失败: {filepath} — {e}")
    else:
        # 纯文本回退（用于测试和非 PDF 文件）
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()


def _build_document_tree(text: str) -> list[Chapter]:
    """从全文文本构建章节目录树"""
    lines = text.split("\n")
    chapters: list[Chapter] = []
    current_title = "开头"
    current_level = 1
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        heading = _detect_heading(stripped)
        if heading:
            # 保存前一个章节
            if current_lines:
                ch_text = "\n".join(current_lines)
                chapters.append(Chapter(
                    title=current_title,
                    level=current_level,
                    text=ch_text,
                    summary=ch_text[:200].replace("\n", " "),
                ))
            current_level, current_title = heading
            current_lines = [stripped]
        else:
            current_lines.append(stripped)

    # 保存最后一个章节
    if current_lines:
        ch_text = "\n".join(current_lines)
        chapters.append(Chapter(
            title=current_title,
            level=current_level,
            text=ch_text,
            summary=ch_text[:200].replace("\n", " "),
        ))

    return chapters


def _detect_heading(line: str) -> Optional[tuple[int, str]]:
    """检测一行文本是否为标题，返回 (层级, 标题) 或 None"""
    # 第X章 / 第X节
    m = re.match(r"^(第[一二三四五六七八九十百]+[章节])\s*(.*)", line)
    if m:
        return (1, f"{m.group(1)} {m.group(2)}".strip())
    # 第X条
    m = re.match(r"^(第[一二三四五六七八九十百]+条)\s*(.*)", line)
    if m:
        return (2, f"{m.group(1)} {m.group(2)}".strip())
    # 数字编号: "1. xxx" / "3.1 xxx"
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[.、)）]\s*(.*)", line)
    if m and len(line) < 80:
        level = 2 if "." in m.group(1) else 2
        return (level, line)
    return None
