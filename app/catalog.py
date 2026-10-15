"""Version-aware catalogue slots; these entries are not textbook content."""

MOE_JUNIOR = "https://www.moe.gov.cn/jyb_xwfb/s271/201708/t20170828_312487.html"
MOE_HIGH = "https://www.moe.gov.cn/fbh/live/2019/50754/sfcl/201906/t20190620_386630.html"
PEP_CATALOG = "https://www.pep.com.cn/products/jc/"
ZHEJIANG_IT = "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3185/site/attach/0/6228b91eb0e646a4bbf3f4578c20ece3.pdf"
ZHEJIANG_GT = "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3185/site/attach/0/b92c77b7999b4d30ba3d7f95b6c7eb89.pdf"

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
                "catalog_url": (MOE_JUNIOR if stage == "初中" else MOE_HIGH) if edition == "统编版" else PEP_CATALOG,
                "note": "目录已建，正文尚未导入；具体册次和修订年份需按实物核验。",
            })
    for subject, edition, publisher in (
        ("信息技术", "浙教版（浙江使用）", "浙江教育出版社"),
        ("通用技术", "苏教版（浙江使用）", "江苏凤凰教育出版社"),
    ):
        entries.append({
            "id": f"高中-{subject}",
            "stage": "高中",
            "subject": subject,
            "edition": edition,
            "publisher": publisher,
            "title": f"浙江高中{subject}教材",
            "catalog_url": ZHEJIANG_IT if subject == "信息技术" else ZHEJIANG_GT,
            "note": "依据浙江省公开教材版别资料建立目录位；最新册次须以学校实际用书核验。",
        })
    return entries
