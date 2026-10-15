import re
from pathlib import Path

import pymupdf


def split_text(text: str, size: int = 650, overlap: int = 80) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            split_at = max(text.rfind("。", start + size // 2, end), text.rfind("\n", start + size // 2, end))
            if split_at > start:
                end = split_at + 1
        body = text[start:end].strip()
        if body:
            chunks.append(body)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def pdf_chunks(path: Path) -> list[tuple[int, str, str]]:
    document = pymupdf.open(path)
    if document.page_count > 1200:
        raise ValueError("单份 PDF 最多 1200 页")
    result = []
    for index, page in enumerate(document):
        content = page.get_text("text", sort=True).strip()
        if not content:
            continue
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
        section = first_line[:70] if len(first_line) < 100 else ""
        result.extend((index + 1, section, part) for part in split_text(content))
    if not result:
        raise ValueError("无法提取文字；扫描版 PDF 需要先做 OCR")
    return result


def plain_chunks(text: str) -> list[tuple[None, str, str]]:
    return [(None, "", part) for part in split_text(text)]
