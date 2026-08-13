# 多云产品信息一站式检索平台

做客户方案时，经常要在腾讯云、阿里云、华为云、火山引擎四家之间来回查文档、比价格，
标签页开一堆还容易记混。这个项目把这件事收到一个入口里：

- 一个搜索框同时搜四家的产品文档，点一下跳官方原文；
- 一张表并排看四家同配置云服务器的刊例价；
- 同一份数据和逻辑也封装成 MCP 工具与 Codebuddy Skill，让 AI Agent 直接调用。

技术上刻意做得很轻：只用 Python 标准库和原生前端，没有任何第三方依赖，Python 3.8 以上就能跑，
不联网也能用，方便丢到内网。

---

## 1. 快速开始

### 第一步：初始化

拿到项目后（clone 或解压都一样）先跑一次，换电脑、换目录后也要重跑：

```bash
cd 课题一
python3 tools/init_project.py
```

它会检查环境和数据、生成本机的 MCP 配置、构建出免后端的单文件版本，最后打印一份上手指引。

想确认一切正常，接着跑自检，预期 71 项全部通过：

```bash
python3 tools/verify_all.py
```

> macOS 的 zsh 默认不认行尾 `#` 注释，从文档里连注释一起复制会报 `unrecognized arguments`。
> 项目里的脚本已能自动忽略这种误传，但复制时只复制命令本身更稳妥。

### 第二步：选一种方式运行

**方式 A：启动后端服务**（推荐，功能最全，带 REST API）

```bash
python3 server/app.py
```

默认监听 <http://127.0.0.1:8787>，浏览器打开就是完整平台。要对外提供访问：

```bash
python3 server/app.py --host 0.0.0.0 --port 8080
```

**方式 B：单文件 HTML**（不需要后端）

```bash
python3 tools/build_static.py
open dist/index.html
```

生成的 `dist/index.html` 已把数据内联进去，双击就能用，也可以丢到对象存储静态网站或 woa 内网目录
（Windows 下直接双击）。

**方式 C：Docker**

```bash
docker build -t multicloud-search .
docker run -d --name mcs -p 8787:8787 multicloud-search
```

环境依赖、systemd 常驻、Nginx 反代、静态托管、故障排查这些细节都在
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。

### 其他自检命令

```bash
python3 tools/check_data.py
python3 tools/check_data.py --check-links --vendor tencent
python3 tools/mcp_selftest.py
```

依次是：校验数据结构并打印四家覆盖矩阵；巡检腾讯云文档链接可达性；测试 MCP 协议与 5 个工具（18 项）。
逐条对照课题验收标准见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。

---

## 2. 功能说明

### 2.1 产品文档聚合搜索

一个搜索框覆盖四家文档站，结果以卡片展示，每张卡片有产品名称、英文名、一句话摘要、
厂商标识（各家品牌色徽章）、类目和同类产品标签。点「官方文档」跳原始文档页；
点「站内搜索」带着当前关键词跳该厂商文档站的搜索页，用来兜住 API 细节、错误码这类长尾内容。

支持的输入方式：中文名（`对象存储`）、英文名（`Object Storage`）、厂商缩写（`COS`/`OSS`/`OBS`/`TOS`）、
能力关键词（`Kubernetes`、`大模型`）。

比较实用的是跨云同类召回：搜 `对象存储` 或任意一家的缩写，四家的对应产品会一起出来，不用挨个搜。
背后是 42 组人工校对的同类映射，四家均已覆盖。查询里带厂商名会自动过滤，
比如 `华为云 数据库` 只出华为云结果。界面上还能多选厂商、按类目筛选、调整返回条数。

收录 176 个主流 IaaS/PaaS 产品，四家各 44 个，分成计算、容器与中间件、存储、网络与 CDN、
数据库、大数据、AI 与大模型、安全、运维可观测、音视频共 10 个类目。

### 2.2 ECS/CVM 价格对比

同一张表并排列出四家同配置云服务器价格，每行包含厂商、实例规格、实例族、配置、
厂商自己的地域 ID、按量单价（元/小时）、包月刊例价（元/月）、与最低价的差距百分比、官方价格页链接。

可筛选的维度：

| 维度 | 可选值 |
| --- | --- |
| 地域 | 华北（北京）、华东（上海）、华南（广州/深圳）、中国香港 |
| 规格 | 2C4G、4C8G、8C16G、4C16G、8C32G |
| vCPU / 内存 | 2/4/8 核，4/8/16/32 GB |
| 实例系列 | 1:2 计算型、1:4 通用内存型 |
| 厂商 | 四家任意组合 |
| 计费口径 | 包月刊例价、按量单价 |

表格会自动算出最低价、最高价和最大价差，并高亮最低价那一行。结果可一键「复制为 Markdown」
或「导出 CSV」，直接贴进方案或报价单。下方还有一张配套资源单价表（SSD 系统盘、固定带宽、按流量），
用于估算整机成本。价格口径与免责声明在页面常驻显示，包含数据快照日期和下次复核日期。

### 2.3 跨云同类对照

输入 `CVM`、`OSS`、`DCS`、`veDB`、`弹性伸缩` 这类产品名或缩写，输出四家对位产品的表格
（产品名、摘要、文档链接），写迁移映射表或方案替换说明时直接用。

### 2.4 给 Agent 用的三条通道

课题要求同时服务人工查阅和 Agent 自动化调用。三条通道共用 `core/engine.py` 与 `data/` 下的同一份数据，
所以人在页面看到的和 Agent 拿到的不会不一致。

| 通道 | 入口 | 需要 LLM | 什么时候用 |
| --- | --- | --- | --- |
| MCP Server | `mcp/multicloud_mcp_server.py` | 需要 | Agent 自己决定调哪个工具、传什么参数（5 个工具，stdio） |
| Codebuddy Skill | `.codebuddy/skills/multicloud-lookup/SKILL.md` | 需要 | 除了查数据，还要让 Agent 遵守输出规范（带免责声明、不许编造价格和链接） |
| REST API / CLI | `server/app.py`、`cli.py` | 不需要 | 脚本、定时任务、CI 这类固定流程，要的是确定性输出 |

第三条通道有个能直接跑的例子，遍历所有规格生成一份《四家云 ECS 价格对比周报》，
加 `--api` 可改成走 REST 取数，挂到 crontab 或 CI 上就是无人值守的定期产出：

```bash
python3 examples/weekly_price_report.py
```

场景剧本、可直接粘贴的 Agent 系统提示词、防幻觉设计见 [`docs/AGENT_USAGE.md`](docs/AGENT_USAGE.md)；
每个工具的参数表和返回结构见 [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md)。

---

## 3. REST API

基址 `http://<host>:<port>`，全部是 GET，返回 `application/json; charset=utf-8`。

| 接口 | 参数 | 说明 |
| --- | --- | --- |
| `/api/health` | 无 | 健康检查 |
| `/api/meta` | 无 | 厂商、类目、地域、规格、收录统计等元数据 |
| `/api/search` | `q`（必填）、`vendors`、`category`、`limit`（1-200） | 文档聚合搜索 |
| `/api/products` | `vendor`、`category` | 产品清单 |
| `/api/equivalents` | `keyword` | 跨云同类对照 |
| `/api/prices/ecs` | `region`、`vcpu`、`memory`、`spec`、`vendors`、`series`、`charge_type`、`sort` | ECS 价格对比 |
| `/api/regions` | 无 | 地域及四家地域 ID 映射 |
| `/data/products.json`、`/data/ecs_prices.json` | 无 | 原始数据，供前端加载（只读白名单） |

几个例子：

```bash
curl "http://127.0.0.1:8787/api/search?q=对象存储&limit=8"
curl "http://127.0.0.1:8787/api/search?q=Kubernetes&vendors=tencent,aliyun"
curl "http://127.0.0.1:8787/api/prices/ecs?region=cn-beijing&vcpu=4&memory=8"
curl "http://127.0.0.1:8787/api/prices/ecs?spec=8c32g&charge_type=on_demand_hour"
curl "http://127.0.0.1:8787/api/equivalents?keyword=CVM"
```

---

## 4. CLI

命令行版本，人工用和 Codebuddy Skill 调用都是它。任意命令加 `--json` 得到结构化输出。

```bash
python3 cli.py docs "对象存储"
python3 cli.py docs "Kubernetes" --vendors tencent,aliyun --limit 8
python3 cli.py price --vcpu 4 --memory 8 --region cn-beijing
python3 cli.py price --spec 8c32g --charge-type on_demand_hour
python3 cli.py equiv CVM
python3 cli.py products --vendor huawei --category database
python3 cli.py regions
```

依次是：文档聚合搜索、限定厂商搜索、按配置查价、按规格查按量单价、同类对照、列产品、看地域映射。

---

## 5. 目录结构

```
课题一/
├── data/                          唯一数据源，人工维护 + 脚本校验
│   ├── products.json              176 个产品索引 + 42 组跨云同类映射
│   └── ecs_prices.json            价格快照：4 地域 × 5 规格 × 4 厂商
├── core/
│   ├── engine.py                  检索算法与价格对比，API/CLI/MCP 都用它
│   ├── cliutil.py                 命令行参数容错（忽略 zsh 误传的注释）
│   └── __init__.py
├── server/app.py                  零依赖 HTTP 服务：REST API + 静态站点
├── web/index.html                 前端单页，需后端托管
├── cli.py                         命令行工具
├── mcp/
│   ├── multicloud_mcp_server.py   MCP Server，stdio + JSON-RPC 2.0，5 个工具
│   └── MCP_SERVER_README.md       MCP 模块说明（故意不叫 README.md，避免同名混淆）
├── .codebuddy/skills/multicloud-lookup/SKILL.md    Codebuddy Skill 定义
├── config/mcp.example.json        MCP 配置模板，只有占位符
├── examples/weekly_price_report.py 自动化调用范例，生成价格周报
├── tools/
│   ├── init_project.py            拿到项目后的一键初始化
│   ├── verify_all.py              一键验收，71 项检查，可进 CI
│   ├── build_static.py            生成单文件 HTML
│   ├── check_data.py              数据自检、覆盖矩阵、链接巡检
│   └── mcp_selftest.py            MCP 自测
├── docs/
│   ├── DEPLOYMENT.md              部署文档
│   ├── DATA_SOURCES.md            数据来源与刷新策略
│   ├── MCP_USAGE.md               MCP 接口定义与调用示例
│   ├── AGENT_USAGE.md             Agent 自动化调用指南
│   └── ACCEPTANCE.md              验收清单，逐条对照课题要求
├── requirements.txt               空依赖清单，用来明确"零第三方依赖"
├── Dockerfile
└── README.md
```

`dist/`（单文件 HTML）和 `reports/`（巡检 CSV、价格周报）是运行时生成的产物，不入库，
`init_project.py` 会重新生成。

---

## 6. 数据从哪来，怎么更新

两个数据文件都是人工维护的：

- **产品索引**：按四家官网文档站的产品入口整理，字段结构化，链接全部是 https 官方域名。
- **价格快照**：照官网价格页/价格计算器的刊例价录入，带 `snapshot_date` 和 `next_review`，
  每条记录都有官方价格页 `source_url` 可回溯。

更新节奏是：价格每月复核一次，产品索引每季度巡检一次，中间遇到新产品或链接失效就随时补录。
每次改完数据必须先跑 `python3 tools/check_data.py` 通过再提交。

为什么不做在线爬取？实测过四家：阿里云搜索接口会触发风控拦截，华为云和火山引擎文档站是 SPA
（无效路径也返回 200），只有腾讯云能精确判断 404。所以选了「静态维护 + 官方链接直达 + 站内搜索兜底」
这条更稳的路。详细结论、字段规范、刷新 SOP 都在 [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)。

需要强调的是：**价格是快照数据，只适合做量级对比和方案初估，对客报价必须回官网核对。**
这句话在页面、API 响应和 MCP 返回里都会带上。

---

## 7. 安全设计

只读查询服务，没有账号体系，也不需要任何密钥，所以攻击面本身很小。具体做了这些事：

- 后端不代理任何用户提供的 URL，没有 SSRF 面；链接巡检脚本只允许请求四家官方域名。
- 静态文件服务经过 `realpath` 校验加后缀白名单，防目录穿越；数据文件只开放两个固定的只读文件。
- 默认只监听 `127.0.0.1`；跨域默认关闭，需要时用 `MCS_ALLOW_ORIGIN` 指定确切来源，不支持 `*`。
- 前端所有数据渲染都做 HTML 转义，外链强制校验 `https://` 并带 `rel="noopener noreferrer"`。
- 无密钥、无用户数据、无数据库，查询参数长度也做了限制。

---

## 8. 移交与打包

### 通过 GitHub 移交

上传：

```bash
cd 课题一
git init
git add -A
git commit -m "feat: 多云产品信息一站式检索平台"
git branch -M main
git remote add origin git@github.com:<你的账号>/<仓库名>.git
git push -u origin main
```

`.gitignore` 已经排除了 `dist/`、`reports/`、`__pycache__` 和 `config/mcp.local.json`。

对方 clone 后三条命令就能跑起来：

```bash
git clone git@github.com:<你的账号>/<仓库名>.git && cd <仓库名>
python3 tools/init_project.py
python3 tools/verify_all.py
```

上传前的几个点已经处理好了：

| 检查点 | 情况 |
| --- | --- |
| 密钥泄露 | 全项目零密钥，不需要任何 API Key |
| 本机路径泄露 | 入库的 `config/mcp.example.json` 只有占位符，真实路径在被忽略的 `mcp.local.json` 里 |
| 隐藏目录会不会漏 | `.codebuddy/` 未被忽略，`git add -A` 会包含（Skill 定义在里面，这是最容易漏的） |
| 跨平台换行符 | `.gitattributes` 统一 `eol=lf`，Windows clone 不会出现 CRLF 噪音 |
| 刚 clone 没初始化能否自检 | 可以，已实测未生成 `mcp.local.json` 时仍然 71/71 通过 |

### 通过压缩包移交

```bash
cd .. && tar --exclude="__pycache__" --exclude=".DS_Store" --exclude="dist" --exclude="reports" \
        --exclude="config/mcp.local.json" -czf 多云检索平台.tar.gz 课题一
```

用 zip 或 tar 打包整个目录会带上隐藏目录 `.codebuddy/`；但如果用 `cp *` 复制就会漏掉它，Skill 就没了。

### 接收方能怎么用

| 用法 | 操作 |
| --- | --- |
| 人工查阅，不想启服务 | 双击 `dist/index.html` |
| 人工查阅，要完整功能 | `python3 server/app.py`，访问 <http://127.0.0.1:8787> |
| Agent 走 MCP | 把 `config/mcp.local.json` 里的 `mcpServers` 粘到 MCP 客户端配置 |
| Agent 走 Skill | 用 Codebuddy 打开项目目录，技能会自动识别 |
| 脚本或定时任务 | `python3 cli.py ...`、`python3 examples/weekly_price_report.py` |

只要有 Python 3.8+，不用联网也不用 `pip install`。
Windows 用户把命令里的 `python3` 换成 `python` 即可，代码没有用任何 POSIX 专有特性。

---

## 9. 验收标准对照

| 验收要求 | 怎么满足的 | 在哪看 |
| --- | --- | --- |
| 完整部署文档，可被他人独立复现 | 环境依赖、启动命令、访问地址、三种部署方式、systemd/Nginx/Docker、冒烟清单、故障排查、升级回滚 | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |
| 文档搜索可用，四家各覆盖主流 IaaS/PaaS | 176 个产品（四家各 44 个）、10 大类、42 组同类映射四家全覆盖，`tools/check_data.py` 会打印覆盖矩阵 | `data/products.json`、`web/index.html` |
| ECS 价格对比页可用，覆盖地域/机型/规格/刊例价 | 4 地域 × 5 规格 × 4 厂商，含实例族、厂商地域 ID、按量与包月刊例价、价差结论 | `data/ecs_prices.json`、价格对比页签 |
| MCP 或 Skills 实现完整，含 README 和至少 2 个调用示例 | MCP 5 个工具带完整 Schema 和 4 个真实调用示例；Skill 含 3 个示例；MCP 自测 18 项全通过 | [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md)、`.codebuddy/skills/multicloud-lookup/SKILL.md` |

想一次性验证全部验收项，跑 `python3 tools/verify_all.py`，共 71 项检查，最近一次实测 71/71 通过。
按课题原文逐条对照（含目标产出、技术要求、验收标准、实测记录、已知边界），见
[`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。
