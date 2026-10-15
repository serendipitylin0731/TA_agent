"""Run a broad, reproducible retrieval audit against the installed textbook DB.

Usage: PYTHONPATH=. .venv/bin/python scripts/evaluate_retrieval.py
"""

from app import db


CASES = [
    ("函数的定义是什么？", "数学", 80), ("一次函数的定义是什么？", "数学", 97),
    ("反比例函数的定义是什么？", "数学", 9), ("勾股定理是什么？", "数学", None),
    ("三角形内角和是多少？", "数学", 18), ("二次函数的顶点式是什么？", "数学", 43),
    ("椭圆的定义", "数学", 110), ("椭圆的第二定义", "数学", 122),
    ("双曲线的定义", "数学", 124), ("抛物线的定义", "数学", None),
    ("导数的定义", "数学", 70), ("光合作用的过程是什么？", "生物学", None),
    ("什么是细胞膜？", "生物学", None), ("减数分裂的过程", "生物学", None),
    ("DNA的双螺旋结构", "生物学", 57), ("生态系统能量流动的特点", "生物学", None),
    ("欧姆定律是什么？", "物理", 105), ("牛顿第一定律是什么？", "物理", 25),
    ("动量守恒定律是什么？", "物理", 18), ("电磁感应是什么？", "物理", None),
    ("中和反应是什么？", "化学", 81), ("氧化还原反应的定义", "化学", 29),
    ("摩尔的定义", "化学", 60), ("化学平衡的影响因素", "化学", None),
    ("鸦片战争爆发的原因", "历史", 9), ("辛亥革命的意义", "历史", 62),
    ("科举制度的发展", "历史", None), ("中国近代社会的性质", "历史", None),
    ("秦朝统一的措施", "历史", None), ("季风气候的成因", "地理", None),
    ("地球自转的地理意义", "地理", 26), ("水循环的过程", "地理", 51),
    ("依法治国的意义", "思想政治", None), ("人民代表大会制度是什么", "思想政治", 12),
    ("济南的冬天描写了什么", "语文", 13), ("背影的作者是谁", "语文", 91),
    ("一般过去时的用法", "英语", None), ("算法的基本特征", "信息技术", 47),
    ("设计的一般原则", "通用技术", 39),
]


def main():
    subject_hits = page_hits = checked_pages = 0
    for question, subject, page in CASES:
        results = [item for item in db.search(question, limit=20) if item["relevance"] == "strong"]
        subject_ok = bool(results and results[0]["subject"] == subject)
        page_ok = page is None or any(item["subject"] == subject and item["page"] == page for item in results[:5])
        subject_hits += subject_ok
        if page is not None:
            checked_pages += 1
            page_hits += page_ok
        lead = f"{results[0]['subject']} p{results[0]['page']}" if results else "无强匹配"
        print(f"{'OK' if subject_ok and page_ok else 'CHECK'}  {question:<22} -> {lead}")
    print(f"学科首位 {subject_hits}/{len(CASES)}，目标页前五 {page_hits}/{checked_pages}")
    for question in ("量子计算机如何制造？", "完全不存在的玄月青铜定律是什么？"):
        strong = [item for item in db.search(question, limit=20) if item["relevance"] == "strong"]
        print(f"无教材证据：{question} -> {'通过' if not strong else '异常'}")
    print("错别字建议：光合做用 ->", db.suggest("光合做用")["corrections"][:3])


if __name__ == "__main__":
    main()
