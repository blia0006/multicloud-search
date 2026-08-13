# 验收清单（逐条对照课题要求）

> 一键跑完全部检查：`python3 tools/verify_all.py`（71 项，退出码 0 即全部通过）
> 最近一次实测：2026-08-12，**71/71 通过**。

---

## A. 目标产出对照

### A1. 产品文档聚合搜索

| 要求 | 实现 | 验证方式 |
| --- | --- | --- |
| 统一搜索框 | 首页「产品文档搜索」页签单一输入框 + 12 个快捷词 | 浏览器打开首页 |
| 覆盖四家文档站 | 176 个产品（腾讯云/阿里云/华为云/火山引擎各 44 个），10 大类；长尾用四家「站内搜索」链接兜底 | `python3 cli.py docs "对象存储"` |
| 结果卡片形式 | 卡片含产品名称、英文名、摘要、**厂商品牌色徽章（来源标识）**、类目标签、同类标签 | 首页搜索任意关键词 |
| 点击跳转原始文档页 | 卡片「官方文档 ↗」直达官方文档；全部为 https 官方域名 | `python3 tools/check_data.py --check-links --vendor tencent`（44/44 返回 200） |

附加能力：厂商缩写检索（`OSS` → 四家同类）、厂商词识别（`华为云 数据库` 自动过滤）、厂商多选、类目过滤、条数控制。

### A2. 产品价格对比查询

| 要求 | 实现 | 验证方式 |
| --- | --- | --- |
| 以 ECS/CVM 为切入点 | 4 厂商 × 5 规格 × 4 地域 = 80 个价格点（20 条机型记录） | 首页「ECS 价格对比」页签 |
| 同一界面呈现四家同类配置 | 一张表同时列出四家，最低价行高亮 + 最大价差结论 | `python3 cli.py price --vcpu 4 --memory 8` |
| 数据来源（抓取或手动维护） | **手动维护快照**，每条带 `source_url` 官方价格页；不做在线爬取的原因与替代路径见 `DATA_SOURCES.md` 第 2 节 | `data/ecs_prices.json` |
| 按 CPU 筛选 | vCPU 下拉（2/4/8） | `--vcpu 8` |
| 按内存筛选 | 内存下拉（4/8/16/32 GB） | `--memory 32` |
| 按地域筛选 | 华北（北京）/华东（上海）/华南（广州·深圳）/中国香港，并给出四家真实 region ID 映射 | `python3 cli.py regions` |

附加能力：规格快捷项、实例系列（1:2 / 1:4）、计费口径切换（包月/按量）、厂商多选、复制 Markdown、导出 CSV、配套资源（云盘/带宽/流量）参考单价。

### A3. MCP / Skills 接口

| 要求 | 实现 | 验证方式 |
| --- | --- | --- |
| 核心能力封装为 MCP 工具 | 5 个工具：`search_cloud_docs`、`compare_ecs_price`、`find_equivalent_products`、`list_cloud_products`、`list_cloud_regions`；stdio + JSON-RPC 2.0 + MCP 2024-11-05 | `python3 tools/mcp_selftest.py` |
| 封装为 Codebuddy Skills | `.codebuddy/skills/multicloud-lookup/SKILL.md`（含触发场景、命令表、3 个示例、输出规范） | 在 Codebuddy 中加载技能并执行示例命令 |
| Agent 可编程调用文档检索 | `search_cloud_docs` / `find_equivalent_products`，返回 Markdown + `structuredContent` 双格式 | `docs/MCP_USAGE.md` 示例 1、3 |
| Agent 可编程调用价格查询 | `compare_ecs_price`，支持地域/vCPU/内存/规格/系列/厂商/计费口径 | `docs/MCP_USAGE.md` 示例 2、4 |
| **同时服务人工查阅与 Agent 自动化调用** | 三条通道共用 `core/engine.py` 与 `data/*.json`：MCP（Agent 自主调用）、Skill（带输出规范）、REST/CLI（无人值守）；含 5 个场景剧本、Agent 系统提示词模板、6 项防幻觉机制 | `docs/AGENT_USAGE.md`、`examples/weekly_price_report.py` |

---

## B. 技术要求对照

| 要求 | 实现 |
| --- | --- |
| 前端：单文件 HTML 或轻量 Web App | 两者都有：`web/index.html`（轻量 Web App，走后端）+ `tools/build_static.py` 产出 `dist/index.html`（**真正单文件，数据内联，103.8 KB，零后端**） |
| 可部署至公网或 woa 内网 | Nginx 反向代理、systemd 常驻、Docker、对象存储静态网站（COS/OSS/OBS）四种方式，见 `DEPLOYMENT.md` 第 3~5 节 |
| 后端（可选）：提供服务及部署说明 | `server/app.py`（零依赖 REST API + 静态服务），部署说明见 `DEPLOYMENT.md`；含健康检查、安全加固、环境变量配置表 |
| 数据更新：说明来源与刷新策略 | `DATA_SOURCES.md`：来源表、四家爬取可行性实测结论、字段规范、价格口径约定、月度/季度/事件驱动三档刷新 SOP、pre-commit 校验 |
| MCP/Skills：接口定义、参数说明、调用示例 | `docs/MCP_USAGE.md`（5 个工具的完整参数表 + 返回结构 + 4 个真实返回示例 + 故障排查）、`mcp/MCP_SERVER_README.md`、`SKILL.md` |

---

## C. 验收标准对照

### C1. 完整部署文档，可被他人独立复现

| 检查点 | 位置 |
| --- | --- |
| 环境依赖 | `DEPLOYMENT.md` §1（OS / Python 3.8+ / **零第三方依赖** / 浏览器 / 网络要求）+ `requirements.txt` |
| 启动命令 | §3.1（`python3 server/app.py`）、§4（静态构建）、§5（Docker） |
| 访问地址 | §3.2 地址表（首页、健康检查、搜索接口、价格接口） |
| 配置项 | §3.3 环境变量表（`MCS_HOST`/`MCS_PORT`/`MCS_DATA_DIR`/`MCS_ALLOW_ORIGIN`） |
| 生产部署 | §3.4 systemd、§3.5 Nginx、§5 Docker（非 root + HEALTHCHECK） |
| MCP/Skill 部署 | §2.1（一键初始化）、§6、§7（MCP 配置模板 `config/mcp.example.json` + 本机配置生成） |
| 冒烟测试清单 | §8（6 条命令 + 6 个浏览器验证点） |
| 故障排查 | §9（7 类常见问题） |
| 升级回滚 | §10（含数据热更新说明） |

```bash
# 复现验证（新环境从零开始）
python3 -V                    # >= 3.8
python3 tools/verify_all.py   # 71 项检查全通过
python3 server/app.py         # 访问 http://127.0.0.1:8787
```

### C2. 产品文档搜索可用，四家至少各覆盖主流 IaaS/PaaS

| 厂商 | 收录数 | 覆盖类目 |
| --- | --- | --- |
| 腾讯云 | 44 | 计算、容器与中间件、存储、网络与CDN、数据库、大数据、AI 与大模型、安全、运维与可观测、音视频 |
| 阿里云 | 44 | 同上 |
| 华为云 | 44 | 同上 |
| 火山引擎 | 44 | 同上 |

- 42 组跨云同类产品映射，**四家覆盖矩阵 100% 完整**（`tools/check_data.py` 输出矩阵与待补全清单）；
- IaaS 关键产品：云服务器、轻量服务器、弹性伸缩、块存储、文件存储、对象存储、VPC、负载均衡、EIP、NAT、专线、CDN、DNS；
- PaaS 关键产品：Kubernetes、镜像仓库、Serverless、MySQL、云原生数据库、Redis、MongoDB、PostgreSQL、DTS、Kafka、RocketMQ、API 网关、微服务、Hadoop、Flink、数仓/数据湖、机器学习平台、大模型、OCR、语音、WAF、DDoS、主机安全、IAM、KMS、监控、日志、APM、点播、直播、RTC。

### C3. ECS 价格对比页面可用，至少覆盖地域、机型、规格配置、刊例价

| 要求维度 | 实现 |
| --- | --- |
| 地域 | 4 个统一地域 + 四家真实 region ID/名称映射（避免"北京 vs 华北2"错配） |
| 机型 | 实例规格名 + 实例族，如 `S5.LARGE8`（标准型 S5）/ `ecs.c7.xlarge`（计算型 c7）/ `c7.xlarge.2`（通用计算增强型 c7）/ `ecs.c3i.xlarge`（计算型 c3i） |
| 规格配置 | 2C4G、4C8G、8C16G、4C16G、8C32G，覆盖 1:2 与 1:4 两种内存比 |
| 刊例价 | 按量单价（元/小时）+ 包月刊例价（元/月），标注计价口径与快照日期，附官方价格页链接 |

### C4. MCP 或 Skills 实现完整，含 README 和 ≥2 个调用示例，在 Codebuddy 中可实际运行

| 检查点 | 状态 |
| --- | --- |
| README | `mcp/MCP_SERVER_README.md`（MCP 模块快速上手）+ `docs/MCP_USAGE.md`（288 行，含接入配置、工具总览、5 个工具参数表、返回结构、Agent 使用规范、故障排查） |
| 调用示例 | MCP **4 个**（均为真实执行输出）+ Skill **3 个** |
| 在 Codebuddy 中可运行 | Skill 已在 Codebuddy 内实际加载执行（11 个场景实测，含边界场景）；MCP 提供配置模板 `config/mcp.example.json` 与一键初始化 `tools/init_project.py` + `tools/mcp_selftest.py` 18 项协议自测 |

---

## D. 实测记录（2026-08-12）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 一键验收 | `python3 tools/verify_all.py` | 71/71 通过 |
| **异地复现（移交模拟）** | 整包复制到另一路径 → `python3 tools/init_project.py` → `python3 tools/verify_all.py` | 初始化正常、MCP 配置自动指向新路径、**71/71 通过** |
| 数据校验 | `python3 tools/check_data.py` | 结构通过，176 产品，覆盖矩阵完整 |
| 腾讯云链接巡检 | `python3 tools/check_data.py --check-links --vendor tencent` | 44/44 返回 200 |
| MCP 自测 | `python3 tools/mcp_selftest.py` | 18/18 通过 |
| Skill 实测 | Codebuddy 内加载并执行 11 个场景 | 全部通过（过程中发现并修复 2 个缺陷） |
| 安全测试 | 目录穿越 6 种绕过方式 | 全部 403 |

### Skill 实测中发现并修复的问题

1. `cli.py equiv "X" --json` 报 `unrecognized arguments`（argparse 顶层参数位置限制，与文档不一致）→ 引入父解析器 + `SUPPRESS`，两种参数顺序均可用。
2. 查询未覆盖配置（如 16C64G）仅返回空表，无提示 → 新增 `no_data_hint` + `available_specs` + 官方价格计算器链接，防止 Agent 编造价格。

---

## E. 已知边界与后续演进

| 项 | 说明 |
| --- | --- |
| 价格为人工快照 | 页面/API/MCP 三处常驻口径与免责声明；月度复核 SOP 见 `DATA_SOURCES.md` §4.1 |
| 阿里云/华为云/火山引擎链接无法自动校验 | 文档站为 SPA（无效路径也返回 200），需人工抽查；每张卡片提供「站内搜索」兜底 |
| 未覆盖 GPU / 大规格机型 | 查询时明确提示「快照未覆盖」并给出官方价格计算器链接，不编造数据 |
| 自动化抓取 | 建议走厂商计费 OpenAPI（密钥仅环境变量注入），路径见 `DATA_SOURCES.md` §2 |
| 无账号体系 | 定位为只读查询服务；内网发布可在 Nginx 层加认证 |
