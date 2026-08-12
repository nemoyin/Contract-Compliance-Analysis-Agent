"""PDF 文本提取 + 文档树构建（含 OCR 回退）"""
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── OCR 配置 ────────────────────────────────────────────
# Tesseract 安装路径（Windows 常见路径）
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
]
_TESSERACT_EXE: Optional[str] = None  # 首次调用时自动探测

OCR_MIN_TEXT_LENGTH = 100  # pdfplumber 提取文本短于此值时触发 OCR 回退


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


def _find_tesseract() -> Optional[str]:
    """探测系统上的 Tesseract 可执行文件路径"""
    for path in _TESSERACT_PATHS:
        if os.path.isfile(path):
            return path
    # 尝试从 PATH 查找
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path, "tesseract.exe" if os.name == "nt" else "tesseract")
        if os.path.isfile(exe):
            return exe
    return None


def _ocr_page_tesseract(image, page_num: int) -> str:
    """使用 Tesseract 对单页图片 OCR（中英文混合）"""
    global _TESSERACT_EXE
    import pytesseract

    if _TESSERACT_EXE is None:
        _TESSERACT_EXE = _find_tesseract()
        if _TESSERACT_EXE:
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE

    if not _TESSERACT_EXE:
        raise RuntimeError("Tesseract 未安装，无法执行 OCR")

    try:
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
        if text.strip():
            logger.info(f"   OCR 第{page_num}页: {len(text)} 字符 (Tesseract)")
        return text
    except Exception as e:
        logger.warning(f"   OCR 第{page_num}页 Tesseract 失败: {e}")
        return ""


def _pdf_page_to_image(page, dpi: int = 300):
    """使用 PyMuPDF 将单页 PDF 渲染为 PIL Image（无需外部依赖如 poppler）"""
    import fitz  # PyMuPDF
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    from PIL import Image
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _ocr_extract_text(filepath: str, total_pages: int) -> str:
    """OCR 回退：将 PDF 每页渲染为图片后 Tesseract 识别文字

    使用 PyMuPDF 渲染页面为图片，无需 poppler 外部依赖。
    Tesseract 无结果的页面静默跳过。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF 未安装，无法执行 OCR")
        return ""

    logger.info(f"🔍 OCR 回退开始 ({total_pages} 页): {os.path.basename(filepath)}")

    try:
        doc = fitz.open(filepath)
    except Exception as e:
        logger.error(f"PDF 打开失败: {e}")
        return ""

    pages_text: list[str] = []
    skipped = 0
    try:
        for page_num in range(1, len(doc) + 1):
            page = doc[page_num - 1]
            try:
                img = _pdf_page_to_image(page, dpi=300)
            except Exception as e:
                logger.warning(f"   第{page_num}页渲染失败: {e}")
                pages_text.append("")
                skipped += 1
                continue

            text = _ocr_page_tesseract(img, page_num)
            if not text.strip():
                skipped += 1
            pages_text.append(text or "")
    finally:
        doc.close()

    full_text = "\n\n".join(pages_text)
    logger.info(f"✅ OCR 完成: {len(full_text)} 字符 / {len(pages_text)} 页 (跳过 {skipped} 页)")
    return full_text


def _extract_text(filepath: str) -> str:
    """从 PDF 或纯文本文件提取全文

    PDF 文件优先使用 pdfplumber（保留文本结构），
    若提取文本过短（扫描件/图片型PDF）则自动回退到 OCR。
    """
    ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""
    if ext == "pdf":
        # ── 第一遍：pdfplumber ──
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                pdf_pages = [page.extract_text() or "" for page in pdf.pages]
                total_pages = len(pdf.pages)
            text = "\n\n".join(pdf_pages)
        except ImportError:
            raise ImportError("pdfplumber 未安装。请运行: pip install pdfplumber")
        except Exception as e:
            raise IOError(f"PDF 解析失败: {filepath} — {e}")

        # ── 判断是否需要 OCR 回退 ──
        usable_chars = len(re.sub(r"\s", "", text))
        if usable_chars < OCR_MIN_TEXT_LENGTH:
            logger.info(
                f"📄 {os.path.basename(filepath)}: "
                f"pdfplumber 提取 {usable_chars} 字符 < {OCR_MIN_TEXT_LENGTH}，触发 OCR 回退"
            )
            ocr_text = _ocr_extract_text(filepath, total_pages)
            ocr_usable = len(re.sub(r"\s", "", ocr_text))
            if ocr_usable > usable_chars:
                return ocr_text
            else:
                logger.warning(
                    f"   OCR 未改善 ({ocr_usable} vs pdfplumber {usable_chars} 字符)，使用 pdfplumber 结果"
                )

        return text
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
