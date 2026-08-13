# 多云产品信息一站式检索平台

面向解决方案架构师（SA）的 **all-in-one 检索入口**：一个界面同时检索 **腾讯云 / 阿里云 / 华为云 / 火山引擎** 四家的产品文档，
并在同一页面对比四家 ECS/CVM 的刊例价；同时把核心能力封装为 **MCP 工具** 与 **Codebuddy Skill**，供 AI Agent 编程调用。

- 人工场景：浏览器打开即用，搜索 → 卡片 → 一键跳转官方文档；价格对比可复制 Markdown / 导出 CSV。
- Agent 场景：MCP Server（5 个工具）+ Codebuddy Skill（CLI）+ REST API，同一份数据与逻辑，零重复维护。
- 工程约束：**纯 Python 标准库 + 原生前端，零第三方依赖**，Python 3.8+ 即可运行，内网可离线部署。

---

## 1. 快速开始（三种部署形态，任选其一）

> **拿到项目（clone 或解压）后的第一步**（换电脑/换目录后同样适用）：
>
> ```bash
> cd 课题一
> python3 tools/init_project.py     # 环境与数据检查 → 生成本机 MCP 配置 → 构建单文件版 → 打印上手指引
> python3 tools/verify_all.py       # 70 项自检，期望 0 失败
> ```
>
> 全部代码使用相对定位（`__file__`），项目目录可任意移动；唯一需要绝对路径的是 MCP 客户端配置：
> 入库的 `config/mcp.example.json` 只含占位符，真实路径由上面的脚本生成到 `config/mcp.local.json`（已 gitignore）。

### 形态 A：后端服务模式（推荐，含 REST API）

```bash
cd 课题一
python3 server/app.py                # 默认 http://127.0.0.1:8787
# 或指定监听地址与端口
python3 server/app.py --host 0.0.0.0 --port 8080
```

访问 <http://127.0.0.1:8787> 即为完整平台；REST API 见第 4 节。

### 形态 B：单文件 HTML（零后端，可丢到任意静态托管 / woa 内网目录）

```bash
python3 tools/build_static.py         # 产出 dist/index.html（数据已内联）
open dist/index.html                  # macOS；Windows 直接双击
```

### 形态 C：容器部署

```bash
docker build -t multicloud-search .
docker run -d --name mcs -p 8787:8787 multicloud-search
```

> 完整部署文档（环境依赖、systemd、Nginx、对象存储静态托管、内网发布）见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。

### 自检（验收前先跑一遍）

```bash
python3 tools/verify_all.py                      # 一键验收：70 项检查（数据/搜索/价格/API/安全/MCP/Skill/Agent/前端/文档）
python3 tools/check_data.py                      # 数据结构校验 + 四家覆盖矩阵
python3 tools/check_data.py --check-links --vendor tencent   # 文档链接巡检
python3 tools/mcp_selftest.py                    # MCP 协议 + 5 个工具自测（18 项检查）
```

逐条验收标准对照见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。

---

## 2. 目录结构

```
课题一/
├── data/                          # 唯一数据源（人工维护 + 脚本校验）
│   ├── products.json              #   176 个产品索引（四家各 44 个）+ 跨云同类映射表
│   └── ecs_prices.json            #   ECS/CVM 价格快照：4 地域 × 5 规格 × 4 厂商 = 20 条机型记录
├── core/                          # 共享内核（检索算法 + 价格对比），被 API/CLI/MCP 复用
│   ├── __init__.py
│   └── engine.py
├── server/app.py                  # 零依赖 HTTP 服务：REST API + 静态站点
├── web/index.html                 # 前端单页应用（可脱离后端运行）
├── cli.py                         # 命令行工具（供人工与 Codebuddy Skill 调用）
├── mcp/
│   ├── multicloud_mcp_server.py   # MCP Server（stdio / JSON-RPC 2.0，5 个工具）
│   └── MCP_SERVER_README.md       # MCP 模块 README（快速上手，避免与根 README 同名）
├── .codebuddy/skills/multicloud-lookup/SKILL.md   # Codebuddy Skill 定义
├── config/mcp.example.json        # MCP 客户端配置模板（仅占位符；本机配置由 init_project.py 生成到 mcp.local.json）
├── examples/
│   └── weekly_price_report.py     # 自动化调用范例：生成 ECS 价格对比周报（可挂 cron/CI）
├── tools/
│   ├── init_project.py            # 移交后一键初始化（重写 MCP 绝对路径、构建单文件、打印上手指引）
│   ├── verify_all.py              # 一键验收（70 项检查，CI 可用）
│   ├── build_static.py            # 生成单文件 HTML
│   ├── check_data.py              # 数据自检 / 覆盖矩阵 / 链接巡检
│   └── mcp_selftest.py            # MCP 自测
├── docs/
│   ├── DEPLOYMENT.md              # 部署文档（环境依赖、启动命令、访问地址、公网/内网发布）
│   ├── DATA_SOURCES.md            # 数据来源、口径与刷新策略
│   ├── MCP_USAGE.md               # MCP 接口定义、参数说明与调用示例
│   ├── AGENT_USAGE.md             # Agent 自动化调用指南（三条通道、场景剧本、提示词模板）
│   └── ACCEPTANCE.md              # 验收清单（逐条对照课题要求 + 实测记录）
├── requirements.txt               # 空依赖清单（显式声明零第三方依赖）
├── Dockerfile
└── README.md
```

> 构建/运行产物 `dist/`（单文件 HTML）与 `reports/`（链接巡检 CSV）不入库，由脚本按需生成。

---

## 3. 功能说明

### 3.1 产品文档聚合搜索

- 统一搜索框覆盖四家文档站，结果以**卡片**呈现：产品名称、英文名、一句话摘要、**来源厂商标识（品牌色徽章）**、类目、同类标签。
- 点击「官方文档 ↗」直达原始文档页；点击「站内搜索」用当前关键词跳到该厂商文档站搜索页（长尾文档兜底）。
- 检索能力：
  - 中文名（`对象存储`）、英文名（`Object Storage`）、厂商缩写（`COS`/`OSS`/`OBS`/`TOS`）均可命中；
  - **跨云同类映射**：搜 `对象存储` 或 `OSS`，自动带出四家同类产品（42 组同类映射，四家全覆盖）；
  - 厂商词识别：`华为云 数据库` 自动按华为云过滤；
  - 支持按厂商多选、类目过滤、返回条数控制。
- 覆盖范围：计算、容器与中间件、存储、网络与 CDN、数据库、大数据、AI 与大模型、安全、运维可观测、音视频共 **10 大类、176 个主流 IaaS/PaaS 产品**。

### 3.2 ECS/CVM 价格对比

- 同一界面呈现四家同类配置价格：**厂商 / 实例规格 / 实例族 / 配置 / 厂商地域 ID / 按量单价（元/小时）/ 包月刊例价（元/月）/ 较最低价差 / 官方价格页链接**。
- 筛选维度：地域（华北北京、华东上海、华南广州深圳、中国香港）、规格快捷项（2C4G/4C8G/8C16G/4C16G/8C32G）、vCPU、内存、实例系列（1:2 计算型 / 1:4 通用内存型）、厂商、计费口径。
- 自动结论：最低价、最高价、最大价差百分比，最低价行高亮。
- 一键「复制为 Markdown」/「导出 CSV」，直接贴进方案或报价单。
- 附「配套资源参考单价」（SSD 系统盘、固定带宽、按流量），用于整机估算。
- 价格口径与免责声明在页面常驻显示，含快照日期与下次复核日期。

### 3.3 跨云同类对照

输入 `CVM` / `OSS` / `DCS` / `veDB` / `弹性伸缩`，输出四家对位产品表（产品名 + 摘要 + 文档链接），用于迁移映射与方案替换说明。

### 3.4 MCP / Skills（Agent 可编程调用）

课题要求平台"同时服务于人工查阅和 **Agent 自动化调用**两种场景"，为此提供三条通道，共用同一份数据与逻辑：

| 通道 | 入口 | 是否需要 LLM | 适用场景 |
| --- | --- | --- | --- |
| MCP Server | `mcp/multicloud_mcp_server.py` | 是 | AI 客户端里 Agent 自主决定调哪个工具、传什么参数（5 个工具，stdio） |
| Codebuddy Skill | `.codebuddy/skills/multicloud-lookup/SKILL.md` | 是 | 让 Agent 连"输出规范"（免责声明、禁止编造价格与链接）一起遵守 |
| REST API / CLI | `server/app.py`、`cli.py` | 否 | 脚本、定时任务、CI 的无人值守自动化（确定性输出） |

可运行范例：`python3 examples/weekly_price_report.py` 自动产出《四家云 ECS 价格对比周报》（支持 `--api` 走 REST 取数、可挂 crontab/CI）。
场景剧本、Agent 系统提示词模板、防幻觉机制见 [`docs/AGENT_USAGE.md`](docs/AGENT_USAGE.md)；协议级参数与返回结构见 [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md)。

---

## 4. REST API

基址：`http://<host>:<port>`，全部为 `GET`，返回 `application/json; charset=utf-8`。

| 接口 | 参数 | 说明 |
| --- | --- | --- |
| `/api/health` | - | 健康检查 |
| `/api/meta` | - | 厂商、类目、地域、规格、收录统计等元数据 |
| `/api/search` | `q`（必填）、`vendors`、`category`、`limit`(1-200) | 文档聚合搜索 |
| `/api/products` | `vendor`、`category` | 产品清单 |
| `/api/equivalents` | `keyword` | 跨云同类对照 |
| `/api/prices/ecs` | `region`、`vcpu`、`memory`、`spec`、`vendors`、`series`、`charge_type`、`sort` | ECS 价格对比 |
| `/api/regions` | - | 地域及四家地域 ID 映射 |
| `/data/products.json`、`/data/ecs_prices.json` | - | 原始数据（前端加载用，只读白名单） |

示例：

```bash
curl "http://127.0.0.1:8787/api/search?q=对象存储&limit=8"
curl "http://127.0.0.1:8787/api/search?q=Kubernetes&vendors=tencent,aliyun"
curl "http://127.0.0.1:8787/api/prices/ecs?region=cn-beijing&vcpu=4&memory=8"
curl "http://127.0.0.1:8787/api/prices/ecs?spec=8c32g&charge_type=on_demand_hour"
curl "http://127.0.0.1:8787/api/equivalents?keyword=CVM"
```

---

## 5. CLI

```bash
python3 cli.py docs "对象存储"                                  # 文档聚合搜索
python3 cli.py docs "Kubernetes" --vendors tencent,aliyun --limit 8
python3 cli.py price --vcpu 4 --memory 8 --region cn-beijing     # 价格对比
python3 cli.py price --spec 8c32g --charge-type on_demand_hour
python3 cli.py equiv CVM                                        # 同类对照
python3 cli.py products --vendor huawei --category database
python3 cli.py regions
# 任意命令加 --json 得到结构化输出
```

---

## 6. 数据来源与刷新

- **产品索引**：以四家官网文档站的产品文档入口为准，人工整理维护（结构化字段 + 同类映射），链接均为 `https` 官方域名。
- **价格数据**：人工维护的刊例价快照（`snapshot_date` + `next_review`），每条记录带官方价格页 `source_url`。
- **刷新策略**：产品索引季度巡检 + 事件驱动补录；价格月度复核；每次变更必须跑 `tools/check_data.py` 通过后提交。
- 详细说明（为何不做在线爬取、爬取风险与替代方案、刷新 SOP、字段规范）见 [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)。

> ⚠️ 价格为快照数据，仅用于量级对比与方案初估；对客报价必须回到各厂商官网价格页/价格计算器核对。

---

## 7. 安全设计

- 后端不代理任何用户提供的 URL，无 SSRF 面；链接巡检脚本对四家官方域名做白名单校验。
- 静态文件服务经 `realpath` 校验 + 后缀白名单，防目录穿越；数据文件仅开放两个固定只读文件。
- 默认仅监听 `127.0.0.1`；跨域默认关闭，需要时用 `MCS_ALLOW_ORIGIN` 指定确切来源（不支持 `*`）。
- 前端所有数据渲染做 HTML 转义，外链强制 `https://` 白名单校验并带 `rel="noopener noreferrer"`。
- 无密钥、无用户数据、无数据库，只读数据集；查询参数长度受限。

---

## 8. 移交与打包

### 8.1 通过 GitHub 移交（推荐）

上传：

```bash
cd 课题一
git init
git add -A                      # .gitignore 已排除 dist/、reports/、__pycache__、config/mcp.local.json
git commit -m "feat: 多云产品信息一站式检索平台"
git branch -M main
git remote add origin git@github.com:<你的账号>/<仓库名>.git
git push -u origin main
```

导师侧（三条命令即可运行）：

```bash
git clone git@github.com:<你的账号>/<仓库名>.git && cd <仓库名>
python3 tools/init_project.py     # 生成本机 MCP 配置 + 构建 dist/index.html
python3 tools/verify_all.py       # 70 项自检，期望 0 失败
```

上传前确认（已在本项目中处理好）：

| 检查点 | 状态 |
| --- | --- |
| 不含任何密钥/令牌 | 全项目零密钥（无需 API Key，纯本地数据） |
| 不泄露本机绝对路径 | `config/mcp.example.json` 仅占位符；真实路径在 gitignore 的 `mcp.local.json` |
| 隐藏目录 `.codebuddy/` 会入库 | 未被 gitignore，`git add -A` 会包含（Skill 定义在其中） |
| 跨平台换行符 | `.gitattributes` 统一 `eol=lf`，Windows clone 不会出现 CRLF 噪音 |
| 可再生产物不入库 | `dist/`、`reports/` 已忽略，由 `init_project.py` 重新生成 |
| 刚 clone 未初始化也能通过自检 | 已实测：未生成 `mcp.local.json` 时 `verify_all.py` 仍 70/70 通过 |

### 8.2 通过压缩包移交

```bash
cd .. && tar --exclude="__pycache__" --exclude=".DS_Store" --exclude="dist" --exclude="reports" \
        --exclude="config/mcp.local.json" -czf 多云检索平台.tar.gz 课题一
# 或 zip：zip -r 多云检索平台.zip 课题一 -x "*__pycache__*" "*.DS_Store" "课题一/dist/*" "课题一/reports/*"
```

> 用 zip/tar 打包整个目录会包含隐藏目录 `.codebuddy/`；但用 `cp *` 复制会漏掉它，Skill 就没了。

### 8.3 接收方拿到后的五种用法

| 使用方式 | 操作 |
| --- | --- |
| 人工查阅（零后端） | 双击 `dist/index.html` |
| 人工查阅（完整功能） | `python3 server/app.py` → <http://127.0.0.1:8787> |
| Agent（MCP） | 把 `config/mcp.local.json` 的 `mcpServers` 粘到 MCP 客户端配置 |
| Agent（Skill） | 用 Codebuddy 打开本项目目录，技能自动识别 |
| 脚本/定时任务 | `python3 cli.py …`、`python3 examples/weekly_price_report.py` |

环境要求：**Python 3.8+，无需联网、无需 `pip install`**。
Windows 用户把命令里的 `python3` 换成 `python`（代码未使用任何 POSIX 专有特性）。

---

## 9. 验收标准对照

| 验收项 | 交付物 | 位置 |
| --- | --- | --- |
| 完整部署文档，可独立复现 | 环境依赖、启动命令、访问地址、三种部署形态、Nginx/systemd/Docker、冒烟清单、故障排查、升级回滚 | [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |
| 文档搜索可用，四家各覆盖主流 IaaS/PaaS | 176 个产品（四家各 44 个）、10 大类、42 组同类映射四家全覆盖；`tools/check_data.py` 输出覆盖矩阵 | `data/products.json`、`web/index.html` |
| ECS 价格对比页可用，覆盖地域/机型/规格/刊例价 | 4 地域 × 5 规格 × 4 厂商，含实例族、厂商地域 ID、按量与包月刊例价、价差结论 | `data/ecs_prices.json`、价格对比 Tab |
| MCP/Skills 完整，含 README 与 ≥2 个调用示例，Codebuddy 中可运行 | MCP 5 工具 + 完整 Schema + 4 个调用示例；Skill 含 3 个示例；`tools/mcp_selftest.py` 18 项检查全通过 | [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md)、`.codebuddy/skills/multicloud-lookup/SKILL.md` |

**一键验证全部验收项**：`python3 tools/verify_all.py` → 70 项检查，最近实测 **70/70 通过**。
逐条对照说明（含目标产出、技术要求、验收标准、实测记录、已知边界）见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。
