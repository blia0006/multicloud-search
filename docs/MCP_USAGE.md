# MCP 接口文档（multicloud-search）

> 面向 AI Agent 的多云检索能力封装。传输方式 **stdio**，协议 **JSON-RPC 2.0 / MCP 2024-11-05**，
> 实现文件 `mcp/multicloud_mcp_server.py`，**零第三方依赖**（仅 Python 标准库）。

---

## 1. 接入配置

### Codebuddy / Claude Desktop 等 MCP 客户端

```json
{
  "mcpServers": {
    "multicloud-search": {
      "command": "python3",
      "args": ["/绝对路径/课题一/mcp/multicloud_mcp_server.py"]
    }
  }
}
```

可选环境变量：

| 变量 | 说明 |
| --- | --- |
| `MCS_DATA_DIR` | 自定义数据目录（默认项目内 `data/`），可指向团队共享维护的数据副本 |

```json
{
  "mcpServers": {
    "multicloud-search": {
      "command": "python3",
      "args": ["/opt/multicloud-search/mcp/multicloud_mcp_server.py"],
      "env": { "MCS_DATA_DIR": "/data/multicloud" }
    }
  }
}
```

### 验证是否可用

```bash
python3 tools/mcp_selftest.py          # 期望输出：18 项检查，0 项失败
```

握手与工具列表也可手工验证：

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"cli","version":"1.0"}}}' \
  | python3 mcp/multicloud_mcp_server.py

echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 mcp/multicloud_mcp_server.py
```

支持的方法：`initialize`、`notifications/initialized`、`tools/list`、`tools/call`、`ping`、`shutdown`。

---

## 2. 工具总览

| 工具 | 用途 | 必填参数 |
| --- | --- | --- |
| `search_cloud_docs` | 四家云厂商产品文档聚合搜索 | `query` |
| `compare_ecs_price` | ECS/CVM 同配置价格横向对比 | 无（全部可选） |
| `find_equivalent_products` | 跨云同类产品对照 | `keyword` |
| `list_cloud_products` | 按厂商/类目列出收录产品 | 无 |
| `list_cloud_regions` | 地域列表与四家地域 ID 映射 | 无 |

所有工具的返回结构统一为：

```jsonc
{
  "content": [{ "type": "text", "text": "…Markdown 表格，可直接展示给用户…" }],
  "structuredContent": { /* 完整结构化 JSON，供 Agent 二次加工 */ },
  "isError": false
}
```

所有工具都支持公共参数 `format`：`markdown`（默认，人类可读表格）或 `json`（`content.text` 直接为 JSON 字符串）。

---

## 3. 接口定义

### 3.1 `search_cloud_docs`

产品文档聚合搜索。支持中文名、英文名、厂商缩写与能力关键词，并自动带出四家同类产品。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | ✅ | - | 关键词，如 `对象存储`、`CVM`、`Kubernetes`、`大模型`、`WAF` |
| `vendors` | string[] | - | 全部 | 取值 `tencent`/`aliyun`/`huawei`/`volcengine` |
| `category` | string | - | 全部 | `compute`/`container`/`storage`/`network`/`database`/`bigdata`/`ai`/`security`/`devops`/`media` |
| `limit` | integer | - | 12 | 1~50 |
| `format` | string | - | `markdown` | `markdown`/`json` |

`structuredContent` 关键字段：

```jsonc
{
  "query": "对象存储",
  "total": 4,                       // 命中总数
  "returned": 4,
  "matched_equivalents": ["object-storage"],
  "groups": [{ "equivalent": "object-storage", "label": "对象存储", "vendors": ["tencent","aliyun","huawei","volcengine"] }],
  "results": [{
    "product_id": "tc-cos",
    "vendor": "tencent", "vendor_name": "腾讯云", "vendor_color": "#0052D9",
    "name": "对象存储 COS", "en": "Cloud Object Storage",
    "category": "storage", "category_name": "存储",
    "equivalent": "object-storage", "equivalent_label": "对象存储",
    "summary": "海量对象存储，兼容 S3 API，支持多存储类型与生命周期。",
    "doc_url": "https://cloud.tencent.com/document/product/436",
    "site_search_url": "https://cloud.tencent.com/search/doc/%E5%AF%B9%E8%B1%A1%E5%AD%98%E5%82%A8",
    "score": 93, "match_reasons": ["产品名匹配", "同类产品映射"]
  }],
  "fallback_search_links": [{ "vendor": "aliyun", "vendor_name": "阿里云", "url": "https://help.aliyun.com/search?k=..." }],
  "snapshot_date": "2026-08-12"
}
```

### 3.2 `compare_ecs_price`

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `region` | string | - | `cn-beijing` | `cn-beijing`（华北北京）/`cn-shanghai`（华东上海）/`cn-south`（华南广州深圳）/`hongkong`（中国香港） |
| `vcpu` | integer | - | 不限 | 如 `2`/`4`/`8` |
| `memory_gb` | integer | - | 不限 | 如 `4`/`8`/`16`/`32` |
| `spec_id` | string | - | 不限 | `2c4g`/`4c8g`/`8c16g`/`4c16g`/`8c32g`（与 vcpu/memory 二选一即可） |
| `vendors` | string[] | - | 全部 | 厂商过滤 |
| `series` | string | - | 不限 | `general`＝1:2 计算/标准型；`memory`＝1:4 通用/内存型 |
| `charge_type` | string | - | `monthly` | `monthly`（元/月）/`on_demand_hour`（元/小时），同时决定排序与价差基准 |
| `format` | string | - | `markdown` | - |

`structuredContent` 关键字段：

```jsonc
{
  "filters": { "region": "cn-beijing", "region_name": "华北（北京）", "vcpu": 4, "memory_gb": 8, "charge_type": "monthly" },
  "summary": {
    "count": 4,
    "cheapest": { "vendor": "volcengine", "vendor_name": "火山引擎", "instance_type": "ecs.c3i.xlarge", "price": 464 },
    "most_expensive": { "vendor": "tencent", "instance_type": "S5.LARGE8", "price": 536 },
    "max_gap_pct": 15.5
  },
  "rows": [{
    "vendor": "volcengine", "vendor_name": "火山引擎",
    "instance_type": "ecs.c3i.xlarge", "family": "计算型 c3i", "series": "general",
    "vcpu": 4, "memory_gb": 8,
    "region_name": "华北（北京）", "vendor_region": "华北2（北京）", "vendor_region_id": "cn-beijing",
    "on_demand_hour": 1.16, "monthly": 464, "currency": "CNY",
    "diff_vs_cheapest_pct": 0.0, "is_cheapest": true,
    "source_url": "https://www.volcengine.com/pricing?product=ECS"
  }],
  "price_scope": "仅含实例计算规格（vCPU/内存）刊例价…",
  "disclaimer": "本文件为人工维护的价格快照…",
  "snapshot_date": "2026-08-12",
  "no_data_hint": "",                 // 无匹配时给出的说明（含可用规格列表）
  "available_specs": ["2c4g","4c8g","8c16g","4c16g","8c32g"],
  "vendor_price_pages": { "tencent": "https://buy.cloud.tencent.com/price/cvm/calculator" },
  "extras": { "system_disk_ssd_per_gb_month": { "tencent": 1.0 }, "bandwidth_fixed_per_mbps_month": { "tencent": 25.0 } }
}
```

地域非法时返回 `{"error":"unknown_region","available_regions":[...]}`，不抛异常。
筛选条件无匹配（如 `vcpu: 16`）时 `rows` 为空数组，同时 `no_data_hint` 给出「当前快照未覆盖 + 可用规格」说明，
Markdown 输出中会附四家官方价格计算器链接——此时应把该提示转达用户，**不要编造价格**。

### 3.3 `find_equivalent_products`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keyword` | string | ✅ | 任一厂商产品名/缩写/能力词，如 `CVM`、`OSS`、`DCS`、`veDB`、`弹性伸缩` |
| `format` | string | - | `markdown`/`json` |

返回 `matches[]`，每项含 `equivalent`、`label` 与 `vendors`（四家各自的产品名、摘要、文档链接）。

### 3.4 `list_cloud_products`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `vendor` | string | `tencent`/`aliyun`/`huawei`/`volcengine` |
| `category` | string | 同 `search_cloud_docs` 的类目枚举 |
| `format` | string | `markdown`/`json` |

返回 `total`、`count_by_vendor`、`products[]`。

### 3.5 `list_cloud_regions`

无业务参数。返回统一地域 ID → 四家真实地域 ID/名称映射，用于在报价单里写清"腾讯云 ap-beijing 对齐阿里云 cn-beijing"。

---

## 4. 调用示例（真实返回）

### 示例 1：客户问「对象存储四家分别叫什么、文档在哪」

请求：

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_cloud_docs","arguments":{"query":"Kubernetes","limit":4}}}
```

命令行复现：

```bash
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_cloud_docs","arguments":{"query":"Kubernetes","limit":4}}}' \
  | python3 mcp/multicloud_mcp_server.py
```

`content[0].text` 实际返回：

```markdown
### 文档聚合搜索：`Kubernetes`

命中 **4** 条，展示 4 条 ｜ 索引快照 2026-08-12

| 厂商 | 产品 | 类目 | 摘要 | 文档链接 |
| --- | --- | --- | --- | --- |
| 腾讯云 | 容器服务 TKE | 容器与中间件 | 原生 Kubernetes 托管集群，支持托管/独立集群与 Serverless 容器。 | [打开](https://cloud.tencent.com/document/product/457) |
| 阿里云 | 容器服务 ACK | 容器与中间件 | 托管 Kubernetes 集群，含 Pro 版、Serverless 版与边缘版。 | [打开](https://help.aliyun.com/zh/ack/) |
| 火山引擎 | 容器服务 VKE | 容器与中间件 | 托管 Kubernetes 集群，支持 VPC-CNI 高性能网络与弹性容器。 | [打开](https://www.volcengine.com/docs/6460) |
| 华为云 | 云容器引擎 CCE | 容器与中间件 | 托管 Kubernetes 集群，含 CCE Turbo 与 CCE Autopilot。 | [打开](https://support.huaweicloud.com/cce/) |

**同类产品覆盖情况**：Kubernetes 容器服务（4 家）
```

### 示例 2：客户要 8C32G 云服务器在上海的包月刊例价对比

请求：

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"compare_ecs_price","arguments":{"region":"cn-shanghai","spec_id":"8c32g","charge_type":"monthly"}}}
```

`content[0].text` 实际返回：

```markdown
### ECS/CVM 价格对比 — 华东（上海）

筛选：vCPU=any ｜ 内存=anyGB ｜ 规格=8c32g ｜ 系列=any ｜ 计费口径=包月（元/月） ｜ 价格快照 2026-08-12

| 厂商 | 实例规格 | 实例族 | 配置 | 厂商地域 | 按量(元/时) | 包月(元/月) | 较最低价 | 官方价格页 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 火山引擎 | `ecs.g3i.2xlarge` | 通用型 g3i | 8C32G | 华东2（上海） | 3.4 | 1344 | **最低** | [价格页](https://www.volcengine.com/pricing?product=ECS) |
| 阿里云 | `ecs.g7.2xlarge` | 通用型 g7 | 8C32G | 华东2（上海） | 3.58 | 1416 | +5.4% | [价格页](https://www.aliyun.com/price/product#/ecs/detail) |
| 华为云 | `s6.2xlarge.4` | 通用计算型 s6 | 8C32G | 华东-上海一 | 3.68 | 1456 | +8.3% | [价格页](https://www.huaweicloud.com/pricing/calculator.html#/ecs) |
| 腾讯云 | `M5.2XLARGE32` | 内存型 M5 | 8C32G | 上海 | 3.76 | 1488 | +10.7% | [价格页](https://buy.cloud.tencent.com/price/cvm/calculator) |

**结论**：最低 火山引擎 `ecs.g3i.2xlarge` = 1344 元；最高 腾讯云 `M5.2XLARGE32` = 1488 元；最大价差 10.7%
```

### 示例 3：做迁移映射（要结构化数据）

```json
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"find_equivalent_products","arguments":{"keyword":"DCS","format":"json"}}}
```

返回 `华为云 DCS ↔ 腾讯云 云数据库 Redis ↔ 阿里云 Redis/Tair ↔ 火山引擎 Redis 版` 的四家对照，含文档链接，可直接渲染成迁移映射表。

### 示例 4：只看两家、只看按量单价

```json
{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"compare_ecs_price","arguments":{"vendors":["tencent","volcengine"],"vcpu":8,"memory_gb":16,"charge_type":"on_demand_hour"}}}
```

---

## 5. Agent 使用规范（建议写入系统提示）

1. 价格结论必须附带**口径与快照日期**，并提示"正式报价以官网为准"（返回体已带 `price_scope`/`disclaimer`/`snapshot_date`）。
2. 文档链接**原样引用** `doc_url`，不要改写或凭记忆生成。
3. `search_cloud_docs` 未命中时，使用返回体 `fallback_search_links` 给出厂商站内搜索链接，**不要编造产品名或文档地址**。
4. 数据集未覆盖的配置（如 16C64G、GPU 机型）应明确说明"当前快照未覆盖"，并给出 `vendor_price_pages` 中的官方价格计算器链接。
5. 需要跨云替换/迁移说明时优先用 `find_equivalent_products`，它的映射是人工校对的能力对位关系。

---

## 6. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 客户端里看不到工具 | 路径非绝对路径，或 `python3` 不在 PATH | 用绝对路径；`command` 改为 `which python3` 的完整路径 |
| 启动即退出 | 数据文件缺失 | 确认 `data/products.json`、`data/ecs_prices.json` 存在；或设置 `MCS_DATA_DIR` |
| 返回 `Method not found` | 客户端使用了未实现的方法 | 已实现 `initialize`/`tools/list`/`tools/call`/`ping`/`shutdown`；其他方法按协议返回 `-32601` |
| 工具返回内容太长 | 默认 markdown 全量表格 | 调小 `limit`，或用 `format: "json"` 后自行裁剪 |
| 价格数据过期 | 快照未复核 | 见 [`DATA_SOURCES.md`](DATA_SOURCES.md) 的刷新 SOP |
