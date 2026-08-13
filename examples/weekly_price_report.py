#!/usr/bin/env python3
"""示例：无人值守的自动化调用 —— 生成《四家云 ECS 价格对比周报》。

这是"Agent 自动化调用"场景的最小可运行范例：不需要人打开网页，
由脚本 / 定时任务 / CI / Agent 直接调用平台能力并产出可交付的 Markdown。

两种取数方式（同一份数据与逻辑）：
    1) 进程内调用 core.engine（默认，零依赖、离线可用）
    2) 通过 REST API 调用远端部署的服务（--api http://host:port）

用法：
    python3 examples/weekly_price_report.py
    python3 examples/weekly_price_report.py --region cn-shanghai --charge-type on_demand_hour
    python3 examples/weekly_price_report.py --api http://127.0.0.1:8787
    python3 examples/weekly_price_report.py --out /tmp/report.md

定时化（任选其一）：
    crontab:  0 9 * * 1 cd /opt/multicloud-search && python3 examples/weekly_price_report.py
    CI:       在流水线中执行本脚本并把产物作为构建附件
    IDE 自动化任务：每周一 09:00 运行本脚本并把结果发到群里
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine  # noqa: E402

VENDOR_ORDER = ["tencent", "aliyun", "huawei", "volcengine"]


# --------------------------------------------------------------------------- #
# 取数：进程内 or REST
# --------------------------------------------------------------------------- #
def fetch_local(region: str, spec_id: str, charge_type: str):
    return engine.compare_ecs_price(region=region, spec_id=spec_id, charge_type=charge_type)


def fetch_api(base: str, region: str, spec_id: str, charge_type: str):
    if not base.startswith(("http://127.0.0.1", "http://localhost", "https://")):
        raise SystemExit("为避免 SSRF 风险，--api 仅接受 https 地址或本机回环地址：%s" % base)
    query = urllib.parse.urlencode({"region": region, "spec": spec_id, "charge_type": charge_type})
    url = "%s/api/prices/ecs?%s" % (base.rstrip("/"), query)
    req = urllib.request.Request(url, headers={"User-Agent": "weekly-price-report/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - 白名单校验后的固定地址
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
def build_report(fetch, region: str, charge_type: str) -> str:
    meta = engine.meta()
    region_name = next((r["name"] for r in meta["regions"] if r["id"] == region), region)
    unit = "元/月（包月刊例价）" if charge_type == "monthly" else "元/小时（按量单价）"
    specs = [s["id"] for s in meta["specs"]]

    lines = [
        "# 四家云 ECS/CVM 价格对比周报",
        "",
        "- 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "- 对比地域：**%s**（`%s`）" % (region_name, region),
        "- 计价口径：%s" % unit,
        "- 价格快照：%s" % meta["prices_snapshot_date"],
        "",
        "> 本报告由 `examples/weekly_price_report.py` 自动生成，未经人工修改。",
        "",
    ]

    win_count = {v: 0 for v in VENDOR_ORDER}
    all_rows = []

    for spec_id in specs:
        res = fetch(region, spec_id, charge_type)
        rows = res.get("rows", [])
        if not rows:
            lines += ["## %s" % spec_id.upper(), "", res.get("no_data_hint", "无数据"), ""]
            continue
        all_rows.extend(rows)
        cheapest = res["summary"]["cheapest"]
        win_count[cheapest["vendor"]] = win_count.get(cheapest["vendor"], 0) + 1

        lines += [
            "## %dC%dG（%s）" % (rows[0]["vcpu"], rows[0]["memory_gb"], spec_id),
            "",
            "| 厂商 | 实例规格 | 实例族 | 厂商地域 | 按量(元/时) | 包月(元/月) | 较最低价 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in rows:
            diff = "**最低**" if r.get("is_cheapest") else (
                "+%.1f%%" % r["diff_vs_cheapest_pct"] if r.get("diff_vs_cheapest_pct") is not None else "-"
            )
            lines.append("| %s | `%s` | %s | %s | %s | %s | %s |" % (
                r["vendor_name"], r["instance_type"], r["family"], r["vendor_region"],
                r["on_demand_hour"], r["monthly"], diff))
        lines += ["", "小结：最低 **%s %s = %s**，最大价差 %.1f%%。" % (
            cheapest["vendor_name"], cheapest["instance_type"], cheapest["price"],
            res["summary"].get("max_gap_pct") or 0), ""]

    lines += ["## 总体结论", ""]
    total = sum(win_count.values())
    if total:
        ranking = sorted(win_count.items(), key=lambda kv: -kv[1])
        lines.append("- 最低价出现次数：" + "、".join(
            "%s %d/%d" % (engine.meta()["vendors"][v]["name"], c, total) for v, c in ranking if c))
    if all_rows:
        key = charge_type
        lines.append("- 覆盖规格 %d 个，价格记录 %d 条，价格区间 %.2f ~ %.2f %s" % (
            len(specs), len(all_rows),
            min(r[key] for r in all_rows), max(r[key] for r in all_rows),
            "元/月" if charge_type == "monthly" else "元/小时"))
    lines += [
        "",
        "## 数据口径与免责声明",
        "",
        "- %s" % engine.compare_ecs_price()["price_scope"],
        "- %s" % engine.compare_ecs_price()["disclaimer"],
        "",
        "官方价格页：" + "、".join("[%s](%s)" % (v, u) for v, u in meta["vendor_price_pages"].items()),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="自动生成四家云 ECS 价格对比周报")
    parser.add_argument("--region", default="cn-beijing", help="统一地域 ID，默认 cn-beijing")
    parser.add_argument("--charge-type", dest="charge_type", default="monthly",
                        choices=["monthly", "on_demand_hour"])
    parser.add_argument("--api", help="通过 REST API 取数（默认进程内调用）")
    parser.add_argument("--out", help="输出路径，默认 reports/price_report_<日期>.md")
    parser.add_argument("--stdout", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    if args.api:
        fetch = lambda region, spec, ct: fetch_api(args.api, region, spec, ct)  # noqa: E731
    else:
        fetch = fetch_local

    report = build_report(fetch, args.region, args.charge_type)

    if args.stdout:
        print(report)
        return 0

    out = args.out or os.path.join(ROOT, "reports", "price_report_%s.md" % datetime.now().strftime("%Y%m%d"))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fp:
        fp.write(report)
    print("周报已生成：%s（%d 字符）" % (out, len(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
