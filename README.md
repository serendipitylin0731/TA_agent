# 知页 TA Agent

面向初高中教学的本地教材知识库与 AI 问答原型。界面分为 **Chat 问答、查询原文、阅读原版教材**：Chat 先检索相关片段，再由 AI 整理回答，并在回答下方标明参考资料的位置；查询支持输入补全与错别字建议，PDF 可在页面内按原始页序阅读。

项目设计见[系统架构](docs/architecture.md)，比赛展示可参考[演示脚本](docs/demo.md)，[教材覆盖快照](docs/coverage.md)记录本机接入情况，也可用 `python scripts/audit_catalog.py` 重新核查。

## 当前资料状态

- 建有初中、高中共 20 个学科目录位，区分版本与出版社。教育部统编版仅覆盖初中语文、道德与法治、历史，以及高中语文、思想政治、历史。其他学科默认按人教版建档；浙江高中信息技术为浙教版，通用技术为苏教版。目录位不等于已取得教材正文。
- `scripts/seed_open.py` 从中文维基百科公开 API 导入一组示例资料，保留原文链接、贡献者及 CC BY-SA 4.0 标识。这些资料与教材正文分开展示。
- **GitHub 仓库不包含教材 PDF**。教材文件保存在本机 `storage/uploads/`。具有相应使用权限的文件可在本地资料管理页导入；PDF 文本会建立页序索引，扫描 PDF 需要先 OCR。
- 可从[国家中小学智慧教育平台](https://basic.smartedu.cn/)和[人教社电子教材页面](https://www.pep.com.cn/szkjxzy/dzjc/ywjy/)查阅官方在线教材。站点页面与授权范围由运营方决定，项目不会把这些页面冒充为本地已接入的正文。

## 本地运行

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
python scripts/seed_open.py
python scripts/sync_keben.py --dry-run  # 预览匹配的教材
python scripts/sync_keben.py            # 下载并索引本地教材
python scripts/sync_keben.py --book-id 0205  # 单独接入用户指定的历史八下 2027 版
python scripts/sync_general_tech.py     # 补充浙江使用的苏教版通用技术
python scripts/build_suggestions.py      # 为既有资料补建联想词索引
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

访问 `http://127.0.0.1:8765/`。检索和原文阅读无需 DeepSeek 密钥；模型问答需要有效密钥。默认模型为 `deepseek-flash`，通过官方兼容的 Chat Completions 接口直接调用。密钥只在服务端读取，不应提交到 Git。

批量脚本只选网站标注为当前使用、修订年份不晚于本年的教材；初中选六三制，数学选人教 A 版。`--book-id` 用于明确指定单本教材，可接入未来标注的修订版，页面会保留实际年份。下载资料来自[课本网](https://keben.app/)和它标明的[上游目录](https://github.com/TapXWorld/ChinaTextbook)。[课本网的说明](https://keben.app/disclaimer)称其资源供个人学习研究、版权归出版社；本项目仅在本地缓存和索引，不把教材文件推送到 GitHub。下载、解析可能需要几分钟，并受源站可用性影响。

## 功能与边界

| 功能 | 实现 |
| --- | --- |
| 查询原文 | 中文分词、FTS5 与文本匹配检索；导入的开放资料直接在页面内阅读，保留来源链接和许可。 |
| 教材阅读 | 上传 PDF/TXT/Markdown 后归入指定学段、学科和册次；PDF 在页面内打开并支持页序定位。 |
| 来源问答 | 取相关片段发给 DeepSeek，回答附 `[n]` 证据；没有相关片段时不调用模型猜答案。 |
| 模型常识 | 独立模式，标注为未核对教材，不给出虚构教材页码。 |

本地服务只绑定 `127.0.0.1`。上传文件和 SQLite 数据库存于 `storage/`，被 `.gitignore` 排除。若以后部署为多人服务，需先加入账户权限、文件访问控制和数据隔离。

## 资料依据

- [教育部：义务教育三科统编教材](https://www.moe.gov.cn/jyb_xwfb/s271/201708/t20170828_312487.html)
- [教育部：普通高中三科统编教材](https://www.moe.gov.cn/fbh/live/2019/50754/sfcl/201906/t20190620_386630.html)
- [浙江省高中信息技术版别示例](https://fzggw.zj.gov.cn/module/download/downfile.jsp?classid=0&filename=87f4c93d3626414ab3159dbec0f51e95.pdf)
- [浙江省高中通用技术版别示例](https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3185/site/attach/0/b92c77b7999b4d30ba3d7f95b6c7eb89.pdf)
- [DeepSeek API 文档](https://api-docs.deepseek.com/guides/codex)

## 验证

```bash
python -m pytest -q
node --check web/app.js
```
