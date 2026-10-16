"""Build page-aware Markdown documents and retrieval chunks from local textbooks."""

import hashlib
import re
from pathlib import Path

import pymupdf

from .ingest import split_text

CHAPTER = re.compile(r"^第[一二三四五六七八九十百\d]+(?:章|节|单元)\s*[^\n]{0,35}")
NUMBERED = re.compile(r"^[一二三四五六七八九十]+[、．.]\s*([^\n]{2,35})")
SHORT_TOPIC = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9·、（）()\s]{2,18}$")
RUNNING_HEADERS = {"通用技术", "必修", "选择性必修", "学习目标", "思考与讨论", "思考", "探究"}


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t|·● ")


def update_section(text: str, chapter: str, topic: str) -> tuple[str, str]:
    """Keep the last real chapter/topic heading, ignoring page headers and contents."""
    lines = [clean_line(line) for line in text.splitlines() if clean_line(line)]
    if any("目录" in line for line in lines[:4]) and len(lines) > 12:
        return chapter, topic
    for line in lines[:18]:
        if line in RUNNING_HEADERS or re.fullmatch(r"(?:技术与设计|第?\d+页|\d{1,3})\s*\d*", line):
            continue
        chapter_match = CHAPTER.match(line)
        if chapter_match and len(chapter_match.group(0)) < 40:
            new_chapter = chapter_match.group(0).split("学习目标")[0].strip()
            if new_chapter != chapter:
                topic = ""
            chapter = new_chapter
            continue
        numbered = NUMBERED.match(line)
        if numbered:
            candidate = numbered.group(1).split("学习目标")[0].split("任务一")[0].strip()
            if 2 <= len(candidate) <= 25:
                topic = candidate
                continue
        if topic and SHORT_TOPIC.fullmatch(line) and len(line) <= 12 and line.endswith(("原则", "定律", "性质", "结构")):
            # A page may contain several subtopics; keep the parent topic for retrieval.
            continue
    return chapter, topic


def key_images(document: pymupdf.Document, page: pymupdf.Page, page_number: int,
               image_dir: Path, max_images: int = 4) -> list[tuple[float, str]]:
    """Extract sizeable embedded figures; ignore tiny ornaments and full-page scans."""
    selected = []
    seen = set()
    page_area = page.rect.width * page.rect.height
    for record in page.get_images(full=True):
        xref, width, height = record[0], record[2], record[3]
        if xref in seen or width < 180 or height < 110 or width * height < 25000:
            continue
        seen.add(xref)
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        if rect.width * rect.height > page_area * .78:
            continue
        selected.append((rect.width * rect.height, rect.y0, xref))
    selected.sort(reverse=True)
    output = []
    for _, y, xref in selected[:max_images]:
        try:
            raw = document.extract_image(xref)
            ext = raw.get("ext", "png").lower()
            data = raw["image"]
            if ext not in {"png", "jpg", "jpeg", "webp"}:
                pixmap = pymupdf.Pixmap(document, xref)
                if pixmap.n not in (1, 3):
                    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
                data = pixmap.tobytes("png")
                ext = "png"
            name = f"p{page_number:04d}-{hashlib.sha256(data).hexdigest()[:12]}.{ext}"
            image_dir.mkdir(parents=True, exist_ok=True)
            path = image_dir / name
            if not path.exists():
                path.write_bytes(data)
            output.append((y, name))
        except Exception:
            continue
    return output


def page_markdown(page: pymupdf.Page, page_number: int, images: list[tuple[float, str]],
                  image_relative_dir: str, section: str) -> str:
    elements = []
    for block in page.get_text("blocks", sort=True):
        if len(block) > 6 and block[6] != 0:
            continue
        body = block[4].strip()
        if body:
            elements.append((block[1], body))
    for index, (y, name) in enumerate(images, 1):
        elements.append((y, f"![PDF 第 {page_number} 页插图 {index}]({image_relative_dir}/{name})"))
    elements.sort(key=lambda item: item[0])
    heading = f"## PDF 第 {page_number} 页"
    if section:
        heading += f"\n\n> 章节：{section}"
    return heading + "\n\n" + "\n\n".join(text for _, text in elements) + "\n"


def convert_book(source: dict, output_root: Path, with_images: bool = True) -> tuple[Path, list[tuple[int, str, str]], int]:
    source_id = source["id"]
    path = Path(source["file_path"])
    markdown_path = output_root / f"{source_id}.md"
    image_dir = output_root / "images" / str(source_id)
    image_relative_dir = f"images/{source_id}"
    page_chunks = []
    image_count = 0
    chapter = topic = ""
    parts = [f"# {source['title']}",
             f"教材编号：{source_id} · {source['stage']} · {source['subject']} · {source['edition']} · {source['volume']}",
             "页码采用 PDF 原始页序。插图从原文件提取，图文位置以原版教材为准。"]
    with pymupdf.open(path) as document:
        for page_number, page in enumerate(document, 1):
            content = page.get_text("text", sort=True).strip()
            chapter, topic = update_section(content, chapter, topic)
            section = " / ".join(filter(None, (chapter, topic)))
            images = key_images(document, page, page_number, image_dir) if with_images else []
            image_count += len(images)
            parts.append(page_markdown(page, page_number, images, image_relative_dir, section))
            if content:
                page_chunks.extend((page_number, "§ " + section if section else "", segment)
                                   for segment in split_text(content, size=850, overlap=70))
    output_root.mkdir(parents=True, exist_ok=True)
    temp = markdown_path.with_suffix(".md.part")
    temp.write_text("\n\n".join(parts), encoding="utf-8")
    temp.replace(markdown_path)
    return markdown_path, page_chunks, image_count
