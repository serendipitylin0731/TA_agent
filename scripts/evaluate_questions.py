"""Broad retrieval audit: subject, topical page, answers, typo and absence cases.

Usage: PYTHONPATH=. .venv/bin/python scripts/evaluate_questions.py
"""

from collections import Counter

from app import db


QUESTIONS = {
    "语文": [
        "《背影》的作者是谁？", "《济南的冬天》描写了什么？", "《故乡》的作者是谁？",
        "《岳阳楼记》的作者是谁？", "《出师表》的作者是谁？", "《木兰诗》讲了什么？",
        "《桃花源记》的作者是谁？", "《孔乙己》的作者是谁？", "《沁园春·雪》的作者是谁？",
        "《论语》十二章讲了什么？", "《春》的作者是谁？", "《从百草园到三味书屋》的作者是谁？",
    ],
    "数学": [
        "函数的定义是什么？", "一次函数的定义是什么？", "反比例函数的定义是什么？",
        "二次函数的顶点式是什么？", "椭圆的第二定义是什么？", "双曲线的定义是什么？",
        "抛物线的定义是什么？", "导数的定义是什么？", "勾股定理是什么？",
        "三角形内角和是多少？", "等差数列的通项公式是什么？", "概率的定义是什么？",
    ],
    "英语": [
        "一般过去时的用法是什么？", "现在完成时的用法是什么？", "现在进行时如何使用？",
        "过去进行时的用法是什么？", "被动语态怎么构成？", "形容词比较级怎么用？",
        "定语从句是什么？", "一般将来时如何使用？", "名词复数怎么变化？",
        "非谓语动词有哪些形式？",
    ],
    "物理": [
        "欧姆定律是什么？", "牛顿第一定律是什么？", "动量守恒定律是什么？",
        "电磁感应是什么？", "浮力的大小如何计算？", "光的反射定律是什么？",
        "惯性是什么？", "压强的定义是什么？", "机械能守恒定律是什么？",
        "电流和电压有什么关系？", "焦耳定律是什么？", "电功率的定义是什么？",
    ],
    "化学": [
        "中和反应是什么？", "氧化还原反应的定义是什么？", "摩尔的定义是什么？",
        "化学平衡的影响因素有哪些？", "质量守恒定律是什么？", "酸有哪些通性？",
        "碱有哪些通性？", "离子键是什么？", "共价键是什么？",
        "电解质是什么？", "原电池的工作原理是什么？", "阿伏加德罗常数是多少？",
    ],
    "生物学": [
        "光合作用的过程是什么？", "细胞膜有什么作用？", "减数分裂的过程是什么？",
        "DNA的双螺旋结构是什么？", "生态系统能量流动的特点有哪些？", "有丝分裂的过程是什么？",
        "孟德尔分离定律是什么？", "呼吸作用的过程是什么？", "食物链是什么？",
        "自然选择学说是什么？", "基因是什么？", "神经元的结构是什么？",
    ],
    "道德与法治": [
        "宪法的地位是什么？", "公民的基本权利有哪些？", "公民的基本义务有哪些？",
        "未成年人保护法保护什么？", "法律的特征有哪些？", "依法治国是什么？",
        "社会主义核心价值观有哪些？", "我国的国家机构有哪些？", "什么是公平正义？",
        "人民代表大会制度是什么？",
    ],
    "思想政治": [
        "人民代表大会制度是什么？", "全面依法治国的意义是什么？", "市场在资源配置中起什么作用？",
        "社会主义核心价值观有哪些？", "文化自信是什么？", "社会存在与社会意识的关系是什么？",
        "中国共产党的领导地位是什么？", "新发展理念包括什么？", "我国的基本经济制度是什么？",
        "国家利益和国际关系的关系是什么？",
    ],
    "历史": [
        "中国古代科举制度如何发展？", "鸦片战争爆发的原因是什么？", "辛亥革命的意义是什么？",
        "秦朝统一采取了哪些措施？", "商鞅变法的内容是什么？", "洋务运动的目的是什么？",
        "五四运动的意义是什么？", "明治维新的主要措施是什么？", "工业革命的影响是什么？",
        "新文化运动的主要内容是什么？", "抗日战争胜利的意义是什么？", "隋朝科举制度如何形成？",
    ],
    "地理": [
        "水循环的过程是什么？", "季风气候形成的原因是什么？", "地球自转有哪些地理意义？",
        "地球公转会产生什么现象？", "我国气候的主要特征是什么？", "锋面雨是怎么形成的？",
        "板块构造学说是什么？", "河流地貌如何形成？", "太阳辐射对地球有什么影响？",
        "气压带和风带如何形成？", "人口迁移的主要原因是什么？", "洋流对气候有什么影响？",
    ],
    "信息技术": [
        "算法的基本特征有哪些？", "算法和程序有什么区别？", "信息编码是什么？",
        "数据结构有哪些？", "人工智能的应用有哪些？", "计算机网络是什么？",
        "网络安全如何保护？", "循环结构是什么？", "数据库是什么？",
        "数据可视化有什么作用？", "机器学习是什么？", "云计算是什么？",
    ],
    "通用技术": [
        "什么是设计的一般原则？", "设计的一般原则有哪些？", "设计的一般原则包括什么？",
        "实用原则是什么？", "创新原则是什么？", "经济原则是什么？",
        "道德原则是什么？", "美观原则是什么？", "技术规范原则是什么？",
        "可持续发展原则是什么？", "设计的一般过程有哪些？", "人机关系是什么？",
    ],
}

GOLD = {
    "什么是设计的一般原则？": (39, "实用 创新 经济 道德 美观 技术规范 可持续发展"),
    "设计的一般原则有哪些？": (39, "实用 创新 经济 道德 美观 技术规范 可持续发展"),
    "设计的一般原则包括什么？": (39, "实用 创新 经济 道德 美观 技术规范 可持续发展"),
    "椭圆的第二定义是什么？": (122, "焦点 准线 距离"),
    "三角形内角和是多少？": (18, "180"),
    "欧姆定律是什么？": (105, "电流 电压 电阻"),
    "牛顿第一定律是什么？": (25, "匀速 运动"),
}


def main():
    stats = Counter()
    failures = []
    total = sum(map(len, QUESTIONS.values()))
    for subject, questions in QUESTIONS.items():
        for question in questions:
            results = [item for item in db.search(question, limit=15) if item["relevance"] == "strong"]
            top = results[0] if results else None
            stats["strong"] += bool(top)
            stats["subject"] += bool(top and top["subject"] == subject)
            scoped = [item for item in db.search(question, subject=subject, limit=15)
                      if item["relevance"] == "strong"]
            stats["scoped"] += bool(scoped)
            gold = GOLD.get(question)
            if gold:
                page, words = gold
                gold_match = next((item for item in results[:5] if item["subject"] == subject and item["page"] == page), None)
                stats["gold_page"] += bool(gold_match)
                if gold_match:
                    text = db.get_chunks([gold_match["id"]])[0]["text"]
                    stats["gold_terms"] += all(db.normalize_search(word) in db.normalize_search(text)
                                               for word in words.split())
            if not top or top["subject"] != subject or gold and not gold_match:
                failures.append((subject, question, f"{top['subject']} p{top['page']}" if top else "无强匹配"))
    print(f"问题总数 {total}；有强证据 {stats['strong']}/{total}；首位学科 {stats['subject']}/{total}")
    print(f"限定对应学科后有强证据 {stats['scoped']}/{total}")
    print(f"指定页前五 {stats['gold_page']}/{len(GOLD)}；答案关键词齐全 {stats['gold_terms']}/{len(GOLD)}")
    print("需要复核：")
    for subject, question, found in failures:
        print(f"  [{subject}] {question} -> {found}")
    for query in ("量子计算机如何制造？", "完全不存在的玄月青铜定律是什么？"):
        print("无教材证据", query, not any(item["relevance"] == "strong" for item in db.search(query, limit=10)))
    print("错别字建议", db.suggest("光合做用")["corrections"][:3])


if __name__ == "__main__":
    main()
