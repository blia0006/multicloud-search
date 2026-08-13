# 数据来源、口径与刷新策略

## 1. 结论先行

| 数据集 | 文件 | 来源方式 | 刷新频率 | 责任人 |
| --- | --- | --- | --- | --- |
| 产品文档索引（176 条） | `data/products.json` | **人工维护**（依据四家官网文档站产品入口整理）+ 脚本校验 | 季度巡检 + 事件驱动（新产品发布/文档站改版即时补录） | SA 团队轮值 |
| ECS/CVM 价格快照（20 条机型 × 4 地域） | `data/ecs_prices.json` | **人工维护**（依据四家官网价格页/价格计算器刊例价） | 月度复核（字段 `data_quality.next_review` 标注下次复核日期） | SA 团队轮值 |
| 跨云同类映射（42 组） | `data/products.json > equivalents` | 人工定义（产品能力对位） | 随产品索引一起维护 | 同上 |

> 平台内所有价格与摘要均为**快照**，页面与 API 响应中常驻 `snapshot_date` 与免责声明；对客报价必须回官网价格页核对（每条记录自带 `source_url`）。

---

## 2. 为什么选择"静态维护 + 官方链接直达"，而不是在线爬取

在实现前对四家文档站与价格站做了可行性验证，结论如下：

| 厂商 | 文档搜索接口探测结果 | 结论 |
| --- | --- | --- |
| 腾讯云 | 文档页可直接访问，无效文档 ID 返回真实 404（可自动校验） | 链接可自动巡检 |
| 阿里云 | 搜索接口返回 `Security Verification`（风控拦截，需要 JS 挑战） | 不可稳定爬取 |
| 华为云 | 文档站为 SPA，任意路径均返回 200 外壳，内容由前端渲染 | 无法用 HTTP 状态判定，爬取需无头浏览器 |
| 火山引擎 | 同为 SPA，无服务端标题，产品页/文档页均返回 200 空壳 | 同上 |

因此本项目采用的策略是：

1. **主数据静态维护**：把四家主流 IaaS/PaaS 产品的名称、英文名、缩写、能力摘要、类目、官方文档入口结构化沉淀，检索完全离线、结果确定、响应毫秒级，不受厂商风控与站点改版影响；
2. **长尾用站内搜索兜底**：每张卡片除"官方文档"外还提供"站内搜索"按钮，用当前关键词跳到厂商文档站搜索页，覆盖 API 细节、错误码、最佳实践等长尾内容；
3. **可自动校验的部分自动化**：`tools/check_data.py --check-links` 对官方域名白名单做可达性巡检（腾讯云可精确判定 404）；
4. **不做无头浏览器爬取**：规避反爬对抗、`robots.txt` 与站点条款风险、运维成本与稳定性风险；若后续确有需求，应走厂商开放的官方渠道（如价格查询 OpenAPI）而非页面抓取。

### 未来可选的自动化升级路径（有需要再做）

| 能力 | 官方渠道 | 说明 |
| --- | --- | --- |
| 腾讯云价格 | CVM `DescribeZoneInstanceConfigInfos` / `InquiryPriceRunInstances` | 需 SecretId/SecretKey，**必须走环境变量注入，禁止写入仓库** |
| 阿里云价格 | BSS OpenAPI `GetPayAsYouGoPrice` / `GetSubscriptionPrice` | 同上 |
| 华为云价格 | 云商店/价格查询 API `ListOnDemandResourceRatings` | 同上 |
| 火山引擎价格 | 计费 OpenAPI | 同上 |

接入原则：只读权限的子账号 + 密钥仅从环境变量读取 + 抓取结果写回 `data/ecs_prices.json` 并保留 `snapshot_date`，仍由 `tools/check_data.py` 校验后提交。

---

## 3. 字段规范

### 3.1 `data/products.json`

```jsonc
{
  "snapshot_date": "2026-08-12",          // 索引快照日期
  "vendors": {                             // 厂商元数据
    "tencent": {
      "name": "腾讯云",
      "color": "#0052D9",                 // 卡片徽章品牌色
      "doc_home": "https://cloud.tencent.com/document",
      "doc_search": "https://cloud.tencent.com/search/doc/{q}",  // {q} 为关键词占位符
      "price_home": "https://buy.cloud.tencent.com/price/cvm/calculator"
    }
  },
  "categories": [{ "id": "compute", "name": "计算" }],
  "equivalents": {                         // 跨云同类映射（检索召回的关键）
    "object-storage": {
      "label": "对象存储",
      "aliases": ["对象存储", "cos", "oss", "obs", "tos", "s3", "bucket"]
    }
  },
  "products": [{
    "id": "tc-cos",                        // 全局唯一，格式 <厂商前缀>-<产品缩写>
    "vendor": "tencent",                   // tencent | aliyun | huawei | volcengine
    "name": "对象存储 COS",                 // 官方中文名（含缩写）
    "en": "Cloud Object Storage",
    "cat": "compute",                      // 必须存在于 categories
    "equiv": "object-storage",              // 必须存在于 equivalents
    "aliases": ["cos"],                    // 该产品专属别名
    "summary": "海量对象存储，兼容 S3 API…",   // 一句话摘要，建议 ≤ 45 字
    "doc_url": "https://cloud.tencent.com/document/product/436"  // 必须 https + 官方域名
  }]
}
```

新增产品时的**硬性要求**（`tools/check_data.py` 会校验）：

- `id` 唯一；`vendor` / `cat` / `equiv` 合法；`summary`、`doc_url` 非空；
- `doc_url` 必须 `https://` 且域名在白名单内（`cloud.tencent.com`、`help.aliyun.com`、`support.huaweicloud.com`、`www.volcengine.com` 等）；
- 新增能力若四家都有对应产品，应同时补齐 4 条记录，保持覆盖矩阵完整。

### 3.2 `data/ecs_prices.json`

```jsonc
{
  "snapshot_date": "2026-08-12",
  "currency": "CNY",
  "price_scope": "仅含实例计算规格（vCPU/内存）刊例价，不含系统盘、数据盘、公网带宽…",
  "data_quality": { "source": "manual", "verified_by": "SA 人工核对", "next_review": "2026-09-12" },
  "regions": [{
    "id": "cn-beijing", "name": "华北（北京）",
    "vendor_regions": {                    // 统一地域 → 四家地域 ID/名称映射
      "tencent": { "id": "ap-beijing", "name": "北京" }
    }
  }],
  "specs": [{ "id": "4c8g", "vcpu": 4, "memory_gb": 8, "ratio": "1:2" }],
  "items": [{
    "vendor": "tencent",
    "product": "云服务器 CVM",
    "instance_type": "S5.LARGE8",          // 厂商官方实例规格名
    "family": "标准型 S5",                  // 实例族
    "series": "general",                   // general=1:2；memory=1:4
    "spec_id": "4c8g", "vcpu": 4, "memory_gb": 8,
    "prices": {                            // 每个地域两个口径
      "cn-beijing": { "on_demand_hour": 1.36, "monthly": 536 }
    },
    "source_url": "https://buy.cloud.tencent.com/price/cvm/calculator"
  }]
}
```

价格口径统一约定（**必须一致，否则对比无意义**）：

1. 只取**刊例价**（未含任何折扣、代金券、承诺消费优惠）；
2. 只含**实例计算规格**（vCPU + 内存），不含系统盘、数据盘、公网带宽、镜像、快照；
3. `on_demand_hour` = 按量计费单价（元/小时）；`monthly` = 包月刊例价（元/月）；
4. 地域按 `regions` 的统一 ID 对齐，`vendor_regions` 记录各家真实地域 ID，避免"北京 vs 华北2"错配；
5. 同一 `spec_id` 下四家实例族应尽量选择**同代次、同定位**机型（计算型对计算型、通用型对通用型）。

---

## 4. 刷新 SOP

### 4.1 月度价格复核（约 30 分钟）

1. 打开四家官方价格页（`data/ecs_prices.json > vendor_price_pages`，或页面表格每行的"官方价格页"链接）：
   - 腾讯云：<https://buy.cloud.tencent.com/price/cvm/calculator>
   - 阿里云：<https://www.aliyun.com/price/product#/ecs/detail>
   - 华为云：<https://www.huaweicloud.com/pricing/calculator.html#/ecs>
   - 火山引擎：<https://www.volcengine.com/pricing?product=ECS>
2. 逐条核对 20 条机型记录在 4 个地域的按量与包月刊例价；
3. 更新 `items[].prices`，同步更新顶层 `snapshot_date` 与 `data_quality.next_review`（+1 月）；
4. 若厂商下线机型/上线新代次，替换 `instance_type`、`family` 并在提交说明里写明；
5. 执行校验并提交：

```bash
python3 tools/check_data.py            # 必须"结构校验通过 ✓"
python3 cli.py price --vcpu 4 --memory 8
python3 tools/build_static.py          # 如使用单文件部署形态，需重新构建
```

### 4.2 季度产品索引巡检（约 1 小时）

```bash
# 1. 覆盖矩阵，检查是否出现缺口
python3 tools/check_data.py

# 2. 链接巡检（腾讯云可精确判定；其余厂商抽查）
python3 tools/check_data.py --check-links --report reports/link_check.csv
```

1. 修复 `reports/link_check.csv` 中标记 `CHECK` 的链接；
2. 阿里云/华为云/火山引擎按 `--report` 输出抽查 10~15 条（SPA 站点无法自动判定）；
3. 补录本季度新发布的重要产品（尤其 AI/大模型、云原生数据库等高频变动领域）；
4. 更新 `products.json > snapshot_date`。

### 4.3 事件驱动补录

触发条件：客户方案中出现索引未覆盖的产品、厂商文档站改版导致链接失效、新增地域需求。
处理：当天补录并跑 `tools/check_data.py`，无需等到巡检周期。

---

## 5. 数据质量看板（脚本输出）

```bash
python3 tools/check_data.py
```

输出三部分：

1. **结构校验**：字段完整性、引用一致性、URL 合法性（有错即 `exit 1`，可接入 CI/pre-commit）；
2. **覆盖矩阵**：42 组同类产品 × 4 家的 ✓/— 矩阵，并列出"待补全清单"；
3. **各厂商收录数量**：当前为四家各 44 个，共 176 个。

建议接入 Git pre-commit：

```bash
# .git/hooks/pre-commit
#!/bin/sh
python3 tools/check_data.py || { echo "数据校验失败，提交已阻止"; exit 1; }
```

---

## 6. 免责声明（页面与 API 响应中同步展示）

- 本平台数据为人工整理的快照，用于**方案初估与量级对比**；
- 各厂商产品能力、机型代次与价格随时调整，**正式对客材料与报价必须以厂商官网/官方报价为准**；
- 跨云"同类产品"为能力对位归类，不代表功能完全等价，具体差异需查阅各自官方文档。
