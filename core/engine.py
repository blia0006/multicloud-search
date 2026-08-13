"""多云产品信息一站式检索平台 —— 核心检索与价格对比引擎。

设计要点：
- 纯标准库实现，零第三方依赖，便于在任意环境（含内网）复现部署。
- 数据与逻辑解耦：数据在 data/*.json，引擎只做加载、匹配与聚合。
- 同一套引擎同时服务于 HTTP API、CLI、MCP Server 与 Codebuddy Skill。
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

__all__ = [
    "DATA_DIR",
    "get_dataset",
    "search_docs",
    "list_products",
    "find_equivalents",
    "compare_ecs_price",
    "list_regions",
    "list_specs",
    "meta",
]

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("MCS_DATA_DIR") or os.path.join(os.path.dirname(_HERE), "data")

_PRODUCTS_FILE = "products.json"
_PRICES_FILE = "ecs_prices.json"

_lock = threading.Lock()
_cache: Dict[str, Any] = {"stamp": None, "data": None}

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _stamp(paths: Iterable[str]) -> tuple:
    out = []
    for p in paths:
        try:
            out.append((p, os.path.getmtime(p)))
        except OSError:
            out.append((p, None))
    return tuple(out)


def get_dataset(force: bool = False) -> Dict[str, Any]:
    """加载并缓存数据集，文件修改后自动热更新。"""
    products_path = os.path.join(DATA_DIR, _PRODUCTS_FILE)
    prices_path = os.path.join(DATA_DIR, _PRICES_FILE)
    stamp = _stamp([products_path, prices_path])

    with _lock:
        if not force and _cache["data"] is not None and _cache["stamp"] == stamp:
            return _cache["data"]

        products_doc = _read_json(products_path)
        prices_doc = _read_json(prices_path)

        categories = {c["id"]: c["name"] for c in products_doc.get("categories", [])}
        vendors = products_doc.get("vendors", {})
        equivalents = products_doc.get("equivalents", {})

        # 反向索引：别名 -> equiv key
        equiv_alias_index: Dict[str, List[str]] = {}
        for key, item in equivalents.items():
            names = [key, item.get("label", "")] + list(item.get("aliases", []))
            for alias in names:
                alias = (alias or "").strip().lower()
                if alias:
                    equiv_alias_index.setdefault(alias, []).append(key)

        # 厂商名索引（用于「腾讯云 对象存储」这类查询）
        vendor_alias_index: Dict[str, str] = {}
        for vid, v in vendors.items():
            for alias in [vid, v.get("name", ""), v.get("short", "")]:
                alias = (alias or "").strip().lower()
                if alias:
                    vendor_alias_index[alias] = vid
        vendor_alias_index.update(
            {
                "腾讯": "tencent", "tc": "tencent", "txy": "tencent",
                "阿里": "aliyun", "ali": "aliyun", "aly": "aliyun",
                "华为": "huawei", "hw": "huawei", "hwc": "huawei",
                "火山": "volcengine", "字节": "volcengine", "volc": "volcengine", "ve": "volcengine",
            }
        )

        products = []
        for p in products_doc.get("products", []):
            item = dict(p)
            item["vendor_name"] = vendors.get(p["vendor"], {}).get("name", p["vendor"])
            item["category_name"] = categories.get(p.get("cat", ""), p.get("cat", ""))
            item["equiv_label"] = equivalents.get(p.get("equiv", ""), {}).get("label", "")
            haystack = " ".join(
                [
                    p.get("name", ""),
                    p.get("en", ""),
                    p.get("summary", ""),
                    " ".join(p.get("aliases", []) or []),
                    item["equiv_label"],
                    item["category_name"],
                    item["vendor_name"],
                ]
            ).lower()
            item["_hay"] = haystack
            products.append(item)

        data = {
            "products_doc": products_doc,
            "prices_doc": prices_doc,
            "vendors": vendors,
            "categories": products_doc.get("categories", []),
            "category_map": categories,
            "equivalents": equivalents,
            "equiv_alias_index": equiv_alias_index,
            "vendor_alias_index": vendor_alias_index,
            "products": products,
            "regions": prices_doc.get("regions", []),
            "specs": prices_doc.get("specs", []),
            "price_items": prices_doc.get("items", []),
        }
        _cache["data"] = data
        _cache["stamp"] = stamp
        return data


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _doc_search_url(vendor_conf: Dict[str, Any], query: str) -> str:
    tpl = vendor_conf.get("doc_search") or vendor_conf.get("doc_home") or ""
    if "{q}" in tpl:
        return tpl.replace("{q}", quote(query or "", safe=""))
    return tpl


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def _as_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [x.strip() for x in re.split(r"[,\s|]+", value) if x.strip()]
        return parts or None
    if isinstance(value, (list, tuple, set)):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return parts or None
    return None


def _normalize_vendors(values: Any, data: Dict[str, Any]) -> Optional[List[str]]:
    items = _as_list(values)
    if not items:
        return None
    idx = data["vendor_alias_index"]
    out = []
    for raw in items:
        vid = idx.get(raw.strip().lower())
        if vid and vid not in out:
            out.append(vid)
    return out or None


# --------------------------------------------------------------------------- #
# 文档聚合搜索
# --------------------------------------------------------------------------- #
def _score_product(product: Dict[str, Any], query: str, toks: List[str], equiv_hits: List[str]) -> Dict[str, Any]:
    q = query.strip().lower()
    score = 0
    reasons: List[str] = []

    name = (product.get("name") or "").lower()
    en = (product.get("en") or "").lower()
    aliases = [a.lower() for a in (product.get("aliases") or [])]

    if q:
        if q == name or q in aliases:
            score += 100
            reasons.append("名称精确匹配")
        elif q in name:
            score += 55
            reasons.append("产品名匹配")
        elif q in en:
            score += 40
            reasons.append("英文名匹配")
        elif any(q in a or a in q for a in aliases):
            score += 45
            reasons.append("别名匹配")

    if product.get("equiv") in equiv_hits:
        score += 38
        reasons.append("同类产品映射")

    for t in toks:
        if len(t) < 2 and not re.match(r"^[a-z0-9]$", t):
            continue
        if t in name:
            score += 18
        elif t in en:
            score += 12
        elif any(t in a for a in aliases):
            score += 14
        elif t in (product.get("summary") or "").lower():
            score += 7
        elif t in product["_hay"]:
            score += 4

    if not reasons and score > 0:
        reasons.append("关键词匹配")
    return {"score": score, "reasons": reasons}


def search_docs(
    query: str,
    vendors: Any = None,
    category: Optional[str] = None,
    limit: Any = 20,
    group_by_equivalent: bool = True,
) -> Dict[str, Any]:
    """跨四家云厂商的产品文档聚合搜索。

    返回卡片列表（产品名称、摘要、来源标识、原始文档链接）。
    """
    data = get_dataset()
    limit = _clamp(limit, 1, 200, 20)
    query = (query or "").strip()
    toks = _tokens(query)

    # 查询里包含厂商名时自动作为过滤条件
    vendor_filter = _normalize_vendors(vendors, data)
    implied_vendors: List[str] = []
    for t in toks:
        vid = data["vendor_alias_index"].get(t)
        if vid and vid not in implied_vendors:
            implied_vendors.append(vid)
    if vendor_filter is None and implied_vendors and len(implied_vendors) < 4:
        vendor_filter = implied_vendors

    # 命中的同类产品 key（支持 "对象存储"/"oss" 一次搜出四家）
    equiv_hits: List[str] = []
    alias_index = data["equiv_alias_index"]
    for key in alias_index.get(query.lower(), []):
        if key not in equiv_hits:
            equiv_hits.append(key)
    for t in toks:
        for key in alias_index.get(t, []):
            if key not in equiv_hits:
                equiv_hits.append(key)

    results: List[Dict[str, Any]] = []
    for p in data["products"]:
        if vendor_filter and p["vendor"] not in vendor_filter:
            continue
        if category and p.get("cat") != category:
            continue
        if not query:
            scored = {"score": 1, "reasons": ["全量列表"]}
        else:
            scored = _score_product(p, query, toks, equiv_hits)
            if scored["score"] <= 0:
                continue
        vendor_conf = data["vendors"].get(p["vendor"], {})
        results.append(
            {
                "product_id": p["id"],
                "vendor": p["vendor"],
                "vendor_name": p["vendor_name"],
                "vendor_short": vendor_conf.get("short", ""),
                "vendor_color": vendor_conf.get("color", "#666"),
                "name": p["name"],
                "en": p.get("en", ""),
                "category": p.get("cat", ""),
                "category_name": p["category_name"],
                "equivalent": p.get("equiv", ""),
                "equivalent_label": p["equiv_label"],
                "summary": p.get("summary", ""),
                "doc_url": p.get("doc_url", ""),
                "site_search_url": _doc_search_url(vendor_conf, query or p["name"]),
                "score": scored["score"],
                "match_reasons": scored["reasons"],
            }
        )

    vendor_order = {"tencent": 0, "aliyun": 1, "huawei": 2, "volcengine": 3}
    results.sort(key=lambda r: (-r["score"], vendor_order.get(r["vendor"], 9), r["name"]))
    total = len(results)
    results = results[:limit]

    groups: List[Dict[str, Any]] = []
    if group_by_equivalent and results:
        bucket: Dict[str, List[Dict[str, Any]]] = {}
        for r in results:
            bucket.setdefault(r["equivalent"], []).append(r)
        for key, items in bucket.items():
            groups.append(
                {
                    "equivalent": key,
                    "label": data["equivalents"].get(key, {}).get("label", key),
                    "vendors": sorted({i["vendor"] for i in items}, key=lambda v: vendor_order.get(v, 9)),
                    "product_ids": [i["product_id"] for i in items],
                }
            )
        groups.sort(key=lambda g: (-len(g["vendors"]), g["label"]))

    return {
        "query": query,
        "vendors": vendor_filter or list(data["vendors"].keys()),
        "category": category or "",
        "total": total,
        "returned": len(results),
        "matched_equivalents": equiv_hits,
        "groups": groups,
        "results": results,
        "fallback_search_links": [
            {
                "vendor": vid,
                "vendor_name": v.get("name", vid),
                "url": _doc_search_url(v, query),
            }
            for vid, v in data["vendors"].items()
            if query and (not vendor_filter or vid in vendor_filter)
        ],
        "snapshot_date": data["products_doc"].get("snapshot_date", ""),
    }


def list_products(vendor: Any = None, category: Optional[str] = None) -> Dict[str, Any]:
    """按厂商/类目列出已收录产品。"""
    data = get_dataset()
    vendor_filter = _normalize_vendors(vendor, data)
    items = []
    for p in data["products"]:
        if vendor_filter and p["vendor"] not in vendor_filter:
            continue
        if category and p.get("cat") != category:
            continue
        items.append(
            {
                "product_id": p["id"],
                "vendor": p["vendor"],
                "vendor_name": p["vendor_name"],
                "name": p["name"],
                "en": p.get("en", ""),
                "category": p.get("cat", ""),
                "category_name": p["category_name"],
                "equivalent": p.get("equiv", ""),
                "summary": p.get("summary", ""),
                "doc_url": p.get("doc_url", ""),
            }
        )
    counts: Dict[str, int] = {}
    for i in items:
        counts[i["vendor"]] = counts.get(i["vendor"], 0) + 1
    return {"total": len(items), "count_by_vendor": counts, "products": items}


def find_equivalents(keyword: str) -> Dict[str, Any]:
    """输入任一厂商产品名/缩写，返回四家的同类产品对照表。"""
    data = get_dataset()
    kw = (keyword or "").strip().lower()
    if not kw:
        return {"keyword": keyword, "matches": []}

    keys: List[str] = []
    for k in data["equiv_alias_index"].get(kw, []):
        if k not in keys:
            keys.append(k)
    if not keys:
        for p in data["products"]:
            if kw in (p.get("name") or "").lower() or kw in [a.lower() for a in (p.get("aliases") or [])]:
                if p.get("equiv") and p["equiv"] not in keys:
                    keys.append(p["equiv"])
    if not keys:
        for alias, ks in data["equiv_alias_index"].items():
            if kw in alias or alias in kw:
                for k in ks:
                    if k not in keys:
                        keys.append(k)

    matches = []
    for key in keys[:5]:
        row = {
            "equivalent": key,
            "label": data["equivalents"].get(key, {}).get("label", key),
            "vendors": {},
        }
        for p in data["products"]:
            if p.get("equiv") != key:
                continue
            row["vendors"].setdefault(p["vendor"], []).append(
                {
                    "vendor_name": p["vendor_name"],
                    "name": p["name"],
                    "doc_url": p.get("doc_url", ""),
                    "summary": p.get("summary", ""),
                }
            )
        matches.append(row)
    return {"keyword": keyword, "matches": matches}


# --------------------------------------------------------------------------- #
# ECS/CVM 价格对比
# --------------------------------------------------------------------------- #
def list_regions() -> Dict[str, Any]:
    data = get_dataset()
    return {
        "regions": data["regions"],
        "snapshot_date": data["prices_doc"].get("snapshot_date", ""),
    }


def list_specs() -> Dict[str, Any]:
    data = get_dataset()
    return {"specs": data["specs"]}


def compare_ecs_price(
    region: str = "cn-beijing",
    vcpu: Any = None,
    memory_gb: Any = None,
    spec_id: Optional[str] = None,
    vendors: Any = None,
    series: Optional[str] = None,
    charge_type: str = "monthly",
    sort: str = "asc",
) -> Dict[str, Any]:
    """同一界面/同一响应内返回四家同类配置的 ECS/CVM 价格对比。

    :param region: 统一地域 id（见 list_regions），默认华北（北京）
    :param vcpu: vCPU 核数筛选
    :param memory_gb: 内存 GB 筛选
    :param spec_id: 规格 id（如 4c8g），与 vcpu/memory 二选一
    :param vendors: 厂商过滤，支持 "tencent,aliyun" 或列表
    :param series: general（1:2 计算/标准型）或 memory（1:4 通用/内存型）
    :param charge_type: monthly（包月刊例价）| on_demand_hour（按量单价）
    """
    data = get_dataset()
    prices_doc = data["prices_doc"]
    region = (region or "cn-beijing").strip()
    region_ids = [r["id"] for r in data["regions"]]
    if region not in region_ids:
        return {
            "error": "unknown_region",
            "message": "未知地域 %r，可选：%s" % (region, ", ".join(region_ids)),
            "available_regions": region_ids,
        }

    charge_type = charge_type if charge_type in ("monthly", "on_demand_hour") else "monthly"
    vendor_filter = _normalize_vendors(vendors, data)

    try:
        vcpu_i = int(vcpu) if vcpu not in (None, "", "any") else None
    except (TypeError, ValueError):
        vcpu_i = None
    try:
        mem_i = int(float(memory_gb)) if memory_gb not in (None, "", "any") else None
    except (TypeError, ValueError):
        mem_i = None

    region_conf = next(r for r in data["regions"] if r["id"] == region)
    rows: List[Dict[str, Any]] = []
    for item in data["price_items"]:
        if vendor_filter and item["vendor"] not in vendor_filter:
            continue
        if spec_id and item.get("spec_id") != spec_id:
            continue
        if vcpu_i is not None and int(item.get("vcpu", 0)) != vcpu_i:
            continue
        if mem_i is not None and int(item.get("memory_gb", 0)) != mem_i:
            continue
        if series and item.get("series") != series:
            continue
        price = (item.get("prices") or {}).get(region)
        if not price:
            continue
        vendor_conf = data["vendors"].get(item["vendor"], {})
        rows.append(
            {
                "vendor": item["vendor"],
                "vendor_name": vendor_conf.get("name", item["vendor"]),
                "vendor_color": vendor_conf.get("color", "#666"),
                "product": item.get("product", ""),
                "region": region,
                "region_name": region_conf.get("name", region),
                "vendor_region": (region_conf.get("vendor_regions", {}).get(item["vendor"], {}) or {}).get("name", ""),
                "vendor_region_id": (region_conf.get("vendor_regions", {}).get(item["vendor"], {}) or {}).get("id", ""),
                "instance_type": item.get("instance_type", ""),
                "family": item.get("family", ""),
                "series": item.get("series", ""),
                "spec_id": item.get("spec_id", ""),
                "vcpu": item.get("vcpu"),
                "memory_gb": item.get("memory_gb"),
                "on_demand_hour": price.get("on_demand_hour"),
                "monthly": price.get("monthly"),
                "currency": prices_doc.get("currency", "CNY"),
                "source_url": item.get("source_url", ""),
            }
        )

    reverse = str(sort).lower() in ("desc", "-1", "high")
    rows.sort(key=lambda r: (r.get(charge_type) is None, r.get(charge_type) or 0), reverse=reverse)

    valid = [r for r in rows if r.get(charge_type) is not None]
    summary: Dict[str, Any] = {"count": len(rows), "charge_type": charge_type}
    if valid:
        cheapest = min(valid, key=lambda r: r[charge_type])
        dearest = max(valid, key=lambda r: r[charge_type])
        base = cheapest[charge_type] or 0
        for r in rows:
            v = r.get(charge_type)
            if v is None or not base:
                r["diff_vs_cheapest_pct"] = None
            else:
                r["diff_vs_cheapest_pct"] = round((v - base) / base * 100, 1)
            r["is_cheapest"] = bool(v is not None and v == base)
        summary.update(
            {
                "cheapest": {
                    "vendor": cheapest["vendor"],
                    "vendor_name": cheapest["vendor_name"],
                    "instance_type": cheapest["instance_type"],
                    "price": cheapest[charge_type],
                },
                "most_expensive": {
                    "vendor": dearest["vendor"],
                    "vendor_name": dearest["vendor_name"],
                    "instance_type": dearest["instance_type"],
                    "price": dearest[charge_type],
                },
                "max_gap_pct": round(((dearest[charge_type] - base) / base * 100), 1) if base else None,
            }
        )

    return {
        "filters": {
            "region": region,
            "region_name": region_conf.get("name", region),
            "vcpu": vcpu_i,
            "memory_gb": mem_i,
            "spec_id": spec_id or "",
            "series": series or "",
            "vendors": vendor_filter or list(data["vendors"].keys()),
            "charge_type": charge_type,
        },
        "summary": summary,
        "rows": rows,
        "no_data_hint": (
            ""
            if rows
            else (
                "当前价格快照未覆盖该筛选条件（地域=%s，vCPU=%s，内存=%s，规格=%s，系列=%s）。"
                "可用规格：%s；请改用受支持的规格，或通过 vendor_price_pages 中的官方价格计算器查询。"
                % (
                    region_conf.get("name", region),
                    vcpu_i or "any",
                    mem_i or "any",
                    spec_id or "any",
                    series or "any",
                    ", ".join(s["id"] for s in data["specs"]),
                )
            )
        ),
        "available_specs": [s["id"] for s in data["specs"]],
        "currency": prices_doc.get("currency", "CNY"),
        "price_scope": prices_doc.get("price_scope", ""),
        "disclaimer": prices_doc.get("disclaimer", ""),
        "snapshot_date": prices_doc.get("snapshot_date", ""),
        "extras": prices_doc.get("extras", {}),
        "vendor_price_pages": prices_doc.get("vendor_price_pages", {}),
    }


def meta() -> Dict[str, Any]:
    """前端初始化所需的全部元数据。"""
    data = get_dataset()
    counts: Dict[str, int] = {}
    for p in data["products"]:
        counts[p["vendor"]] = counts.get(p["vendor"], 0) + 1
    return {
        "vendors": data["vendors"],
        "categories": data["categories"],
        "equivalents": {k: v.get("label", k) for k, v in data["equivalents"].items()},
        "regions": data["regions"],
        "specs": data["specs"],
        "product_count": len(data["products"]),
        "product_count_by_vendor": counts,
        "products_snapshot_date": data["products_doc"].get("snapshot_date", ""),
        "prices_snapshot_date": data["prices_doc"].get("snapshot_date", ""),
        "price_disclaimer": data["prices_doc"].get("disclaimer", ""),
        "vendor_price_pages": data["prices_doc"].get("vendor_price_pages", {}),
    }
