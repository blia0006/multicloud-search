#!/usr/bin/env python3
"""多云检索平台命令行工具（供人工、脚本与 Codebuddy Skill 调用）。

用法示例：
    python3 cli.py docs "对象存储"                      # 四家同类产品文档聚合搜索
    python3 cli.py docs "Kubernetes" --vendors tencent,aliyun --limit 8
    python3 cli.py price --vcpu 4 --memory 8 --region cn-beijing
    python3 cli.py price --spec 8c32g --charge-type on_demand_hour
    python3 cli.py equiv CVM                            # 跨云同类产品对照
    python3 cli.py products --vendor huawei --category database
    python3 cli.py regions
加 --json 输出机器可读结果。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import engine  # noqa: E402


def _dump(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_docs(res) -> None:
    print("查询：%s ｜ 命中 %d 条（展示 %d 条）｜ 数据快照 %s"
          % (res["query"] or "(全部)", res["total"], res["returned"], res["snapshot_date"]))
    if res["matched_equivalents"]:
        print("识别到同类产品类别：%s" % ", ".join(res["matched_equivalents"]))
    print("-" * 96)
    for i, r in enumerate(res["results"], 1):
        print("%2d. [%s] %s %s" % (i, r["vendor_name"], r["name"], ("(%s)" % r["en"]) if r["en"] else ""))
        print("    类目：%s ｜ 同类：%s ｜ 匹配：%s"
              % (r["category_name"], r["equivalent_label"] or "-", "/".join(r["match_reasons"])))
        print("    摘要：%s" % r["summary"])
        print("    文档：%s" % r["doc_url"])
    if not res["results"]:
        print("未命中本地索引，可使用厂商站内搜索：")
        for link in res["fallback_search_links"]:
            print("  - %s: %s" % (link["vendor_name"], link["url"]))


def _print_price(res) -> None:
    if res.get("error"):
        print("错误：%s" % res.get("message"))
        return
    f = res["filters"]
    print("地域：%s ｜ 规格筛选：vCPU=%s 内存=%sGB spec=%s series=%s ｜ 计费：%s ｜ 快照 %s"
          % (f["region_name"], f["vcpu"] or "any", f["memory_gb"] or "any", f["spec_id"] or "any",
             f["series"] or "any", f["charge_type"], res["snapshot_date"]))
    print("-" * 108)
    header = "%-8s %-16s %-22s %-8s %-10s %12s %12s %10s" % (
        "厂商", "实例规格", "实例族", "配置", "地域", "按量(元/时)", "包月(元/月)", "较最低")
    print(header)
    print("-" * 108)
    for r in res["rows"]:
        print("%-8s %-16s %-22s %-8s %-10s %12s %12s %10s" % (
            r["vendor_name"],
            r["instance_type"],
            r["family"],
            "%dC%dG" % (r["vcpu"], r["memory_gb"]),
            r["vendor_region"] or r["region_name"],
            r["on_demand_hour"],
            r["monthly"],
            ("最低" if r.get("is_cheapest") else ("+%.1f%%" % r["diff_vs_cheapest_pct"])
             if r.get("diff_vs_cheapest_pct") is not None else "-"),
        ))
    if not res["rows"]:
        print("（无匹配记录）")
        print("-" * 108)
        print("提示：%s" % res.get("no_data_hint", ""))
        for vendor, url in (res.get("vendor_price_pages") or {}).items():
            print("  官方价格计算器 - %-12s %s" % (vendor, url))
    s = res.get("summary", {})
    if s.get("cheapest"):
        print("-" * 108)
        print("最低价：%s %s = %s 元（%s）｜ 最高价：%s %s = %s 元 ｜ 最大价差 %.1f%%"
              % (s["cheapest"]["vendor_name"], s["cheapest"]["instance_type"], s["cheapest"]["price"],
                 f["charge_type"], s["most_expensive"]["vendor_name"], s["most_expensive"]["instance_type"],
                 s["most_expensive"]["price"], s.get("max_gap_pct") or 0))
    print("口径：%s" % res["price_scope"])
    print("声明：%s" % res["disclaimer"])


def _print_equiv(res) -> None:
    if not res["matches"]:
        print("未找到 %r 对应的同类产品映射。" % res["keyword"])
        return
    for m in res["matches"]:
        print("== %s（%s）" % (m["label"], m["equivalent"]))
        for vendor, items in m["vendors"].items():
            for it in items:
                print("   %-8s %-28s %s" % (it["vendor_name"], it["name"], it["doc_url"]))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="多云产品信息一站式检索 CLI")
    parser.add_argument("--json", action="store_true", help="输出 JSON（可放在子命令前或后）")

    # 公共参数父解析器：让 `cli.py equiv DCS --json` 与 `cli.py --json equiv DCS` 均可用。
    # default=SUPPRESS 避免子解析器用默认值覆盖顶层已解析的 --json。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="输出 JSON")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_docs = sub.add_parser("docs", help="产品文档聚合搜索", parents=[common])
    p_docs.add_argument("query", nargs="?", default="")
    p_docs.add_argument("--vendors", help="tencent,aliyun,huawei,volcengine（支持中文『腾讯云』等）")
    p_docs.add_argument("--category", help="compute/storage/network/database/...")
    p_docs.add_argument("--limit", type=int, default=20)

    p_price = sub.add_parser("price", help="ECS/CVM 价格对比", parents=[common])
    p_price.add_argument("--region", default="cn-beijing")
    p_price.add_argument("--vcpu", type=int)
    p_price.add_argument("--memory", type=int, dest="memory_gb")
    p_price.add_argument("--spec", dest="spec_id", help="2c4g/4c8g/8c16g/4c16g/8c32g")
    p_price.add_argument("--vendors")
    p_price.add_argument("--series", choices=["general", "memory"])
    p_price.add_argument("--charge-type", dest="charge_type", default="monthly",
                         choices=["monthly", "on_demand_hour"])
    p_price.add_argument("--sort", default="asc", choices=["asc", "desc"])

    p_equiv = sub.add_parser("equiv", help="跨云同类产品对照", parents=[common])
    p_equiv.add_argument("keyword")

    p_products = sub.add_parser("products", help="列出已收录产品", parents=[common])
    p_products.add_argument("--vendor")
    p_products.add_argument("--category")

    sub.add_parser("regions", help="列出支持的地域及厂商地域映射", parents=[common])
    sub.add_parser("meta", help="输出平台元数据", parents=[common])

    args = parser.parse_args()
    as_json = getattr(args, "json", False)

    if args.cmd == "docs":
        res = engine.search_docs(args.query, vendors=args.vendors, category=args.category, limit=args.limit)
        _dump(res) if as_json else _print_docs(res)
    elif args.cmd == "price":
        res = engine.compare_ecs_price(region=args.region, vcpu=args.vcpu, memory_gb=args.memory_gb,
                                       spec_id=args.spec_id, vendors=args.vendors, series=args.series,
                                       charge_type=args.charge_type, sort=args.sort)
        _dump(res) if as_json else _print_price(res)
    elif args.cmd == "equiv":
        res = engine.find_equivalents(args.keyword)
        _dump(res) if as_json else _print_equiv(res)
    elif args.cmd == "products":
        res = engine.list_products(vendor=args.vendor, category=args.category)
        if as_json:
            _dump(res)
        else:
            print("共 %d 个产品：%s" % (res["total"], res["count_by_vendor"]))
            for p in res["products"]:
                print("  %-8s %-34s %-12s %s" % (p["vendor_name"], p["name"], p["category_name"], p["doc_url"]))
    elif args.cmd == "regions":
        res = engine.list_regions()
        if as_json:
            _dump(res)
        else:
            for r in res["regions"]:
                mapping = " ｜ ".join("%s=%s(%s)" % (v, m["name"], m["id"]) for v, m in r["vendor_regions"].items())
                print("%-12s %-14s %s" % (r["id"], r["name"], mapping))
    elif args.cmd == "meta":
        _dump(engine.meta())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
