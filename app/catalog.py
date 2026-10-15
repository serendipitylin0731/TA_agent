"""Version-aware catalogue slots; these entries are not textbook content."""

MOE_JUNIOR = "https://www.moe.gov.cn/srcsite/A26/s8001/202408/W020240805496325238752.pdf"
MOE_HIGH = "https://www.moe.gov.cn/fbh/live/2019/50754/sfcl/201906/t20190620_386630.html"
ZHEJIANG = "https://jyt.zj.gov.cn/module/download/downfile.jsp?classid=0&filename=0f7705da383c486c96fb7f519d8cf2e0.pdf"

SUBJECTS = [
    ("语文", "统编版", "人民教育出版社"),
    ("数学", "人教版（默认选定）", "人民教育出版社"),
    ("英语", "人教版（默认选定）", "人民教育出版社"),
    ("物理", "人教版（默认选定）", "人民教育出版社"),
    ("化学", "人教版（默认选定）", "人民教育出版社"),
    ("生物学", "人教版（默认选定）", "人民教育出版社"),
    ("道德与法治", "统编版", "人民教育出版社"),
    ("历史", "统编版", "人民教育出版社"),
    ("地理", "人教版（默认选定）", "人民教育出版社"),
]


def catalog_entries():
    entries = []
    for stage in ("初中", "高中"):
        for subject, edition, publisher in SUBJECTS:
            real_subject = "思想政治" if stage == "高中" and subject == "道德与法治" else subject
            entries.append({
                "id": f"{stage}-{real_subject}",
                "stage": stage,
                "subject": real_subject,
                "edition": edition,
                "publisher": publisher,
                "title": f"{stage}{real_subject}教材",
                "catalog_url": MOE_JUNIOR if stage == "初中" else MOE_HIGH,
                "note": "目录已建，正文尚未导入；具体册次和修订年份需按实物核验。",
            })
    for subject in ("信息技术", "通用技术"):
        entries.append({
            "id": f"高中-{subject}",
            "stage": "高中",
            "subject": subject,
            "edition": "浙江省教学用书目录所列版本",
            "publisher": "浙江教育出版社",
            "title": f"浙江高中{subject}教材",
            "catalog_url": ZHEJIANG,
            "note": "依据已检索到的浙江省教学用书目录建立目录位；最新册次须以学校实际用书核验。",
        })
    return entries
