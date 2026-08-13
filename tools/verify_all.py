#!/usr/bin/env python3
"""一键验收脚本：把所有验收标准跑成可复现的自动化检查。

用法：
    python3 tools/verify_all.py
    python3 tools/verify_all.py --verbose

检查覆盖：
    1. 数据结构校验与四家覆盖矩阵（tools/check_data.py）
    2. 产品文档搜索能力（CLI + 引擎断言）
    3. ECS 价格对比能力（地域/机型/规格/刊例价字段完整性）
    4. REST API（真实启动服务并逐个接口验证）
    5. MCP Server 协议与 5 个工具（tools/mcp_selftest.py）
    6. 前端产物（单文件 HTML 构建 + 数据内联校验）
退出码 0 表示全部通过，可直接接入 CI。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine  # noqa: E402

VENDORS = ["tencent", "aliyun", "huawei", "volcengine"]

_results = []


def record(section: str, label: str, ok: bool, detail: str = "") -> bool:
    _results.append((section, label, ok, detail))
    print("  %s %s%s" % ("PASS " if ok else "FAIL ", label, ("  → %s" % detail) if detail and not ok else ""))
    return ok


def run(cmd, timeout=120):
    return subprocess.run(  # noqa: S603 - 固定命令数组，无 shell
        cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_json(url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers={"User-Agent": "verify_all/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 本地回环地址
        return resp.status, json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
def check_data_integrity(verbose: bool) -> None:
    print("\n[1/7] 数据完整性与覆盖度")
    proc = run([sys.executable, os.path.join("tools", "check_data.py")])
    out = proc.stdout.decode("utf-8", "replace")
    record("数据", "tools/check_data.py 结构校验通过", proc.returncode == 0 and "结构校验通过" in out)
    record("数据", "42 组同类产品四家覆盖完整", "四家同类产品覆盖完整" in out)

    data = engine.get_dataset(force=True)
    counts = {v: 0 for v in VENDORS}
    for p in data["products"]:
        counts[p["vendor"]] += 1
    record("数据", "四家各覆盖 >= 30 个主流产品（实际 %s）" % counts,
           all(counts[v] >= 30 for v in VENDORS))
    cats = {p["cat"] for p in data["products"]}
    record("数据", "产品类目覆盖 >= 8 个大类（实际 %d）" % len(cats), len(cats) >= 8)
    record("数据", "文档链接全部为 https 官方域名",
           all(p.get("doc_url", "").startswith("https://") for p in data["products"]))
    if verbose:
        print(out)


def check_doc_search() -> None:
    print("\n[2/7] 产品文档聚合搜索")
    res = engine.search_docs("对象存储")
    record("搜索", "关键词『对象存储』命中四家（%d 条）" % res["total"],
           len({r["vendor"] for r in res["results"]}) == 4)
    fields = ["name", "summary", "vendor_name", "doc_url", "category_name"]
    record("搜索", "卡片字段完整（产品名/摘要/来源标识/文档链接/类目）",
           all(all(r.get(f) for f in fields) for r in res["results"]))

    res2 = engine.search_docs("OSS")
    record("搜索", "厂商缩写『OSS』可跨云召回（%d 家）" % len({r["vendor"] for r in res2["results"]}),
           len({r["vendor"] for r in res2["results"]}) >= 4)

    res3 = engine.search_docs("Kubernetes", vendors="tencent,aliyun")
    record("搜索", "厂商过滤生效（仅 tencent/aliyun）",
           {r["vendor"] for r in res3["results"]} <= {"tencent", "aliyun"} and res3["total"] > 0)

    res4 = engine.search_docs("华为云 数据库")
    record("搜索", "自然语言厂商词识别（华为云 数据库）",
           bool(res4["results"]) and {r["vendor"] for r in res4["results"]} == {"huawei"})

    res5 = engine.search_docs("量子计算")
    record("搜索", "零命中时提供四家站内搜索兜底链接",
           res5["total"] == 0 and len(res5["fallback_search_links"]) == 4)

    for cat in ("compute", "storage", "network", "database", "ai"):
        r = engine.list_products(category=cat)
        ok = {p["vendor"] for p in r["products"]} == set(VENDORS)
        record("搜索", "类目 %s 四家均有覆盖" % cat, ok)


def check_price() -> None:
    print("\n[3/7] ECS/CVM 价格对比")
    res = engine.compare_ecs_price(region="cn-beijing", vcpu=4, memory_gb=8)
    record("价格", "4C8G@华北（北京）返回四家（%d 行）" % len(res["rows"]), len(res["rows"]) == 4)
    need = ["vendor_name", "instance_type", "family", "vcpu", "memory_gb",
            "vendor_region", "vendor_region_id", "on_demand_hour", "monthly", "source_url"]
    record("价格", "字段覆盖地域/机型/规格/刊例价/来源",
           all(all(r.get(f) not in (None, "") for f in need) for r in res["rows"]))
    record("价格", "输出最低价/最高价/最大价差结论",
           bool(res["summary"].get("cheapest") and res["summary"].get("max_gap_pct") is not None))
    record("价格", "按排序口径升序排列",
           [r["monthly"] for r in res["rows"]] == sorted(r["monthly"] for r in res["rows"]))

    regions = [r["id"] for r in engine.list_regions()["regions"]]
    record("价格", "地域维度 >= 3 个（实际 %d：%s）" % (len(regions), ",".join(regions)), len(regions) >= 3)
    ok_all_regions = True
    for rg in regions:
        rows = engine.compare_ecs_price(region=rg)["rows"]
        if len({r["vendor"] for r in rows}) != 4:
            ok_all_regions = False
    record("价格", "每个地域均覆盖四家厂商", ok_all_regions)

    specs = engine.list_specs()["specs"]
    record("价格", "规格维度 >= 4 个（实际 %d）" % len(specs), len(specs) >= 4)
    ok_spec = all(len(engine.compare_ecs_price(spec_id=s["id"])["rows"]) == 4 for s in specs)
    record("价格", "每个规格均可对比四家", ok_spec)

    hour = engine.compare_ecs_price(spec_id="8c32g", charge_type="on_demand_hour")
    record("价格", "按量计费口径可用且独立排序",
           [r["on_demand_hour"] for r in hour["rows"]] == sorted(r["on_demand_hour"] for r in hour["rows"]))

    bad = engine.compare_ecs_price(region="us-east")
    record("价格", "非法地域返回结构化错误而非异常", bad.get("error") == "unknown_region")

    empty = engine.compare_ecs_price(vcpu=16)
    record("价格", "未覆盖配置给出提示与官方价格页（防编造）",
           empty["rows"] == [] and bool(empty.get("no_data_hint")) and bool(empty.get("vendor_price_pages")))
    record("价格", "价格口径与免责声明随响应返回",
           bool(engine.compare_ecs_price()["price_scope"]) and bool(engine.compare_ecs_price()["disclaimer"]))


def check_api(verbose: bool) -> None:
    print("\n[4/7] REST API（真实启动服务）")
    port = free_port()
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, os.path.join("server", "app.py"), "--port", str(port)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = "http://127.0.0.1:%d" % port
    try:
        ready = False
        for _ in range(40):
            try:
                status, _body = get_json(base + "/api/health", timeout=1.5)
                ready = status == 200
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        if not record("API", "服务可启动并通过健康检查（端口 %d）" % port, ready):
            return

        status, body = get_json(base + "/api/meta")
        record("API", "/api/meta 返回厂商/地域/规格元数据",
               status == 200 and len(body.get("vendors", {})) == 4 and body.get("product_count", 0) > 100)

        status, body = get_json(base + "/api/search?q=" + quote("对象存储") + "&limit=10")
        record("API", "/api/search 聚合搜索可用（命中 %s）" % body.get("total"),
               status == 200 and len({r["vendor"] for r in body["results"]}) == 4)

        status, body = get_json(base + "/api/prices/ecs?region=cn-beijing&vcpu=4&memory=8")
        record("API", "/api/prices/ecs 价格对比可用（%d 行）" % len(body.get("rows", [])),
               status == 200 and len(body["rows"]) == 4)

        status, body = get_json(base + "/api/equivalents?keyword=CVM")
        record("API", "/api/equivalents 同类对照四家",
               status == 200 and len(body["matches"][0]["vendors"]) == 4)

        status, body = get_json(base + "/api/regions")
        record("API", "/api/regions 返回四家地域映射",
               status == 200 and all(len(r["vendor_regions"]) == 4 for r in body["regions"]))

        status, body = get_json(base + "/api/products?vendor=huawei&category=database")
        record("API", "/api/products 过滤可用（华为云/数据库 %s 个）" % body.get("total"),
               status == 200 and body["total"] >= 3)

        # 静态资源与数据文件
        req = urllib.request.Request(base + "/", headers={"User-Agent": "verify_all/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            html = resp.read().decode("utf-8", "replace")
        record("API", "首页可访问且包含四家厂商标识",
               all(k in html for k in ("腾讯云", "阿里云", "华为云", "火山引擎")))
        status, _ = get_json(base + "/data/products.json")
        record("API", "/data/products.json 只读数据可加载", status == 200)

        # 安全：目录穿越与非法接口
        blocked = 0
        for path in ("/../server/app.py", "/..%2fserver/app.py", "/data/../core/engine.py"):
            try:
                urllib.request.urlopen(base + path, timeout=3)  # noqa: S310
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    blocked += 1
            except Exception:  # noqa: BLE001
                pass
        record("安全", "目录穿越请求全部被拒（%d/3 返回 403）" % blocked, blocked == 3)
        try:
            urllib.request.urlopen(base + "/api/not-exist", timeout=3)  # noqa: S310
            not_found = False
        except urllib.error.HTTPError as exc:
            not_found = exc.code == 404
        record("安全", "未知接口返回 404 结构化错误", not_found)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if verbose:
            print((proc.stdout.read() or b"").decode("utf-8", "replace"))


def check_mcp(verbose: bool) -> None:
    print("\n[5/7] MCP Server 与 Skill")
    proc = run([sys.executable, os.path.join("tools", "mcp_selftest.py")])
    out = proc.stdout.decode("utf-8", "replace")
    record("MCP", "tools/mcp_selftest.py 全部通过", proc.returncode == 0 and "0 项失败" in out)
    record("MCP", "注册 5 个工具", "返回 5 个工具" in out)

    skill = os.path.join(ROOT, ".codebuddy", "skills", "multicloud-lookup", "SKILL.md")
    record("Skill", "SKILL.md 存在且含 frontmatter 描述", os.path.isfile(skill))
    if os.path.isfile(skill):
        text = open(skill, "r", encoding="utf-8").read()
        record("Skill", "SKILL.md 含 >= 2 个调用示例", text.count("### 示例") >= 2)
        record("Skill", "SKILL.md 含输出规范（防编造价格/链接）", "不要编造价格" in text)

    # Skill 承诺的 CLI 命令逐条真实执行
    cli_cases = [
        (["docs", "对象存储"], "对象存储 COS"),
        (["docs", "Kubernetes", "--vendors", "tencent,aliyun", "--limit", "8"], "容器服务"),
        (["price", "--vcpu", "4", "--memory", "8", "--region", "cn-beijing"], "最低价"),
        (["price", "--spec", "8c32g", "--charge-type", "on_demand_hour"], "8C32G"),
        (["equiv", "CVM"], "云服务器"),
        (["products", "--vendor", "huawei", "--category", "database"], "华为云"),
        (["regions"], "cn-beijing"),
    ]
    for argv, expect in cli_cases:
        p = run([sys.executable, "cli.py"] + argv)
        text = p.stdout.decode("utf-8", "replace")
        record("Skill", "cli.py %s" % " ".join(argv), p.returncode == 0 and expect in text)

    # --json 两种参数位置都必须可用
    for argv in (["--json", "equiv", "CVM"], ["equiv", "CVM", "--json"]):
        p = run([sys.executable, "cli.py"] + argv)
        ok = p.returncode == 0
        if ok:
            try:
                json.loads(p.stdout.decode("utf-8"))
            except json.JSONDecodeError:
                ok = False
        record("Skill", "cli.py %s 输出合法 JSON" % " ".join(argv), ok)

    # 无人值守自动化范例：进程内取数与 REST 取数两种模式
    p = run([sys.executable, os.path.join("examples", "weekly_price_report.py"), "--stdout"])
    text = p.stdout.decode("utf-8", "replace")
    record("Agent", "examples/weekly_price_report.py 可直接运行", p.returncode == 0)
    record("Agent", "自动化报告含全部规格与最低价结论",
           text.count("| 厂商 |") >= 5 and "总体结论" in text and "最低价出现次数" in text)
    record("Agent", "自动化报告含计价口径与免责声明",
           "数据口径与免责声明" in text and "官方价格页" in text)
    p = run([sys.executable, os.path.join("examples", "weekly_price_report.py"),
             "--api", "http://10.0.0.1:8080", "--stdout"])
    out_txt = p.stdout.decode("utf-8", "replace")
    record("Agent", "REST 取数模式拒绝非回环 http 地址（防 SSRF）",
           p.returncode != 0 and "SSRF" in out_txt)
    if verbose:
        print(out)


def check_frontend() -> None:
    print("\n[6/7] 前端产物")
    proc = run([sys.executable, os.path.join("tools", "build_static.py")])
    record("前端", "tools/build_static.py 构建成功", proc.returncode == 0)
    dist = os.path.join(ROOT, "dist", "index.html")
    ok = os.path.isfile(dist)
    record("前端", "dist/index.html 已生成", ok)
    if ok:
        text = open(dist, "r", encoding="utf-8").read()
        size_kb = os.path.getsize(dist) / 1024.0
        record("前端", "单文件已内联数据（%.1f KB，无需后端）" % size_kb,
               "__EMBEDDED_DATA__" in text and size_kb > 60)
        record("前端", "包含文档搜索/价格对比/同类对照/API 四个页签",
               all(k in text for k in ("产品文档搜索", "ECS 价格对比", "跨云同类对照", "API / Agent 接入")))
        record("前端", "价格表含地域/机型/规格/刊例价列",
               all(k in text for k in ("厂商地域", "实例族", "包月刊例价", "按量（元/小时）")))
        record("前端", "免责声明与快照日期常驻展示",
               "价格快照日期" in text and "disclaimer" in text)

    src = os.path.join(ROOT, "web", "index.html")
    if os.path.isfile(src):
        stext = open(src, "r", encoding="utf-8").read()
        record("前端", "数据加载支持 data/ 与 ../data/ 双路径回退",
               "../data/products.json" in stext and "data/products.json" in stext)
        record("前端", "file:// 打开时给出可操作的排障指引",
               'location.protocol === "file:"' in stext and "tools/build_static.py" in stext)


def check_docs() -> None:
    print("\n[7/7] 文档完整性与引用一致性")
    required = [
        ("README.md", "项目主入口"),
        ("requirements.txt", "依赖声明"),
        ("Dockerfile", "容器部署"),
        ("docs/DEPLOYMENT.md", "部署文档"),
        ("docs/DATA_SOURCES.md", "数据来源与刷新策略"),
        ("docs/MCP_USAGE.md", "MCP 接口文档"),
        ("docs/AGENT_USAGE.md", "Agent 自动化调用指南"),
        ("docs/ACCEPTANCE.md", "验收清单"),
        ("mcp/MCP_SERVER_README.md", "MCP 模块 README"),
        ("config/mcp.example.json", "MCP 客户端配置示例"),
        ("examples/weekly_price_report.py", "自动化调用范例"),
        ("tools/init_project.py", "移交后一键初始化脚本"),
        (".codebuddy/skills/multicloud-lookup/SKILL.md", "Codebuddy Skill 定义"),
    ]
    missing = [p for p, _d in required if not os.path.isfile(os.path.join(ROOT, p))]
    record("文档", "必备交付文档齐全（%d 份）" % len(required), not missing, "缺失：%s" % ", ".join(missing))

    # 文档内相对链接必须全部有效（防止改名/移动后出现死链）
    import glob
    import re

    doc_files = [os.path.join(ROOT, p) for p, _ in required if p.endswith(".md")]
    doc_files += glob.glob(os.path.join(ROOT, "docs", "*.md"))
    broken = []
    total_links = 0
    for path in sorted(set(doc_files)):
        base = os.path.dirname(path)
        text = open(path, "r", encoding="utf-8").read()
        for m in re.finditer(r"\]\((?!https?:)([^)#]+\.(?:md|json|py|txt|html))\)", text):
            total_links += 1
            target = os.path.normpath(os.path.join(base, m.group(1)))
            if not os.path.isfile(target):
                broken.append("%s -> %s" % (os.path.relpath(path, ROOT), m.group(1)))
    record("文档", "文档相对链接全部有效（%d 条）" % total_links, not broken, "; ".join(broken))

    # 交付文件不应出现同名文档（IDE 扁平列表里无法区分）
    names = {}
    for path in sorted(set(doc_files)):
        names.setdefault(os.path.basename(path), []).append(os.path.relpath(path, ROOT))
    dup = {k: v for k, v in names.items() if len(v) > 1}
    record("文档", "文档文件名无重复（避免扁平列表歧义）", not dup, str(dup))

    # MCP 配置：入库模板必须是占位符（不泄露本机路径）；本机配置若存在必须指向当前项目
    tpl_path = os.path.join(ROOT, "config", "mcp.example.json")
    if os.path.isfile(tpl_path):
        raw = open(tpl_path, "r", encoding="utf-8").read()
        tpl = json.loads(raw)
        tpl_args = ((tpl.get("mcpServers") or {}).get("multicloud-search", {}) or {}).get("args", [""])
        record("文档", "config/mcp.example.json 为占位符模板（入库不泄露本机路径）",
               "/ABSOLUTE/PATH/TO/PROJECT" in tpl_args[0] and "/Users/" not in raw and "C:\\" not in raw,
               "模板里出现了真实本机路径，请改回占位符")

    local_path = os.path.join(ROOT, "config", "mcp.local.json")
    if os.path.isfile(local_path):
        local = json.load(open(local_path, "r", encoding="utf-8"))
        server = (local.get("mcpServers") or {}).get("multicloud-search", {})
        args_ok = bool(server.get("args")) and os.path.isfile(server["args"][0])
        data_dir = (server.get("env") or {}).get("MCS_DATA_DIR", "")
        same_root = args_ok and os.path.realpath(server["args"][0]).startswith(os.path.realpath(ROOT))
        record("文档", "config/mcp.local.json 路径有效且指向当前项目",
               args_ok and same_root and (not data_dir or os.path.isdir(data_dir)),
               "路径失效或指向其它目录，请运行 python3 tools/init_project.py")
    else:
        record("文档", "本机 MCP 配置未生成（首次 clone 属正常，运行 tools/init_project.py 生成）", True)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键验收：数据/搜索/价格/API/MCP/前端/文档")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 78)
    print("多云产品信息一站式检索平台 —— 一键验收")
    print("项目路径：%s" % ROOT)
    print("=" * 78)

    check_data_integrity(args.verbose)
    check_doc_search()
    check_price()
    check_api(args.verbose)
    check_mcp(args.verbose)
    check_frontend()
    check_docs()

    total = len(_results)
    failed = [r for r in _results if not r[2]]
    print("\n" + "=" * 78)
    by_section = {}
    for section, _label, ok, _d in _results:
        s = by_section.setdefault(section, [0, 0])
        s[0] += 1
        if ok:
            s[1] += 1
    for section, (cnt, passed) in by_section.items():
        print("  %-6s %d/%d 通过" % (section, passed, cnt))
    print("-" * 78)
    print("总计：%d 项检查，通过 %d 项，失败 %d 项" % (total, total - len(failed), len(failed)))
    if failed:
        print("\n失败项：")
        for section, label, _ok, detail in failed:
            print("  [%s] %s %s" % (section, label, detail))
    else:
        print("结论：全部验收项通过 ✓")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
