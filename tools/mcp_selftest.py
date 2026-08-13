#!/usr/bin/env python3
"""MCP Server 自测脚本：不依赖任何 MCP 客户端即可验证协议与工具可用性。

用法：
    python3 tools/mcp_selftest.py
    python3 tools/mcp_selftest.py --verbose
退出码 0 表示全部用例通过。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.cliutil import strip_shell_comments  # noqa: E402

SERVER = os.path.join(ROOT, "mcp", "multicloud_mcp_server.py")

CASES = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "selftest", "version": "1.0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "search_cloud_docs", "arguments": {"query": "对象存储", "limit": 6}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "compare_ecs_price", "arguments": {"region": "cn-beijing", "vcpu": 4, "memory_gb": 8}}},
    {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
     "params": {"name": "find_equivalent_products", "arguments": {"keyword": "CVM"}}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
     "params": {"name": "list_cloud_regions", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
     "params": {"name": "list_cloud_products", "arguments": {"vendor": "volcengine", "category": "database", "format": "json"}}},
]


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP Server 自测")
    parser.add_argument("--verbose", action="store_true", help="打印工具返回的完整文本")
    args = parser.parse_args(strip_shell_comments())

    payload = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in CASES)
    proc = subprocess.run(  # noqa: S603 - 固定命令，无 shell
        [sys.executable, SERVER],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))

    responses = {}
    for line in proc.stdout.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        responses[msg.get("id")] = msg

    failed = 0
    total = 0

    def check(cond, label):
        nonlocal failed, total
        total += 1
        print(("  PASS  " if cond else "  FAIL  ") + label)
        if not cond:
            failed += 1

    print("== MCP 协议自测")
    init = responses.get(1, {}).get("result", {})
    check(init.get("protocolVersion") == "2024-11-05", "initialize 返回协议版本 2024-11-05")
    check(init.get("serverInfo", {}).get("name") == "multicloud-search", "serverInfo.name = multicloud-search")

    tools = responses.get(2, {}).get("result", {}).get("tools", [])
    names = [t["name"] for t in tools]
    check(len(tools) == 5, "tools/list 返回 5 个工具：%s" % ", ".join(names))
    for expect in ["search_cloud_docs", "compare_ecs_price", "find_equivalent_products",
                   "list_cloud_products", "list_cloud_regions"]:
        check(expect in names, "工具已注册：%s" % expect)
    check(all("inputSchema" in t and t["inputSchema"].get("type") == "object" for t in tools),
          "所有工具均声明了 JSON Schema 参数")

    print("\n== 工具调用自测")
    r3 = responses.get(3, {}).get("result", {})
    text3 = (r3.get("content") or [{}])[0].get("text", "")
    struct3 = r3.get("structuredContent", {})
    check(struct3.get("total", 0) >= 4, "search_cloud_docs('对象存储') 命中 >= 4 条（实际 %s）" % struct3.get("total"))
    check(len({r["vendor"] for r in struct3.get("results", [])}) == 4, "结果覆盖四家厂商")
    check("腾讯云" in text3 and "|" in text3, "返回 Markdown 表格且含厂商标识")

    r4 = responses.get(4, {}).get("result", {})
    struct4 = r4.get("structuredContent", {})
    check(len(struct4.get("rows", [])) == 4, "compare_ecs_price(4C8G@北京) 返回 4 行（实际 %s）" % len(struct4.get("rows", [])))
    check(struct4.get("summary", {}).get("cheapest") is not None, "价格结果包含最低价结论")
    check(all(r.get("monthly") and r.get("on_demand_hour") for r in struct4.get("rows", [])), "每行包含包月与按量刊例价")

    r5 = responses.get(5, {}).get("result", {})
    struct5 = r5.get("structuredContent", {})
    check(struct5.get("matches") and len(struct5["matches"][0]["vendors"]) == 4, "find_equivalent_products('CVM') 对照四家")

    r6 = responses.get(6, {}).get("result", {})
    check(len(r6.get("structuredContent", {}).get("regions", [])) >= 3, "list_cloud_regions 返回 >= 3 个地域")

    r7 = responses.get(7, {}).get("result", {})
    check(r7.get("structuredContent", {}).get("total", 0) >= 3, "list_cloud_products(火山引擎/数据库) 返回 >= 3 个产品")

    if args.verbose:
        print("\n== search_cloud_docs 返回内容\n" + text3)
        print("\n== compare_ecs_price 返回内容\n" + (r4.get("content") or [{}])[0].get("text", ""))

    print("\n结果：%d 项检查，%d 项失败" % (total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
