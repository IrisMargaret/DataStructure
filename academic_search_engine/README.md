# 学术论文关键词索引与检索系统

数据结构课程设计项目：基于**倒排索引 + Trie 前缀树 + 布尔查询解析器 + TF-IDF + Porter 词干提取**的本地化论文检索工具。
后端 Python + Flask，中文分词 jieba，数据源 arXiv / OpenAlex（含真实中文文献），前端为无框架单页应用（暖纸色学术排版，三视图：检索 / 文库 / 结构说明）。

---

## 功能总览

| 类别 | 功能 |
| --- | --- |
| 核心索引 | 倒排索引 `term → List<Posting(paper_id, tf, positions)>`（手写）；多关键词 AND，**最短 Posting List 优先双指针归并，O(n)** |
| 预处理 | 中英文混合：英文小写 + **Porter 词干提取（手写）**，中文 jieba 分词；停用词过滤 |
| 相关性排序 | 词频 TF 求和 / **TF-IDF 加权**（`idf = ln((N+1)/(df+1)) + 1`）一键切换 |
| 复杂查询 | 递归下降解析：`AND / OR / NOT / 括号 / 引号短语`（PositionList 相邻位置匹配，中英皆可） |
| **中英互译检索** | 离线双语词典（171 对词条）：中文关键词自动扩展英文同义词命中英文文献；英文查询开启「中英互译」后命中中文文献 |
| 模糊提示 | Trie 前缀补全 Top 10；前缀未命中自动**子串包含兜底**（中英文通用） |
| 关键词提取 | 入库时按“篇内 TF × 语料 IDF、标题加权”自动提取 Top 8，关键词并入索引可检索 |
| 检索剖析 | 每次查询返回 trace：各词 df、Posting 长度、归并顺序、布尔 AST、互译扩展词 |
| 动态入库 | PDF / 纯文本(TXT/MD) / **ZIP 压缩包批量** / arXiv URL / 手动填写；**上传原文归档于 `data/papers_files/`，结果与文库可点击「阅读原文」直接查看/下载** |
| **严格去重** | 仅当 规范化标题+作者+年份+摘要 四项**完全一致**才判重（不新增并提示已存在）；同名不同文、同文不同措辞允许并存 |
| 元数据拆解 | 自动提取标题/摘要/作者/年份；**中文乱码修复**（多编码探测 + mojibake 还原 + 噪声行过滤 + 中英双语标题/中文版式处理）；置信度不足或开启时交由 **LLM Agent 精修**（.env 配置） |
| 多源数据采集 | **arXiv**（分类+主题）与 **OpenAlex**（含 `language:zh` 中文文献）双源，可单源/全量抓取，跨源按“内容完全一致”去重 |
| 文库管理 | 分页浏览、标题/作者过滤、**页码手动跳转**、单篇详情（含原文链接与语言/来源标签）、删除（清理索引/文件） |
| 中文支持 | 中文文献导入、中文关键词检索/补全/互译、全中文界面 |

---

## 目录结构与模块层次

```
academic_search_engine/
├── run.py                    # 入口：python run.py [--port 5000] [--no-crawl]
├── requirements.txt  start.bat  .env.example  .gitignore  smoke_test.py
│
├── core/                     # ① 核心算法层（纯手写）
│   ├── paper.py              #    论文实体（含内容键 paper_content_key，严格去重用）
│   ├── preprocessor.py       #    中英分词、停用词、词干化（可选返回原词/位置）
│   ├── stemmer.py            #    Porter 词干提取（官方向量全过）
│   ├── inverted_index.py     #    倒排索引：构建 / AND 归并 / 布尔 / TF-IDF / trace / 并集检索
│   ├── trie.py               #    前缀树自动补全
│   ├── query_parser.py       #    递归下降布尔解析器
│   ├── translator.py         #    中英互译词典查询（core 内离线，零依赖）
│   └── keyword_extractor.py  #    论文关键词提取
│
├── ingest/                   # ② 文档解析入库
│   ├── pdf_extractor.py      #    PDF 文本/元数据（pypdf 优先；乱码还原 + 噪声清理）
│   ├── text_parser.py        #    纯文本启发式拆解（中英文版式、双语标题）
│   ├── document_parser.py    #    统一拆解流水线（规则 → 低置信度转 Agent）
│   ├── zip_importer.py       #    ZIP 安全解包（防路径穿越、上限）
│   ├── encodings.py          #    编码择优解码与 mojibake 还原
│   └── clean_text.py         #    文本噪声行过滤
│
├── crawler/                  # ③ 数据采集（框架化，注册表可扩展）
│   ├── registry.py           #    源注册表 + 跨源严格内容合并
│   ├── arxiv_crawler.py      #    arXiv 源
│   └── openalex_crawler.py   #    OpenAlex 源（含中文主题与 language:zh）
│
├── agent/                    # ④ 拆解 Agent（可选，配置全在 .env）
│   ├── llm.py  prompts.py  paper_agent.py
│
├── service/                  # ⑤ 检索服务门面（唯一入口，RLock + 原子持久化）
│   └── search_service.py     #    检索/补全/文库/入库/文件归档/去重/采集
│
├── web/                      # ⑥ Web 接口层（薄路由）
│   ├── __init__.py  routes.py
│
├── templates/  static/       #    UI：三视图单页
├── data/                     # ⑦ 数据存储
│   ├── papers.json           #    论文元数据（含 keywords/file/language/source）
│   ├── stopwords.txt  bilingual.json
│   └── papers_files/         #    上传原文归档（运行时生成）
└── uploads/                  #    解析临时目录（运行时生成）
```

层间依赖单向：`web → service → core | ingest | crawler | agent`。索引与检索算法全部手写；仅 PDF 解析（pypdf/PyPDF2）、HTTP（requests）、大模型调用使用外部库。

---

## 快速开始

### 1. 安装依赖（Python 3.9+）

```bash
cd academic_search_engine
pip install -r requirements.txt
```

### 2. 启动

**Windows：双击 `start.bat`**，或：

```bash
python run.py                # 数据不足 150 篇时自动采集后启动
python run.py --no-crawl     # 数据已就绪时跳过采集检查
```

浏览器访问 **http://127.0.0.1:5000**。

### 3.（可选）启用大模型拆解 Agent

复制 `.env.example` 为 `.env` 并填写（任意 OpenAI 兼容服务；密钥只存于此文件，已被 gitignore）：

```ini
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxx
LLM_MODEL=your-model-name
```

未配置时系统自动使用规则拆解，全部功能可用。

---

## 使用说明

- **检索视图**：多词 AND、布尔、引号短语、中文关键词均支持；**「中英互译」开关**：中文查询自动扩展英文同义词命中英文文献，英文查询开启后命中中文文献（结果下方 trace 展示互译扩展词）；右上切换 TF / TF-IDD；「查看索引快照」展示倒排原始结构 Top 20。
- **文库视图**：浏览/过滤/详情/删除；分页支持**页码输入跳转**；「动态添加论文」支持 PDF / TXT / ZIP / arXiv URL / 手动；「爬取数据」可选 arXiv / OpenAlex（含中文）/ 全部源，导入结果报告分「成功 / 内容重复跳过 / 失败」三组。
- **原文阅读**：上传过的论文在结果卡、文库行、详情弹窗均提供「阅读原文」链接，点击在新页打开归档 PDF/文本；arXiv 来源则跳转 arXiv 原文页。
- **去重说明**：仅当导入文献与库内某篇在 规范化标题、作者、年份、摘要 上**完全一致**时才判定重复（拦截并提示已有编号）；同名不同文不会误判。
- **结构说明视图**：模块层次、接口契约、算法与数据结构图文说明。

---

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/search?q=&mode=tf\|tfidf&cross=0\|1` | 检索（trace 含互译扩展）；`cross=1` 或查询含中文时跨语言 |
| GET | `/api/suggest?prefix=` | Trie 补全（前缀未命中自动子串包含兜底） |
| GET | `/api/index?limit=` | 倒排索引原始结构快照 |
| GET | `/api/stats` · `/api/meta` | 统计 / 元信息（含 `llm_configured`、`languages`） |
| GET | `/api/papers?page=&size=&q=` · `/api/papers/<id>` | 文库列表 / 详情 |
| GET | `/api/papers/<id>/file` | **原文文件下载/内联查看**（仅库内归档） |
| POST | `/api/papers/manual` | 手动添加 |
| POST | `/api/papers/url` | arXiv URL/编号添加 |
| POST | `/api/papers/file` | 上传 PDF / TXT / ZIP（`ai=0\|1`）；重复返回 `{duplicate:true, existing}`，zip 返回 `{added, duplicated, failed}` |
| DELETE | `/api/papers/<id>` | 删除（清理索引/内容键/原文文件） |
| POST | `/api/crawl` | body `{"source": "arxiv"\|"openalex"\|"all", "pages": 1-5}`（翻页采集新文献） |
| GET | `/api/crawl/status` | 采集状态（含 `added/skipped/source/message` 报告） |

错误统一返回 `{"error": "..."}`。

---

## 测试

```bash
python smoke_test.py
```

64 项离线断言，覆盖 A core 算法（含布尔词干化/NOT 语义）、B ingest、C service+web 全 API、D 跨语言互译、E 中文拆解·归档·去重·补全、F 摘要截取·外链·去噪·错误映射·日志、G Top-K 截断·上传卫生·目录隔离·参数健壮。全部使用隔离临时数据，不污染 `data/papers.json`。

---

## 常见问题

- **首次启动较慢**：论文不足 150 篇自动采集（arXiv，1~3 分钟）。
- **爬取后总数不增加**：属正常——同一源同一批“最新/最相关”论文不会重复入库（会提示“内容重复跳过 n 篇”）。需要更多新文献请换源（OpenAlex/全部源）或提高 `pages`（翻页深度），或稍后 arXiv 更新后再采集。
- **标题可点击**：arXiv 论文链到 arxiv.org/abs；OpenAlex/DOI 论文链到 doi.org；上传且无外部来源的论文标题不可点，但行内提供「阅读原文」打开归档文件。
- **摘要策略**：规则解析只摘录显式“摘要/Abstract”段；无摘要标记的文档摘要为空并自动转 AI 精修；含“1 Introduction/引言”的纯片段不会被当作摘要或标题，会提示改用规范文档。
- **OpenAlex 中文文献**：在文库「爬取数据」选择 OpenAlex 或「全部源」，自动补充中文主题的真实中文题录与摘要（部分中文期刊无摘要属数据源现状）。
- **扫描版 PDF**（无文本层）无法提取，会给出中文提示（可改用 AI 精修或手动填写）。
- **中文文献导入**：支持 UTF-8/GB18030/UTF-16 等常见编码与中文 PDF；解析失败时返回中文可读提示，完整异常与文件记录在 **`logs/app.log`**——若仍失败请保留该日志便于定位。
- **跨语言检索**依赖 `data/bilingual.json` 离线词典；需要更多词对可自行补充该文件（`{"pairs": [["英文","中文"], …]}`）。
- **词干化说明**：检索 “transformer” 与 “transformers” 等价；界面保留原词展示。
