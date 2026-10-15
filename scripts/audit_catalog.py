"""Print a reproducible Markdown snapshot of locally available textbooks."""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402


def report() -> str:
    db.init_db()
    books = [item for item in db.list_sources() if item["kind"] == "textbook"]
    by_catalog: dict[str, list[dict]] = {}
    missing_files = []
    for book in books:
        by_catalog.setdefault(book["catalog_id"], []).append(book)
        full = db.get_source(book["id"])
        if not full["file_path"] or not Path(full["file_path"]).is_file():
            missing_files.append(book["title"])
    lines = [
        "# 本地教材覆盖快照", "",
        f"生成日期：{date.today().isoformat()}。此表反映本机已下载并入库的文件，不代表出版目录已经逐册齐全。", "",
        f"教材共 **{len(books)}** 份；覆盖 **{len([v for v in by_catalog.values() if v])}/{len(db.list_catalog())}** 个学段与学科目录位；"
        f"可检索片段 **{sum(book['chunk_count'] for book in books)}** 个；"
        f"仅可阅读、尚无文本索引 **{sum(book['chunk_count'] == 0 for book in books)}** 份。", "",
        "| 学段 | 学科 | 建档版本 | 已接入 | 可检索 | 册次（以来源目录标注为准） |", "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in db.list_catalog():
        group = by_catalog.get(item["id"], [])
        volumes = "；".join(book["volume"].replace("|", "\\|") for book in sorted(group, key=lambda x: x["volume"])) or "—"
        lines.append(f"| {item['stage']} | {item['subject']} | {item['edition']} | {len(group)} | "
                     f"{sum(book['chunk_count'] > 0 for book in group)} | {volumes} |")
    lines.extend(["", f"本地文件缺失：**{len(missing_files)}** 份。",
                  "", "本表不包含开放网络资料；PDF 文件和 SQLite 数据库均位于被 Git 忽略的 `storage/`。",
                  "教材版权归相应出版社；来源参见各资料记录和 [课本网说明](https://keben.app/disclaimer)。", ""])
    junior_history = by_catalog.get("初中-历史", [])
    if not any("八年级" in book["volume"] and "下册" in book["volume"] for book in junior_history):
        lines.extend(["已知册次缺口：初中历史八年级下册。课本网在本次核查时仅提供 2027 修订版，"
                      "未纳入本次同步；后续应按学校实际用书补齐。", ""])
    if missing_files:
        lines.extend(["", "缺失文件：" + "、".join(missing_files)])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="write Markdown to a file instead of stdout")
    arguments = parser.parse_args()
    content = report()
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(content, encoding="utf-8")
        print(arguments.output)
    else:
        print(content)
