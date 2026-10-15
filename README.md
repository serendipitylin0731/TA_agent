# 知页 TA Agent

面向初高中教学的本地教材知识库与 AI 问答原型。页面分为 **Chat 问答、查询原文、阅读原版教材**。Chat 优先检索教材，跨章节问题会汇集多个相关页，在回答下方显示参考教材与 PDF 页序；没有合适匹配时由模型直接回答，页面另行标注教材检索未命中。查询支持跨行文字、模糊匹配、输入补全和错别字建议；结果按书合并并显示关键页。教材按“初中区/高中区 → 学科 → 册次”浏览封面，进入双页阅读器后可用两侧按钮或方向键翻页、跳转到下一关键词页。

## 本地运行

需要 Python 3.11+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
python scripts/sync_keben.py --dry-run  # 查看计划接入的教材
python scripts/sync_keben.py            # 下载并索引教材
python scripts/sync_keben.py --book-id 0205  # 接入指定教材
python scripts/sync_general_tech.py     # 补充浙江使用的通用技术教材
python scripts/build_suggestions.py    # 为旧数据补建联想词索引
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。检索与阅读无需模型密钥；Chat 需要服务端密钥。默认模型在 `.env` 中配置，密钥不发送到浏览器。最近 10 条对话和检索记录仅保存在当前浏览器的 `localStorage` 中。点击检索结果或引用会从命中页打开；从教材目录进入则从第一页打开。

## 教材与权限

项目目录覆盖初中、高中共 20 个学科目录位。语文、历史、道德与法治/思想政治使用统编版；其他学科按可核查的人教版或浙江省用书目录建档。目录位与实际已接入教材分别统计，定位页码只来自已索引 PDF。教材文件和 SQLite 数据库存放于本机 `storage/`，不提交到 GitHub。

知识库只接受教材文件，公开页面不提供资料上传、删除或网页导入接口。新增教材由部署维护者运行本地同步脚本；若将来开放多人管理，需要先实现身份验证与权限控制。

教材下载来源为[课本网](https://keben.app/)及其标注的[上游目录](https://github.com/TapXWorld/ChinaTextbook)。教材版权归出版社；请按来源站点的使用条款处理本地文件。扫描 PDF 若无可提取文字，须先做 OCR 才能用于检索。

## 验证

```bash
python -m pytest -q
node --check web/app.js
node --check web/reader.js
PYTHONPATH=. python scripts/evaluate_retrieval.py
```

检索评估覆盖 39 个跨学科问题、目标页、无教材证据和错别字建议。`web/vendor/pdfjs/` 为本地 PDF.js 分发文件，许可证见其 `LICENSE`。

更多信息见[系统架构](docs/architecture.md)、[演示脚本](docs/demo.md)和[教材覆盖快照](docs/coverage.md)。
