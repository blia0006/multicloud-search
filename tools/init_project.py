#!/usr/bin/env python3
"""移交后一键初始化：换电脑 / 换目录 / 拿到压缩包后，第一件事跑这个。

它会做四件事：
    1. 检查 Python 版本（>= 3.8）与数据文件完整性
    2. 用**当前实际路径**重写 config/mcp.example.json（MCP 协议要求绝对路径）
    3. 构建零后端单文件版本 dist/index.html
    4. 打印可直接粘贴的 MCP 配置，以及人工/Agent 两种使用方式的下一步命令

用法：
    python3 tools/init_project.py
    python3 tools/init_project.py --python /usr/local/bin/python3   # 指定 MCP 用哪个解释器
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 入库的是占位符模板；本机真实路径写入 mcp.local.json（已在 .gitignore 中忽略，避免泄露本地路径）
TEMPLATE_PATH = os.path.join(ROOT, "config", "mcp.example.json")
CONFIG_PATH = os.path.join(ROOT, "config", "mcp.local.json")


def step(n: int, title: str) -> None:
    print("\n[%d/4] %s" % (n, title))


def check_env() -> bool:
    step(1, "环境与数据检查")
    ok = True
    print("  Python 版本：%s" % sys.version.split()[0])
    if sys.version_info < (3, 8):
        print("  [ERROR] 需要 Python 3.8 及以上")
        ok = False
    else:
        print("  PASS  Python 版本满足要求（>= 3.8）")

    for rel in ("data/products.json", "data/ecs_prices.json", "web/index.html",
                "server/app.py", "cli.py", "mcp/multicloud_mcp_server.py"):
        path = os.path.join(ROOT, rel)
        if os.path.isfile(path):
            print("  PASS  %s" % rel)
        else:
            print("  [ERROR] 缺少文件：%s" % rel)
            ok = False

    proc = subprocess.run(  # noqa: S603
        [sys.executable, os.path.join(ROOT, "tools", "check_data.py")],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode == 0 and "结构校验通过" in out:
        for line in out.splitlines():
            if "产品数" in line or "各厂商收录数量" in line:
                print("  PASS  数据校验通过（%s）" % line.strip())
                break
        else:
            print("  PASS  数据校验通过")
    else:
        print("  [ERROR] 数据校验失败，详见 python3 tools/check_data.py")
        ok = False
    return ok


def rewrite_mcp_config(python_bin: str) -> dict:
    step(2, "生成本机 MCP 配置")
    server_path = os.path.join(ROOT, "mcp", "multicloud_mcp_server.py")
    data_dir = os.path.join(ROOT, "data")
    config = {
        "_comment": (
            "本文件由 tools/init_project.py 按当前项目路径自动生成，已被 .gitignore 忽略（不会入库）。"
            "把 mcpServers 内容复制到 MCP 客户端配置中（Codebuddy：IDE 设置 → MCP）。"
            "迁移目录后重新运行 python3 tools/init_project.py 即可刷新。"
        ),
        "mcpServers": {
            "multicloud-search": {
                "command": python_bin,
                "args": [server_path],
                "env": {"MCS_DATA_DIR": data_dir},
            }
        },
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fp:
        json.dump(config, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    print("  模板（入库，占位符）：%s" % os.path.relpath(TEMPLATE_PATH, ROOT))
    print("  本机配置（不入库）：%s" % os.path.relpath(CONFIG_PATH, ROOT))
    print("  解释器：%s" % python_bin)
    print("  服务端：%s" % server_path)
    return config


def build_static() -> None:
    step(3, "构建零后端单文件版本")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, os.path.join(ROOT, "tools", "build_static.py")],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print("  " + proc.stdout.decode("utf-8", "replace").strip().replace("\n", "\n  "))


def print_next_steps(config: dict) -> None:
    step(4, "下一步怎么用")
    dist = os.path.join(ROOT, "dist", "index.html")
    print("""
  提示：以下命令请整行复制、不要连注释文字一起复制。
  macOS 默认 shell 是 zsh，交互模式下默认不识别 # 注释，
  连注释一起粘贴会报 "unrecognized arguments"。

  ── 人工查阅（二选一）─────────────────────────────────────────
  A) 零后端，双击即可打开：
     %s
  B) 完整功能（含 REST API），启动后端：
     cd %s
     python3 server/app.py
     然后浏览器访问 http://127.0.0.1:8787

  ── Agent 自动化调用（三条通道）──────────────────────────────
  1) MCP：把下面配置粘贴到 MCP 客户端（IDE 设置 → MCP）
%s
     协议自测：
     python3 tools/mcp_selftest.py

  2) Codebuddy Skill：用 Codebuddy 打开本项目目录即自动识别
     技能文件：.codebuddy/skills/multicloud-lookup/SKILL.md

  3) REST / CLI（脚本、定时任务、CI，无需模型）：
     python3 cli.py docs "对象存储"
     python3 cli.py price --vcpu 4 --memory 8
     python3 examples/weekly_price_report.py

  ── 一键验收（70 项检查，期望 0 失败）──────────────────────────
     python3 tools/verify_all.py

  ── 文档 ────────────────────────────────────────────────────
     README.md                项目总览
     docs/DEPLOYMENT.md       部署（环境依赖/启动/访问地址/内网发布）
     docs/AGENT_USAGE.md      Agent 自动化调用指南
     docs/MCP_USAGE.md        MCP 接口定义与调用示例
     docs/DATA_SOURCES.md     数据来源与刷新策略
     docs/ACCEPTANCE.md       验收清单（逐条对照课题要求）
""" % (
        dist,
        ROOT,
        "\n".join("     " + line for line in json.dumps(
            {"mcpServers": config["mcpServers"]}, ensure_ascii=False, indent=2).splitlines()),
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description="移交后一键初始化")
    parser.add_argument("--python", default="python3",
                        help="MCP 客户端启动服务端所用的解释器，默认 python3；若不在 PATH 请填绝对路径")
    args = parser.parse_args()

    print("=" * 74)
    print("多云产品信息一站式检索平台 —— 初始化")
    print("项目路径：%s" % ROOT)
    print("=" * 74)

    ok = check_env()
    config = rewrite_mcp_config(args.python)
    build_static()
    print_next_steps(config)

    print("=" * 74)
    if ok:
        print("初始化完成 ✓  建议接着执行：python3 tools/verify_all.py")
    else:
        print("初始化存在问题，请先修复上面标记 [ERROR] 的项")
    print("=" * 74)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
