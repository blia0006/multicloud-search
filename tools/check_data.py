#!/usr/bin/env python3
"""数据自检与链接巡检脚本（数据刷新流程的第一道闸门）。

功能：
    1. 校验 products.json / ecs_prices.json 结构完整性与引用一致性；
    2. 输出四家厂商的产品覆盖矩阵，指出「某类目某家缺失」的补全清单；
    3. 校验价格数据的地域/规格覆盖；
    4. 可选：巡检文档链接可达性（--check-links），只请求四家官方域名白名单。

用法：
    python3 tools/check_data.py
    python3 tools/check_data.py --check-links --vendor tencent
    python3 tools/check_data.py --check-links --timeout 8 --report reports/link_check.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine  # noqa: E402

# 只允许巡检四家官方域名，避免脚本被数据文件里的任意 URL 引导去请求内网地址（SSRF 防护）
ALLOWED_HOSTS = {
    "cloud.tencent.com", "buy.cloud.tencent.com",
    "help.aliyun.com", "www.aliyun.com",
    "support.huaweicloud.com", "www.huaweicloud.com",
    "www.volcengine.com",
}
UA = "Mozilla/5.0 (compatible; MultiCloudSearch-DataCheck/1.0)"
VENDORS = ["tencent", "aliyun", "huawei", "volcengine"]


def validate(data) -> int:
    errors, warnings = [], []
    products = data["products"]
    equivalents = data["equivalents"]
    cats = set(data["category_map"].keys())
    seen_ids = set()

    for p in products:
        pid = p.get("id")
        if not pid or pid in seen_ids:
            errors.append("产品 id 缺失或重复：%r" % pid)
        seen_ids.add(pid)
        for field in ("vendor", "name", "cat", "equiv", "summary", "doc_url"):
            if not p.get(field):
                errors.append("%s 缺少字段 %s" % (pid, field))
        if p.get("vendor") not in VENDORS:
            errors.append("%s 厂商非法：%s" % (pid, p.get("vendor")))
        if p.get("cat") not in cats:
            errors.append("%s 类目未定义：%s" % (pid, p.get("cat")))
        if p.get("equiv") and p["equiv"] not in equivalents:
            errors.append("%s 同类 key 未定义：%s" % (pid, p["equiv"]))
        url = p.get("doc_url", "")
        if not url.startswith("https://"):
            errors.append("%s 文档链接必须为 https：%s" % (pid, url))
        elif urlparse(url).hostname not in ALLOWED_HOSTS:
            warnings.append("%s 文档域名不在白名单：%s" % (pid, urlparse(url).hostname))

    # 价格数据校验
    prices = data["prices_doc"]
    region_ids = {r["id"] for r in prices.get("regions", [])}
    spec_ids = {s["id"] for s in prices.get("specs", [])}
    for item in prices.get("items", []):
        tag = "%s/%s" % (item.get("vendor"), item.get("instance_type"))
        if item.get("vendor") not in VENDORS:
            errors.append("价格记录厂商非法：%s" % tag)
        if item.get("spec_id") not in spec_ids:
            errors.append("价格记录规格未定义：%s -> %s" % (tag, item.get("spec_id")))
        missing = region_ids - set((item.get("prices") or {}).keys())
        if missing:
            warnings.append("%s 缺少地域价格：%s" % (tag, ", ".join(sorted(missing))))
        for region, price in (item.get("prices") or {}).items():
            if region not in region_ids:
                errors.append("%s 出现未定义地域：%s" % (tag, region))
            for key in ("on_demand_hour", "monthly"):
                if not isinstance(price.get(key), (int, float)) or price[key] <= 0:
                    errors.append("%s@%s 的 %s 非法：%r" % (tag, region, key, price.get(key)))
        if not item.get("source_url", "").startswith("https://"):
            errors.append("%s 缺少合法 source_url" % tag)

    print("== 结构校验")
    print("产品数：%d ｜ 价格记录：%d ｜ 地域：%d ｜ 规格：%d"
          % (len(products), len(prices.get("items", [])), len(region_ids), len(spec_ids)))
    for w in warnings:
        print("  [warn] %s" % w)
    for e in errors:
        print("  [ERROR] %s" % e)
    if not errors:
        print("  结构校验通过 ✓")
    return len(errors)


def coverage(data) -> None:
    print("\n== 覆盖矩阵（同类产品 × 厂商）")
    products = data["products"]
    equivalents = data["equivalents"]
    header = "%-26s %-8s %-8s %-8s %-8s" % ("同类产品", "腾讯云", "阿里云", "华为云", "火山引擎")
    print(header)
    print("-" * len(header))
    gaps = []
    for key, conf in equivalents.items():
        row = {v: 0 for v in VENDORS}
        for p in products:
            if p.get("equiv") == key:
                row[p["vendor"]] += 1
        cells = " ".join("%-8s" % ("✓" if row[v] else "—") for v in VENDORS)
        print("%-26s %s" % (conf.get("label", key)[:24], cells))
        for v in VENDORS:
            if not row[v]:
                gaps.append((conf.get("label", key), v))

    print("\n== 各厂商收录数量")
    counts = {}
    for p in products:
        counts[p["vendor"]] = counts.get(p["vendor"], 0) + 1
    for v in VENDORS:
        print("  %-12s %d 个" % (data["vendors"].get(v, {}).get("name", v), counts.get(v, 0)))

    if gaps:
        print("\n== 待补全清单（%d 项）" % len(gaps))
        for label, v in gaps:
            print("  - %s：缺 %s" % (label, data["vendors"].get(v, {}).get("name", v)))
    else:
        print("\n四家同类产品覆盖完整 ✓")


def check_links(data, vendor_filter, timeout, report_path):
    print("\n== 链接巡检（仅请求官方域名白名单）")
    rows = []
    targets = [p for p in data["products"] if not vendor_filter or p["vendor"] == vendor_filter]
    for i, p in enumerate(targets, 1):
        url = p.get("doc_url", "")
        host = urlparse(url).hostname
        if host not in ALLOWED_HOSTS:
            rows.append((p["id"], p["vendor"], p["name"], url, "skipped", "域名不在白名单"))
            continue
        status, note = "", ""
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (白名单域名)
                status = str(resp.status)
        except urllib.error.HTTPError as exc:
            status = str(exc.code)
            note = "HTTPError"
        except Exception as exc:  # noqa: BLE001
            status = "ERR"
            note = type(exc).__name__
        flag = "ok" if status.startswith("2") or status.startswith("3") else "CHECK"
        rows.append((p["id"], p["vendor"], p["name"], url, status, note or flag))
        print("  [%3d/%3d] %-6s %-12s %s" % (i, len(targets), status, p["vendor"], p["name"]))

    bad = [r for r in rows if not str(r[4]).startswith(("2", "3")) and r[4] != "skipped"]
    print("\n巡检完成：%d 条，异常 %d 条" % (len(rows), len(bad)))
    for r in bad:
        print("  [CHECK] %s %s -> %s (%s)" % (r[1], r[2], r[3], r[4]))
    print("说明：阿里云/华为云/火山引擎文档站为 SPA，无效路径也可能返回 200，"
          "因此链接巡检对腾讯云最精确，其余厂商需人工抽查（页面卡片自带『站内搜索』兜底）。")

    if report_path:
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        with open(report_path, "w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["product_id", "vendor", "name", "doc_url", "http_status", "note"])
            writer.writerows(rows)
        print("报告已写入：%s" % report_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="多云数据自检与链接巡检")
    parser.add_argument("--check-links", action="store_true")
    parser.add_argument("--vendor", choices=VENDORS)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--report", help="链接巡检 CSV 输出路径")
    parser.add_argument("--json", action="store_true", help="仅输出统计 JSON")
    args = parser.parse_args()

    data = engine.get_dataset(force=True)
    if args.json:
        print(json.dumps(engine.meta(), ensure_ascii=False, indent=2))
        return 0

    errors = validate(data)
    coverage(data)
    if args.check_links:
        check_links(data, args.vendor, args.timeout, args.report)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
