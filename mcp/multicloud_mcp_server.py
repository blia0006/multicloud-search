#!/usr/bin/env python3
"""多云产品检索 MCP Server（stdio 传输，JSON-RPC 2.0，零第三方依赖）。

暴露 5 个工具给 AI Agent：
    search_cloud_docs         —— 四家云厂商产品文档聚合搜索
    compare_ecs_price         —— ECS/CVM 同配置价格横向对比
    find_equivalent_products  —— 跨云同类产品对照（CVM ↔ ECS ↔ ECS ↔ ECS）
    list_cloud_products       —— 按厂商/类目列出收录产品
    list_cloud_regions        —— 地域列表与四家地域 ID 映射

在 Codebuddy / Claude Desktop 等 MCP 客户端中配置：
    {
      "mcpServers": {
        "multicloud-search": {
          "command": "python3",
          "args": ["<项目绝对路径>/mcp/multicloud_mcp_server.py"]
        }
      }
    }

手动调试：
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 mcp/multicloud_mcp_server.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import engine  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "multicloud-search", "version": "1.0.0"}

VENDOR_ENUM = ["tencent", "aliyun", "huawei", "volcengine"]

TOOLS = [
    {
        "name": "search_cloud_docs",
        "description": (
            "在腾讯云/阿里云/华为云/火山引擎四家官方文档产品索引中聚合搜索。"
            "支持中文名、英文名、产品缩写（如 CVM/OSS/OBS/TOS）以及能力关键词（如『对象存储』『Kubernetes』），"
            "会自动带出四家的同类产品，返回产品名称、摘要、来源厂商与官方文档链接。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，如 '对象存储'、'CVM'、'Kubernetes'、'大模型'"},
                "vendors": {
                    "type": "array",
                    "items": {"type": "string", "enum": VENDOR_ENUM},
                    "description": "限定厂商，缺省搜索全部四家",
                },
                "category": {
                    "type": "string",
                    "enum": ["compute", "container", "storage", "network", "database", "bigdata", "ai", "security", "devops", "media"],
                    "description": "限定产品类目",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 12},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_ecs_price",
        "description": (
            "对比四家云厂商 ECS/CVM 在相同地域与相同配置下的刊例价（包月价与按量小时价），"
            "返回实例规格、实例族、厂商地域 ID、价格、与最低价差百分比及官方价格页链接。"
            "价格为人工维护快照，正式报价需回官网核对。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "enum": ["cn-beijing", "cn-shanghai", "cn-south", "hongkong"],
                    "default": "cn-beijing",
                    "description": "统一地域 ID（cn-south 表示华南广州/深圳）",
                },
                "vcpu": {"type": "integer", "description": "vCPU 核数，如 2/4/8"},
                "memory_gb": {"type": "integer", "description": "内存 GB，如 4/8/16/32"},
                "spec_id": {"type": "string", "enum": ["2c4g", "4c8g", "8c16g", "4c16g", "8c32g"], "description": "规格快捷 ID"},
                "vendors": {"type": "array", "items": {"type": "string", "enum": VENDOR_ENUM}},
                "series": {"type": "string", "enum": ["general", "memory"], "description": "general=1:2 计算/标准型；memory=1:4 通用/内存型"},
                "charge_type": {"type": "string", "enum": ["monthly", "on_demand_hour"], "default": "monthly"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    },
    {
        "name": "find_equivalent_products",
        "description": "输入任一厂商的产品名或缩写（如 CVM、OSS、DCS、veDB），返回四家云厂商的同类产品对照表与文档链接。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "产品名/缩写/能力关键词"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "list_cloud_products",
        "description": "列出平台已收录的云产品（可按厂商与类目过滤），用于了解覆盖范围或生成方案清单。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "enum": VENDOR_ENUM},
                "category": {"type": "string", "enum": ["compute", "container", "storage", "network", "database", "bigdata", "ai", "security", "devops", "media"]},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    },
    {
        "name": "list_cloud_regions",
        "description": "列出价格对比支持的统一地域，以及四家厂商各自的地域 ID / 名称映射。",
        "inputSchema": {"type": "object", "properties": {"format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"}}},
    },
]


# --------------------------------------------------------------------------- #
# 结果渲染
# --------------------------------------------------------------------------- #
def _md_docs(res: Dict[str, Any]) -> str:
    lines = [
        "### 文档聚合搜索：`%s`" % (res["query"] or "全部"),
        "",
        "命中 **%d** 条，展示 %d 条 ｜ 索引快照 %s" % (res["total"], res["returned"], res["snapshot_date"]),
        "",
        "| 厂商 | 产品 | 类目 | 摘要 | 文档链接 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in res["results"]:
        lines.append(
            "| %s | %s | %s | %s | [打开](%s) |"
            % (r["vendor_name"], r["name"], r["category_name"], r["summary"].replace("|", "/"), r["doc_url"])
        )
    if not res["results"]:
        lines.append("| - | 本地索引未命中 | - | 可使用下方站内搜索链接 | - |")
        for link in res["fallback_search_links"]:
            lines.append("")
            lines.append("- %s 站内搜索：%s" % (link["vendor_name"], link["url"]))
    if res["groups"]:
        lines += ["", "**同类产品覆盖情况**：" + "；".join(
            "%s（%d 家）" % (g["label"], len(g["vendors"])) for g in res["groups"][:5]
        )]
    return "\n".join(lines)


def _md_price(res: Dict[str, Any]) -> str:
    if res.get("error"):
        return "查询失败：%s" % res.get("message")
    f = res["filters"]
    ct_label = "包月（元/月）" if f["charge_type"] == "monthly" else "按量（元/小时）"
    lines = [
        "### ECS/CVM 价格对比 — %s" % f["region_name"],
        "",
        "筛选：vCPU=%s ｜ 内存=%sGB ｜ 规格=%s ｜ 系列=%s ｜ 计费口径=%s ｜ 价格快照 %s"
        % (f["vcpu"] or "any", f["memory_gb"] or "any", f["spec_id"] or "any", f["series"] or "any", ct_label, res["snapshot_date"]),
        "",
        "| 厂商 | 实例规格 | 实例族 | 配置 | 厂商地域 | 按量(元/时) | 包月(元/月) | 较最低价 | 官方价格页 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in res["rows"]:
        diff = "**最低**" if r.get("is_cheapest") else (
            "+%.1f%%" % r["diff_vs_cheapest_pct"] if r.get("diff_vs_cheapest_pct") is not None else "-"
        )
        lines.append(
            "| %s | `%s` | %s | %dC%dG | %s | %s | %s | %s | [价格页](%s) |"
            % (r["vendor_name"], r["instance_type"], r["family"], r["vcpu"], r["memory_gb"],
               r["vendor_region"], r["on_demand_hour"], r["monthly"], diff, r["source_url"])
        )
    s = res.get("summary", {})
    if not res["rows"]:
        lines += ["", "**当前快照未覆盖该配置**：" + res.get("no_data_hint", ""), "",
                  "官方价格计算器："]
        for vendor, url in (res.get("vendor_price_pages") or {}).items():
            lines.append("- %s：%s" % (vendor, url))
    if s.get("cheapest"):
        lines += [
            "",
            "**结论**：最低 %s `%s` = %s 元；最高 %s `%s` = %s 元；最大价差 %.1f%%"
            % (s["cheapest"]["vendor_name"], s["cheapest"]["instance_type"], s["cheapest"]["price"],
               s["most_expensive"]["vendor_name"], s["most_expensive"]["instance_type"],
               s["most_expensive"]["price"], s.get("max_gap_pct") or 0),
        ]
    lines += ["", "口径：%s" % res["price_scope"], "", "> %s" % res["disclaimer"]]
    return "\n".join(lines)


def _md_equiv(res: Dict[str, Any]) -> str:
    if not res["matches"]:
        return "未找到 `%s` 的同类产品映射，可改用 search_cloud_docs 做关键词检索。" % res["keyword"]
    lines = ["### 跨云同类产品对照：`%s`" % res["keyword"]]
    for m in res["matches"]:
        lines += ["", "#### %s" % m["label"], "", "| 厂商 | 产品 | 摘要 | 文档 |", "| --- | --- | --- | --- |"]
        for _vendor, items in m["vendors"].items():
            for it in items:
                lines.append("| %s | %s | %s | [打开](%s) |"
                             % (it["vendor_name"], it["name"], it["summary"].replace("|", "/"), it["doc_url"]))
    return "\n".join(lines)


def _md_products(res: Dict[str, Any]) -> str:
    lines = ["### 已收录产品（共 %d 个）" % res["total"], "",
             "分布：" + "、".join("%s %d" % (k, v) for k, v in res["count_by_vendor"].items()), "",
             "| 厂商 | 产品 | 类目 | 文档 |", "| --- | --- | --- | --- |"]
    for p in res["products"]:
        lines.append("| %s | %s | %s | [打开](%s) |" % (p["vendor_name"], p["name"], p["category_name"], p["doc_url"]))
    return "\n".join(lines)


def _md_regions(res: Dict[str, Any]) -> str:
    lines = ["### 地域映射", "", "| 统一地域 | 名称 | 腾讯云 | 阿里云 | 华为云 | 火山引擎 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in res["regions"]:
        vr = r["vendor_regions"]
        lines.append("| `%s` | %s | %s(`%s`) | %s(`%s`) | %s(`%s`) | %s(`%s`) |" % (
            r["id"], r["name"],
            vr["tencent"]["name"], vr["tencent"]["id"],
            vr["aliyun"]["name"], vr["aliyun"]["id"],
            vr["huawei"]["name"], vr["huawei"]["id"],
            vr["volcengine"]["name"], vr["volcengine"]["id"],
        ))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 工具调度
# --------------------------------------------------------------------------- #
def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    args = args or {}
    fmt = args.get("format", "markdown")

    if name == "search_cloud_docs":
        res = engine.search_docs(
            query=args.get("query", ""),
            vendors=args.get("vendors"),
            category=args.get("category"),
            limit=args.get("limit", 12),
        )
        text = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else _md_docs(res)
    elif name == "compare_ecs_price":
        res = engine.compare_ecs_price(
            region=args.get("region", "cn-beijing"),
            vcpu=args.get("vcpu"),
            memory_gb=args.get("memory_gb"),
            spec_id=args.get("spec_id"),
            vendors=args.get("vendors"),
            series=args.get("series"),
            charge_type=args.get("charge_type", "monthly"),
        )
        text = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else _md_price(res)
    elif name == "find_equivalent_products":
        res = engine.find_equivalents(args.get("keyword", ""))
        text = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else _md_equiv(res)
    elif name == "list_cloud_products":
        res = engine.list_products(vendor=args.get("vendor"), category=args.get("category"))
        text = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else _md_products(res)
    elif name == "list_cloud_regions":
        res = engine.list_regions()
        text = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else _md_regions(res)
    else:
        return {"content": [{"type": "text", "text": "未知工具：%s" % name}], "isError": True}

    return {"content": [{"type": "text", "text": text}], "structuredContent": res, "isError": False}


def handle(request: Dict[str, Any]):
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": "多云（腾讯云/阿里云/华为云/火山引擎）产品文档检索与 ECS 价格对比工具集。",
        }
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params.get("name", ""), params.get("arguments") or {})
    if method in ("shutdown",):
        return {}
    raise ValueError("Method not found: %s" % method)


def main() -> int:
    stdin = sys.stdin
    stdout = sys.stdout
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "Parse error"}}, ensure_ascii=False) + "\n")
            stdout.flush()
            continue

        req_id = request.get("id")
        try:
            result = handle(request)
        except ValueError as exc:
            if req_id is not None:
                stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id,
                                         "error": {"code": -32601, "message": str(exc)}}, ensure_ascii=False) + "\n")
                stdout.flush()
            continue
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            if req_id is not None:
                stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id,
                                         "error": {"code": -32603, "message": "Internal error: %s" % exc}},
                                        ensure_ascii=False) + "\n")
                stdout.flush()
            continue

        if req_id is None or result is None:
            continue
        stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
