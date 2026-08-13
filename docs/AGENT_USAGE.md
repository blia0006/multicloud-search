# Agent 自动化调用指南

课题要求平台"**同时服务于人工查阅和 Agent 自动化调用两种场景**"。本文档专讲第二种场景：
不需要人打开网页，由 **AI Agent** 或 **脚本/定时任务/CI** 直接调用平台能力并产出结果。

---

## 1. 两种场景的区别

| 维度 | 人工查阅 | Agent 自动化调用 |
| --- | --- | --- |
| 入口 | 浏览器打开页面 | MCP 工具 / Skill 命令 / REST API |
| 交互 | 人输入关键词、看卡片、点链接 | 程序传参数、拿结构化数据、自动加工 |
| 输出 | 可视化卡片与表格 | JSON（`structuredContent`）或 Markdown 片段 |
| 典型用途 | 临时查一个产品、当场比个价 | 自动写方案章节、批量迁移映射表、定期价格监控 |
| 对应交付物 | `web/index.html`、`dist/index.html` | `mcp/multicloud_mcp_server.py`、`SKILL.md`、`server/app.py`、`cli.py` |

关键点：**两种场景共用同一份数据（`data/*.json`）与同一套逻辑（`core/engine.py`）**，
所以人在页面上看到的价格，和 Agent 拿到的价格必然一致，不会出现"两套口径"。

```
                         ┌───────────────────────┐
   人工 ── 浏览器 ───────►│  web / dist index.html │
                         └───────────┬───────────┘
                                     │
   Agent ── MCP stdio ───►┌──────────▼───────────┐    ┌──────────────────┐
   Agent ── Skill(CLI) ──►│   core/engine.py     │───►│  data/*.json     │
   系统 ── REST API ─────►└──────────────────────┘    └──────────────────┘
```

---

## 2. 三条通道怎么选

| 通道 | 适用对象 | 是否需要 LLM | 启动方式 | 何时选它 |
| --- | --- | --- | --- | --- |
| **MCP Server** | 支持 MCP 的 AI 客户端（Codebuddy、Claude Desktop 等） | 是 | 客户端按需拉起（stdio） | Agent 需要**自主决定**调哪个工具、传什么参数 |
| **Codebuddy Skill** | Codebuddy 内的 Agent | 是 | 打开项目自动识别 | 想让 Agent 连"输出规范"（免责声明、禁止编造）一起遵守 |
| **REST API / CLI** | 脚本、定时任务、CI、其他后端系统 | 否 | `python3 server/app.py` 或直接 `cli.py` | 固定流程的无人值守自动化，不需要模型推理 |

三者可以并存：Agent 用 MCP 做探索式查询，流水线用 REST 做定期产出。

---

## 3. 通道一：MCP（Agent 自主调用）

### 3.1 配置

先执行 `python3 tools/init_project.py` 生成本机配置 `config/mcp.local.json`（入库的 `config/mcp.example.json` 只含占位符），
再把其中的 `mcpServers` 粘到客户端 MCP 配置中：

```json
{
  "mcpServers": {
    "multicloud-search": {
      "command": "python3",
      "args": ["/绝对路径/课题一/mcp/multicloud_mcp_server.py"],
      "env": { "MCS_DATA_DIR": "/绝对路径/课题一/data" }
    }
  }
}
```

### 3.2 一次完整调用链（实测输出）

Agent 侧真实发生的四步（`tools/mcp_selftest.py` 与下述命令均可复现）：

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sa-agent","version":"1.0"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"compare_ecs_price","arguments":{"region":"cn-shanghai","spec_id":"4c8g"}}}' \
 | python3 mcp/multicloud_mcp_server.py
```

| 步骤 | 方法 | Agent 得到什么 |
| --- | --- | --- |
| ① 握手 | `initialize` | 协议版本、`serverInfo`、`instructions`（告诉模型这个服务是干什么的） |
| ② 就绪通知 | `notifications/initialized` | 无返回（通知类消息） |
| ③ 发现能力 | `tools/list` | 5 个工具的名称、描述、**JSON Schema 参数定义**——模型据此自己决定怎么传参 |
| ④ 执行 | `tools/call` | `content[0].text`（Markdown，可直接展示）+ `structuredContent`（JSON，可二次加工） |

实测结果（2026-08-12）：

```
[id=1] 握手成功：{'name': 'multicloud-search', 'version': '1.0.0'}，可用能力=['tools']
[id=2] 同类对照 → tencent:对象存储 COS / aliyun:对象存储 OSS / huawei:对象存储服务 OBS / volcengine:对象存储 TOS
[id=3] 协议错误 → Method not found: compare_ecs_price（Agent 会据此换用 tools/call 重试）
[id=4] 价格对比 → 最低 火山引擎 ecs.c3i.xlarge = 464 元/月，最大价差 15.5%
```

> 第 3 行是刻意发错方法名的负例：服务返回标准 JSON-RPC `-32601` 错误而不是崩溃，Agent 可以自行纠正重试。

### 3.3 为什么返回两种格式

```jsonc
{
  "content": [{ "type": "text", "text": "### ECS/CVM 价格对比 …Markdown 表格…" }],
  "structuredContent": { "rows": [ … ], "summary": { "cheapest": … } }
}
```

- `content.text`：Agent 可以**原样贴给用户**，省掉一次模型重排（少一次幻觉机会）；
- `structuredContent`：Agent 需要计算（比如"三年 TCO"、"筛出比腾讯云贵的"）时用它，避免解析表格文本。

工具还支持 `format: "json"` 参数，让 `content.text` 直接变成 JSON 字符串，适配只读取 text 的客户端。

---

## 4. 通道二：Codebuddy Skill（Agent 按规范调用）

Skill 定义在 `.codebuddy/skills/multicloud-lookup/SKILL.md`，它比 MCP 多做了一件事：**约束 Agent 的输出行为**。

工作方式：

1. 用户说"帮我对比下四家 4C8G 云服务器价格"；
2. Codebuddy 根据 SKILL.md 的 `description` 判断该加载本技能；
3. Agent 读到技能里的命令表，执行 `python3 cli.py price --vcpu 4 --memory 8`；
4. Agent 按技能里的「输出使用规范」组织回答——**必须带口径与免责声明、链接原样引用、不许编造价格**。

技能内置的四条护栏（对应 SKILL.md「输出使用规范」）：

| 护栏 | 防止的问题 |
| --- | --- |
| 价格必须带口径与快照日期 | Agent 把快照价当成实时报价给客户 |
| 链接原样引用 `doc_url` | Agent 凭记忆编出不存在的文档地址 |
| 命中不到时用站内搜索兜底 | Agent 编造产品名 |
| 数据没有的配置要说"未覆盖" | Agent 硬算/瞎猜 16C64G、GPU 机型的价格 |

实测：本技能已在 Codebuddy 内加载并跑通 11 个场景（含边界场景），过程中还反向暴露了 2 个真实缺陷（见 `docs/ACCEPTANCE.md` §D）。

---

## 5. 通道三：REST API / CLI（无人值守自动化）

不需要模型参与的固定流程，用这条通道最稳（确定性输出、可进 CI）。

### 5.1 REST

```bash
curl -s "http://127.0.0.1:8787/api/search?q=对象存储&limit=10"
curl -s "http://127.0.0.1:8787/api/prices/ecs?region=cn-beijing&vcpu=4&memory=8"
curl -s "http://127.0.0.1:8787/api/equivalents?keyword=CVM"
```

### 5.2 CLI（结构化取数）

```bash
python3 cli.py docs "对象存储" --json | python3 -c "import sys,json;print([r['name'] for r in json.load(sys.stdin)['results']])"
python3 cli.py price --spec 8c32g --charge-type on_demand_hour --json
```

### 5.3 完整范例：自动生成价格对比周报

`examples/weekly_price_report.py` 是一个**可直接运行**的自动化范例，遍历全部规格、汇总最低价分布、附口径与免责声明，产出可交付的 Markdown：

```bash
python3 examples/weekly_price_report.py                       # 进程内取数（离线可用）
python3 examples/weekly_price_report.py --api http://127.0.0.1:8787   # 走 REST 取数
python3 examples/weekly_price_report.py --region cn-shanghai --charge-type on_demand_hour --stdout
```

输出示例（截取）：

```markdown
# 四家云 ECS/CVM 价格对比周报
- 对比地域：**华北（北京）**（`cn-beijing`）
- 计价口径：元/月（包月刊例价）
- 价格快照：2026-08-12

## 4C8G（4c8g）
| 厂商 | 实例规格 | 实例族 | 厂商地域 | 按量(元/时) | 包月(元/月) | 较最低价 |
| --- | --- | --- | --- | --- | --- | --- |
| 火山引擎 | `ecs.c3i.xlarge` | 计算型 c3i | 华北2（北京） | 1.16 | 464 | **最低** |
| 阿里云 | `ecs.c7.xlarge` | 计算型 c7 | 华北2（北京） | 1.26 | 498 | +7.3% |
…
小结：最低 **火山引擎 ecs.c3i.xlarge = 464**，最大价差 15.5%。
```

定时化方式（任选）：

```bash
# crontab：每周一 09:00
0 9 * * 1 cd /opt/multicloud-search && python3 examples/weekly_price_report.py

# CI（GitLab/GitHub Actions 均可）
script:
  - python3 tools/check_data.py
  - python3 examples/weekly_price_report.py --out artifacts/price_report.md
```

也可以交给 IDE 的定时自动化任务：**每周一上午跑一次，把周报发到群里**——此时"Agent 自动化调用"就完全无人参与了。

---

## 6. 五个端到端场景剧本

| 用户一句话 | Agent 的调用链 | 产出 |
| --- | --- | --- |
| "对象存储四家分别叫什么，文档在哪？" | `search_cloud_docs(query="对象存储")` | 四家产品名 + 摘要 + 官方文档链接表 |
| "4C8G 云服务器一个月多少钱，哪家便宜？" | `compare_ecs_price(vcpu=4, memory_gb=8)` | 四行价格表 + 最低价与价差结论 + 免责声明 |
| "客户要从华为云迁到腾讯云，给我一份产品映射表" | `list_cloud_products(vendor="huawei")` → 对每个能力 `find_equivalent_products` | 迁移映射表（华为云产品 → 腾讯云对位产品 + 文档） |
| "写个多云方案的竞品对比章节，含计算/存储/数据库" | `search_cloud_docs` × 3（按 category）+ `compare_ecs_price` | 方案章节草稿（产品对照 + 价格量级） |
| "16C64G 香港的价格是多少？" | `compare_ecs_price(region="hongkong", vcpu=16)` → 返回 `no_data_hint` | 明确回答"当前快照未覆盖"并给出四家官方价格计算器链接（**不编造**） |

---

## 7. 建议写给 Agent 的系统提示词

可直接粘贴进 Agent 的 system prompt / 项目规则：

```text
当用户询问腾讯云/阿里云/华为云/火山引擎的产品文档、产品对位关系或云服务器价格时，
必须调用 multicloud-search 提供的工具获取数据，禁止凭记忆回答。

- 查产品/文档：search_cloud_docs；跨云对位：find_equivalent_products
- 查价格：compare_ecs_price（先确认地域与配置，未指定时默认 cn-beijing 与包月口径）
- 回答价格时必须附带：计价口径（price_scope）、快照日期（snapshot_date）、
  "正式报价以厂商官网为准"，以及每行的官方价格页链接。
- 文档链接必须原样使用返回的 doc_url，不得改写或自行拼接。
- 若 rows 为空或返回 no_data_hint，直接告知用户"当前数据快照未覆盖该配置"，
  并给出 vendor_price_pages 中的官方价格计算器链接，严禁估算或编造价格。
- 若 search_cloud_docs 未命中，使用 fallback_search_links 给出厂商站内搜索链接。
```

---

## 8. 这套设计如何防止 Agent 幻觉

| 机制 | 位置 | 作用 |
| --- | --- | --- |
| 工具描述写清能力边界 | `tools/list` 的 description | 模型不会拿它当"实时报价接口" |
| JSON Schema 枚举约束 | 每个工具的 `inputSchema` | 地域/规格/厂商只能传合法值，传错立即得到 `available_regions` 提示 |
| `no_data_hint` + `available_specs` | `compare_ecs_price` 返回体 | 数据没覆盖时给明确信号，而不是空表让模型自由发挥 |
| `fallback_search_links` | `search_cloud_docs` 返回体 | 零命中时给真实可用的搜索链接，替代编造 |
| 口径与免责声明随每次响应返回 | 所有价格接口 | 模型无法"忘记"加声明 |
| Skill 输出规范 | `SKILL.md` | 把上述要求写成 Agent 必须遵守的行为准则 |

---

## 9. 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 客户端里看不到工具 | 配置里不是绝对路径 / `python3` 不在 PATH | 用绝对路径；`command` 换成 `which python3` 的输出 |
| 工具返回内容过长 | 默认返回全量 Markdown 表格 | 调小 `limit`，或用 `format:"json"` 后自行裁剪 |
| Agent 仍然编造价格 | 未加系统提示词约束 | 粘贴本文 §7 的提示词；或改用 Skill 通道（自带规范） |
| 自动化脚本取不到数 | 服务未启动 / 端口不对 | 先 `curl /api/health`；或去掉 `--api` 改用进程内取数 |
| 数据过期 | 快照未复核 | 见 `DATA_SOURCES.md` §4 刷新 SOP |

协议级细节（每个工具的完整参数表与返回结构）见 [`MCP_USAGE.md`](MCP_USAGE.md)。
