# 知页 TA Agent

## 项目简介

知页 TA Agent 是面向初高中师生的教材知识库与智能问答系统，目标是让教学问题既能得到清楚的回答，也能回到原版教材核对依据。系统目前接入 113 册初高中教材，按学段、学科和册次整理，覆盖语文、数学、英语、物理、化学、生物、政治、历史、地理，以及信息技术和通用技术等领域。项目将 PDF 中可提取的正文转换为带原始页序、章节信息和关键插图的 Markdown，再建立本地分页索引；资料库只收录教材，避免把普通网页误标为课本原文。页面设有 **Chat 问答、查询原文、阅读原版教材** 三个入口：用户可以用自然语言提问，让模型先检索相关页，再把跨章节、跨册次的材料整理为通顺的解释，并在答案下方列出教材名称和 PDF 页码；也可以直接检索关键词，查看按书合并的结果及关键页。检索支持问题改写、多词组检索、跨行文字、模糊匹配、输入补全与错别字建议。若没有足够的教材证据，系统会直接给出模型回答，并在下方单独说明未命中，不编造教材出处。阅读界面按初中区、高中区和学科展示教材封面，采用双页翻阅，支持方向键、页面边缘翻页及跳转到下一关键词页。左侧保留最近十个聊天会话和十次原文检索，便于继续学习。项目把来源定位和原版核验放在回答之后，帮助教师备课、学生复习及跨学科查证；对于没有文字层的扫描页，仍需补做 OCR。

## 本地运行

需要 Python 3.11+、Git LFS 和 zstd。克隆仓库后先取回教材数据并解压分页 Markdown：

```bash
git lfs install
git lfs pull
cat storage/markdown.tar.zst.part-* | tar --zstd -xf - -C storage
```

安装 Python 依赖、配置服务端模型密钥并启动：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。检索与阅读无需模型密钥；Chat 需要服务端密钥。默认模型在 `.env` 中配置，密钥不发送到浏览器。左侧分别保存最近 10 个聊天会话和 10 次原文检索，记录仅在当前浏览器的 `localStorage` 中。点击 Chat 或查询原文导航会新建空白页面，点击侧栏记录可恢复内容。点击检索结果或引用会从命中页打开；从教材目录进入则从第一页打开。

已下载 PDF 经 PyMuPDF 提取文字，生成 `storage/markdown/{教材编号}.md`，每页保留原 PDF 页序、章节、可提取的正文以及部分关键插图的相对链接。检索数据库用这些 Markdown 转换出的分页文本重新建立索引，并保存原始 PDF 页码供定位。教材 PDF、SQLite 索引和 Markdown 压缩包通过 Git LFS 管理；解压后的 Markdown 与图片仍是本地工作目录文件。PDF 中若某一页只有扫描图片而无文本层，其图中文字目前仍需 OCR；图片本身未进入语义索引。

需要更新教材时，维护者可运行 `python scripts/sync_keben.py --dry-run` 查看计划、运行 `python scripts/sync_keben.py` 下载并索引，或以 `--book-id 0205` 接入单本。浙江通用技术教材的补充脚本为 `python scripts/sync_general_tech.py`。更新后运行 `PYTHONPATH=. python scripts/build_markdown.py` 重建分页 Markdown；脚本可中断续跑，单本强制重建用 `--book-id 编号 --force`。重新打包用 `tar -C storage -cf - markdown | zstd -3 -T0 -o storage/markdown.tar.zst`，再用 `split -b 200M -d -a 2 storage/markdown.tar.zst storage/markdown.tar.zst.part-` 生成 LFS 分卷并提交。

## 教材与权限

项目目录覆盖初中、高中共 20 个学科目录位。语文、历史、道德与法治/思想政治使用统编版；其他学科按可核查的人教版或浙江省用书目录建档。目录位与实际已接入教材分别统计，定位页码只来自已索引 PDF。教材 PDF、SQLite 数据库和 Markdown 压缩包位于 `storage/`，通过 Git LFS 上传；运行环境密钥仍只保存在本地 `.env`。

知识库只接受教材文件，公开页面不提供资料上传、删除或网页导入接口。新增教材由部署维护者运行本地同步脚本；若将来开放多人管理，需要先实现身份验证与权限控制。

教材下载来源为[课本网](https://keben.app/)及其标注的[上游目录](https://github.com/TapXWorld/ChinaTextbook)。教材版权归出版社；请按来源站点的使用条款处理本地文件。扫描 PDF 若无可提取文字，须先做 OCR 才能用于检索。

## 验证

```bash
python -m pytest -q
node --check web/app.js
node --check web/reader.js
PYTHONPATH=. python scripts/evaluate_retrieval.py
PYTHONPATH=. python scripts/evaluate_questions.py
PYTHONPATH=. python scripts/evaluate_answers.py  # 需要配置模型 API，抽查真实回答
```

检索评估覆盖 39 个基础问题和 138 个扩展问题，还检查指定页、无教材证据和错别字建议。真实回答脚本覆盖 14 个跨学科及未命中案例。`web/vendor/pdfjs/` 为本地 PDF.js 分发文件，许可证见其 `LICENSE`。

更多信息见[系统架构](docs/architecture.md)、[演示脚本](docs/demo.md)、[验证记录](docs/evaluation.md)和[教材覆盖快照](docs/coverage.md)。
