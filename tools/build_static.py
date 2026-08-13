#!/usr/bin/env python3
"""构建「单文件 HTML」版本：把数据内联进页面，产出 dist/index.html。

产物可直接双击打开、或丢到任意静态托管（COS/OSS/OBS/TOS 静态网站、Nginx、woa 内网静态目录），
无需后端、无需跨域配置。

用法：
    python3 tools/build_static.py
    python3 tools/build_static.py --out /tmp/index.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine  # noqa: E402
from core.cliutil import strip_shell_comments  # noqa: E402


def _js_json(obj) -> str:
    """安全内联 JSON（避免 </script> 提前闭合、避免行分隔符问题）。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build(out_path: str) -> str:
    src = os.path.join(ROOT, "web", "index.html")
    with open(src, "r", encoding="utf-8") as fp:
        html = fp.read()

    with open(os.path.join(engine.DATA_DIR, "products.json"), "r", encoding="utf-8") as fp:
        products = json.load(fp)
    with open(os.path.join(engine.DATA_DIR, "ecs_prices.json"), "r", encoding="utf-8") as fp:
        prices = json.load(fp)

    payload = "<script>window.__EMBEDDED_DATA__={\"products\":%s,\"prices\":%s};</script>\n" % (
        _js_json(products),
        _js_json(prices),
    )
    stamp = "<!-- built at %s by tools/build_static.py -->\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "</head>" not in html:
        raise SystemExit("web/index.html 结构异常：缺少 </head>")
    html = html.replace("</head>", stamp + payload + "</head>", 1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(html)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成单文件 HTML 版本")
    parser.add_argument("--out", default=os.path.join(ROOT, "dist", "index.html"))
    args = parser.parse_args(strip_shell_comments())
    path = build(args.out)
    size = os.path.getsize(path) / 1024.0
    print("已生成单文件版本：%s（%.1f KB）" % (path, size))
    print("直接用浏览器打开即可使用，无需后端。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
