# 学术论文检索（Academic Search Engine）

数据结构课程设计项目：**本地化论文库 + 倒排索引检索 + AI 元数据拆解**，一套代码交付三种形态——
**Android App（WebView + 内嵌 Python）**、**Web（浏览器）**、**桌面独立窗口软件**。

核心算法（倒排索引 / Trie / 布尔解析 / TF-IDF / Porter 词干 / 关键词提取）全部手写；
数据源 arXiv / OpenAlex（含中文文献），离线词典做中英互译检索；
可上传 PDF / TXT / ZIP 增量入库并即时可检索；
配置任意 OpenAI 兼容大模型（应用内填写，无需改代码）即可对入库论文做 AI 元数据精修。

## 功能总览

| 类别 | 说明 |
| --- | --- |
| 检索 | 多词 AND / 布尔(AND OR NOT 括号 引号短语) / 中文检索；词频 TF 与 TF-IDF 一键切换；每次检索附「剖析」（倒排表长度、归并顺序、布尔语法树） |
| 索引 | 倒排索引 term→Posting(论文ID,词频,位置)；Trie 前缀补全 Top10（未命中自动子串兜底） |
| 中英互译检索 | 离线双语词典：中文查询自动扩展英文同义词，英文查询开「中英互译」命中中文文献 |
| 文库 | 分页/搜索/详情/删除；统计条「唯一关键词」「索引总项数」可点击展开全部词条列表（可筛选、分页、点词即搜） |
| 入库 | 上传 PDF/TXT/MD、ZIP 批量、arXiv 链接抓取、手动填写；**点击或拖拽文件到虚线框即可**（桌面窗口自动使用系统原生文件对话框直传）；原文归档于 data/papers_files，可「阅读原文」；严格内容去重 |
| AI 精修 | 「AI 设置」页填写 API 地址/Key/模型（可测试连接、保存即生效、仅存本机）；精修标题/摘要/作者/年份/关键词；失败自动回退规则拆解 |
| 多源采集 | arXiv / OpenAlex 单源或全量抓取（页面「开始采集」），跨源按内容去重 |
| 三端 | 同一套响应式 UI：手机竖屏底部导航、横屏顶部导航、宽屏/桌面左侧导航；桌面为独立窗口软件 |

## 仓库结构

```
├── README.md                       # 本文件
├── docs/android-apk.md             # APK 安装 / 构建 / 无线调试排障指南
├── academic_search_engine/         # 主项目（后端 + Web 前端，手机/桌面共用）
│   ├── paths.py                    # 数据根/资源根统一（支撑打包运行）
│   ├── run.py                      # Web 启动入口
│   ├── core/ ingest/ crawler/ agent/ service/ web/   # 分层后端
│   ├── templates/ static/          # 前端（三端同一份）
│   ├── data/                       # 论文元数据/停用词/互译词典（papers_files 为运行归档）
│   ├── smoke_test.py               # 76 项离线冒烟测试
│   ├── android/                    # Android 工程（Chaquopy 内嵌 Python + 一键构建脚本）
│   ├── desktop/                    # 桌面版：desktop_app.py + PyInstaller spec + build_exe.ps1
│   └── scripts/gen_icons.py        # 品牌图标生成（Pillow）
```

模块依赖单向：`web → service → core | ingest | crawler | agent`；
索引与检索算法无第三方依赖；PDF 解析 pypdf/PyPDF2、HTTP requests、大模型调用为外部库。

## 三种运行形态

### 1) Web（源码运行）

```bash
cd academic_search_engine
pip install -r requirements.txt          # Python 3.9+
python run.py --no-crawl                 # 浏览器访问 http://127.0.0.1:5000
# 数据不足 150 篇时会自动采集 arXiv（不加 --no-crawl）；Windows 也可双击 start.bat
```

### 2) Android APK（手机）

- 直接安装：`academic_search_engine/android/AcademicSearchEngine-debug.apk`（约 85MB，内置 Python 运行时与 1126 篇数据，离线可用）；
- 重新构建与真机排障：见 [docs/android-apk.md](docs/android-apk.md)（`android\build_apk.bat` 一键出包，支持 USB / 无线调试）。

### 3) 桌面独立软件（Windows）

```bat
cd academic_search_engine/desktop
build_exe.ps1        :: 产物 dist\学术论文检索.exe（双击运行，内置独立窗口）
```

- 双击 exe → 弹出独立窗口（WebView2 内核，标题/图标/可缩放）；系统缺少 WebView2 时自动用默认浏览器打开；
- `学术论文检索.exe --browser` 强制使用系统浏览器；窗口关闭或 Ctrl+C 即退出，无残留进程；
- 首次运行自动在 exe 同级目录生成 `data/`（种子 1126 篇），论文库/上传/AI 配置/日志都持久化于此，**请勿放入 Program Files 等只读目录**。

## 配置 AI（三种形态通用）

1. 打开任一端的「AI 设置」视图；
2. 填写 API 地址（如 `https://api.deepseek.com/v1`）、API Key、模型名（如 `deepseek-chat`）；点「测试连接」验证；
3. 保存即生效并持久化（Android=应用私有目录，桌面/Web=数据目录 `data/app_settings.json`，均已 gitignore）；
4. 上传论文时勾选「AI 精修元数据」即可由模型补全标题/摘要/作者/年份/关键词；失败自动回退规则拆解。

> 兼容老用法：也可复制 `academic_search_engine/.env.example` 为 `.env` 填写（`LLM_API_BASE/KEY/MODEL`）。
> Key 只保存在本机，接口与日志不回显明文。

## 测试

```bash
cd academic_search_engine
python smoke_test.py      # 76 项离线断言：算法/入库/API/去重/互译/设置/词条列表，全部隔离临时数据
```

## 维护与二次开发

- **改前端/后端后**：Web 与桌面直接生效；Android 需执行 `sync_android.ps1`（把 python 包、templates/static、数据种子同步进 android 工程）再构建 APK。同步产物在 `android/app/src/main/python|assets` 下，**不要手改**（会被覆盖），仓库中已 gitignore。
- **新增数据源**：在 `crawler/registry.py` 注册一个「抓取函数 → 论文字典列表」，即出现在采集下拉框。
- **更换 AI 服务商**：任意 OpenAI 兼容 Chat Completions 服务即可（在应用内配置）。
- **补充互译词典**：编辑 `data/bilingual.json`（`{"pairs":[["英文","中文"],…]}`）。
- **关键词自动提取**：入库时按“标题 TF×2 + 摘要 TF”×IDF 取 Top8，规则见 `core/keyword_extractor.py`。
- **图标**：改 `scripts/gen_icons.py` 配色后执行（Pillow 依赖仅开发机需要），可重新生成 Android/网页/桌面全套图标。
- **代码规范**：后端薄路由，业务全在 `service/search_service.py`（RLock 并发安全）；路径统一从 `paths.py` 取（`DATA_ROOT` 可写数据 / `RESOURCE_ROOT` 只读资源，支撑手机与桌面打包后的读写分离）。

## 常见问题

- 首次启动慢？数据就绪(<150 篇才采集)后约 1~2 秒建索引；手机首次解压数据约 10~60 秒。
- 手机上 AI 显示「未配置」？到「AI 设置」填写即可；APK 内不内置任何密钥。
- 爬取后总数不增？同源同批论文按内容去重会提示“重复跳过”，属正常；换 OpenAlex/全部源或提高翻页可拿到新文献。
- 扫描版 PDF（无文本层）不再导入失败：系统会按文件名自动建立「待完善」占位条目并归档原文件，提示里给出删除重传 / AI 精修 / 手动完善三种出路。
- 字体：内置思源宋体（OFL）随包分发，保证各端离线时中文宋体、西文衬线观感一致。
- 详细排障（adb/logcat、桌面 exe 说明）见 `docs/android-apk.md` 与各模块 docstring。