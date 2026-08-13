---
name: multicloud-lookup
description: 查询和对比腾讯云、阿里云、华为云、火山引擎四家云厂商的产品文档与 ECS/CVM 价格。当用户需要多云产品选型、跨云同类产品对照（如 CVM 对应阿里云什么产品）、云服务器刊例价对比、或撰写多云方案/迁移映射表时使用本技能。
---

# 多云产品信息一站式检索（Skill）

本技能封装了本地维护的四家云厂商产品索引与 ECS/CVM 价格快照，通过 `cli.py` 提供确定性查询，
无需联网、无需 API Key，输出可直接粘贴进方案文档。

## 何时使用

- 用户问「XX 能力四家云分别叫什么」「腾讯云 CVM 对应阿里云/华为云/火山引擎哪个产品」
- 用户要「4C8G 在四家云一个月多少钱」「哪家云服务器最便宜」「按量计费单价对比」
- 用户要写多云方案、竞品对比章节、迁移映射表、报价初估
- 用户要找某个云产品的官方文档链接

## 可用命令

工作目录为本项目根目录（`cli.py` 所在目录）。所有命令均可加 `--json` 输出结构化结果。

| 场景 | 命令 |
| --- | --- |
| 文档聚合搜索 | `python3 cli.py docs "<关键词>" [--vendors tencent,aliyun,huawei,volcengine] [--category compute] [--limit 20]` |
| ECS 价格对比 | `python3 cli.py price [--region cn-beijing] [--vcpu 4] [--memory 8] [--spec 4c8g] [--series general\|memory] [--charge-type monthly\|on_demand_hour] [--vendors ...]` |
| 跨云同类对照 | `python3 cli.py equiv "<产品名或缩写>"` |
| 产品清单 | `python3 cli.py products [--vendor huawei] [--category database]` |
| 地域映射 | `python3 cli.py regions` |
| 平台元数据 | `python3 cli.py meta` |

参数取值：

- `--vendors` / `--vendor`：`tencent`、`aliyun`、`huawei`、`volcengine`（也接受「腾讯云/阿里云/华为云/火山引擎」）
- `--category`：`compute`、`container`、`storage`、`network`、`database`、`bigdata`、`ai`、`security`、`devops`、`media`
- `--region`：`cn-beijing`（华北北京）、`cn-shanghai`（华东上海）、`cn-south`（华南广州/深圳）、`hongkong`（中国香港）
- `--spec`：`2c4g`、`4c8g`、`8c16g`、`4c16g`、`8c32g`

## 调用示例

### 示例 1：客户问「对象存储四家分别叫什么，文档在哪」

```bash
python3 cli.py docs "对象存储"
```

输出四张卡片式记录（腾讯云 COS / 阿里云 OSS / 华为云 OBS / 火山引擎 TOS），含摘要与官方文档直达链接。
把结果整理成「产品名 + 一句话摘要 + 文档链接」的表格回复用户。

### 示例 2：客户要 4C8G 云服务器四家包月刊例价对比

```bash
python3 cli.py price --vcpu 4 --memory 8 --region cn-beijing
```

输出按价格升序的四行对比（实例规格、实例族、厂商地域、按量单价、包月刊例价、较最低价差）以及最低/最高价结论。
回复时必须带上「价格为快照数据，正式报价以官网为准」的说明，并给出官方价格页链接。

### 示例 3：写迁移映射表（结构化取数）

```bash
python3 cli.py equiv "DCS" --json
python3 cli.py price --spec 8c32g --charge-type on_demand_hour --json
```

用 `--json` 拿到结构化数据后自行渲染 Markdown 表格。

## 输出使用规范

1. **价格必须带口径与免责声明**：仅含实例 vCPU/内存刊例价，不含系统盘、公网带宽与商务折扣；数据为人工维护快照（`data/ecs_prices.json` 的 `snapshot_date`）。
2. **链接原样引用**：不要改写 `doc_url` / `source_url`。
3. **命中不到时**：使用 `docs` 命令输出中的「厂商站内搜索」链接兜底，不要凭记忆编造文档地址或产品名。
4. **不要编造价格**：数据文件里没有的配置（如 16C64G、GPU 机型）会返回「（无匹配记录）」并给出 `no_data_hint` 与四家官方价格计算器链接，直接把该提示与链接转达用户即可。
5. **参数位置**：`--json` 放在子命令前后均可（`cli.py --json equiv CVM` 与 `cli.py equiv CVM --json` 等价）。

## 数据位置与刷新

- 产品索引：`data/products.json`（176 个产品，四家各 44 个）
- 价格快照：`data/ecs_prices.json`（4 地域 × 5 规格 × 4 厂商）
- 刷新与校验：`python3 tools/check_data.py`（结构校验 + 覆盖矩阵），`--check-links` 可巡检文档链接
- 刷新策略详见 `docs/DATA_SOURCES.md`
