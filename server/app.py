#!/usr/bin/env python3
"""多云产品信息一站式检索平台 —— 后端 API + 静态站点服务（零第三方依赖）。

启动：
    python3 server/app.py                    # 默认 127.0.0.1:8787
    MCS_HOST=0.0.0.0 MCS_PORT=8080 python3 server/app.py
    python3 server/app.py --host 0.0.0.0 --port 8080

安全约束：
    - 静态文件只允许读取 web/ 目录下的白名单后缀文件，路径经 realpath 校验，防目录穿越；
    - 服务端不会代理任何用户提供的 URL（无 SSRF 面）；
    - 默认仅监听 127.0.0.1；对外暴露请通过 Nginx/反向代理并显式设置 MCS_HOST=0.0.0.0；
    - 跨域默认关闭，如需前后端分离部署，用 MCS_ALLOW_ORIGIN 指定确切来源（不支持 *）。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import posixpath
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import engine  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.realpath(os.path.join(ROOT, "web"))
ALLOWED_SUFFIX = {".html", ".css", ".js", ".svg", ".png", ".ico", ".webp", ".woff2"}
MAX_QUERY_LEN = 200
ALLOW_ORIGIN = os.environ.get("MCS_ALLOW_ORIGIN", "").strip()


def _first(params, key, default=None):
    values = params.get(key)
    if not values:
        return default
    value = values[0]
    if isinstance(value, str) and len(value) > MAX_QUERY_LEN:
        value = value[:MAX_QUERY_LEN]
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "MultiCloudSearch/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ #
    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ALLOW_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    # ------------------------------------------------------------------ #
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            params = parse_qs(parsed.query)
            if path.startswith("/api/"):
                return self._route_api(path, params)
            if path in ("/data/products.json", "/data/ecs_prices.json"):
                return self._serve_data(os.path.basename(path))
            return self._serve_static(path)
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            self.log_message("error: %s", exc)
            return self._json({"error": "internal_error", "message": str(exc)}, 500)

    do_HEAD = do_GET

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    # ------------------------------------------------------------------ #
    def _route_api(self, path: str, params):
        if path == "/api/health":
            return self._json({"status": "ok", "version": "1.0.0"})

        if path == "/api/meta":
            return self._json(engine.meta())

        if path == "/api/search":
            return self._json(
                engine.search_docs(
                    query=_first(params, "q", "") or "",
                    vendors=_first(params, "vendors"),
                    category=_first(params, "category"),
                    limit=_first(params, "limit", 30),
                )
            )

        if path == "/api/products":
            return self._json(
                engine.list_products(
                    vendor=_first(params, "vendor"),
                    category=_first(params, "category"),
                )
            )

        if path == "/api/equivalents":
            return self._json(engine.find_equivalents(_first(params, "keyword", "") or ""))

        if path == "/api/regions":
            return self._json(engine.list_regions())

        if path in ("/api/prices/ecs", "/api/price/ecs"):
            return self._json(
                engine.compare_ecs_price(
                    region=_first(params, "region", "cn-beijing") or "cn-beijing",
                    vcpu=_first(params, "vcpu"),
                    memory_gb=_first(params, "memory") or _first(params, "memory_gb"),
                    spec_id=_first(params, "spec"),
                    vendors=_first(params, "vendors"),
                    series=_first(params, "series"),
                    charge_type=_first(params, "charge_type", "monthly") or "monthly",
                    sort=_first(params, "sort", "asc") or "asc",
                )
            )

        return self._json({"error": "not_found", "message": "未知接口 %s" % path}, 404)

    # ------------------------------------------------------------------ #
    def _serve_data(self, filename: str):
        """仅开放两个固定数据文件供前端加载（白名单，无用户可控路径）。"""
        if filename not in ("products.json", "ecs_prices.json"):
            return self._json({"error": "forbidden"}, 403)
        target = os.path.join(os.path.realpath(engine.DATA_DIR), filename)
        if not os.path.isfile(target):
            return self._json({"error": "not_found", "message": "%s 不存在" % filename}, 404)
        with open(target, "rb") as fp:
            body = fp.read()
        return self._send(200, body, "application/json; charset=utf-8", "no-cache")

    # ------------------------------------------------------------------ #
    def _serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        # 规范化并阻断目录穿越
        clean = posixpath.normpath(path).lstrip("/")
        if clean.startswith("..") or "\x00" in clean:
            return self._json({"error": "forbidden"}, 403)
        target = os.path.realpath(os.path.join(WEB_DIR, clean))
        if not (target == WEB_DIR or target.startswith(WEB_DIR + os.sep)):
            return self._json({"error": "forbidden"}, 403)
        if os.path.splitext(target)[1].lower() not in ALLOWED_SUFFIX:
            return self._json({"error": "forbidden", "message": "不允许的文件类型"}, 403)
        if not os.path.isfile(target):
            return self._json({"error": "not_found", "message": "%s 不存在" % path}, 404)

        with open(target, "rb") as fp:
            body = fp.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        cache = "no-cache" if target.endswith(".html") else "public, max-age=300"
        return self._send(200, body, ctype, cache)


def main() -> int:
    parser = argparse.ArgumentParser(description="多云产品信息一站式检索平台后端服务")
    parser.add_argument("--host", default=os.environ.get("MCS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCS_PORT", "8787")))
    args = parser.parse_args()

    data = engine.get_dataset()  # 启动即校验数据可加载
    print(
        "数据加载完成：%d 个产品 / %d 条价格记录（产品快照 %s，价格快照 %s）"
        % (
            len(data["products"]),
            len(data["price_items"]),
            data["products_doc"].get("snapshot_date", "-"),
            data["prices_doc"].get("snapshot_date", "-"),
        )
    )
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("服务已启动： http://%s:%d" % (args.host, args.port))
    print("API 健康检查： http://%s:%d/api/health" % (args.host, args.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
