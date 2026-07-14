#!/usr/bin/env python3
"""xianyu_search.py — 闲鱼商品搜索 via in-page mtop API（服务端筛选）。

借鉴 OpenCLI clis/xianyu/search.js (df8c75f / df8ca8d)：在已登录的持久化 session
`xianyu` 页面里调 `window.lib.mtop.request('mtop.taobao.idlemtopsearch.pc.search')`，
价格区间 / 地区交给**服务端**筛（`propValueStr.searchFilter` / `extraFilterValue`），
而非抓一屏 DOM 再本地过滤。签名由页面自带 mtop lib 完成，无需手搓。

前置：session `xianyu` 已登录（探活由 SKILL.md 前置段保证，本脚本不探活）。
输出：stdout 一行 JSON `{ok, query, count, items}`；失败 exit 1 + stderr，busy exit 3。

退出码：
  0  成功
  1  通用错误（mtop 不可用 / 响应异常 / 参数错）
  2  登录态失效（HTML 登录墙 / mtop SESSION_EXPIRED）
  3  session xianyu 正忙（fail-first）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from urllib.parse import quote_plus

CAMOUFOX_BIN = os.environ.get("CAMOUFOX_BIN", "camoufox-cli")
SESSION = "xianyu"
ROWS_PER_PAGE = 30
MAX_LIMIT = 60
MTOP_API = "mtop.taobao.idlemtopsearch.pc.search"
PAGE_INTERVAL_S = 1.0  # 翻页间隔，避免风控


class SessionBusyError(RuntimeError):
    pass


class LoginWallError(RuntimeError):
    pass


def camoufox(args: list[str], timeout: int = 60) -> dict:
    """跑 camoufox-cli --json，返回解析后的响应信封 dict。"""
    cmd = [CAMOUFOX_BIN, "--session", SESSION, "--persistent", "--json", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    combined = (r.stdout or "") + (r.stderr or "")
    if "正忙" in combined:
        raise SessionBusyError("session xianyu 正忙，请等待当前操作完成后再试")
    if not r.stdout:
        raise RuntimeError(f"camoufox-cli 无输出，stderr: {r.stderr[:200]}")
    try:
        env = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"camoufox-cli 输出非 JSON: {r.stdout[:200]}") from e
    if not env.get("success", False):
        raise RuntimeError(f"camoufox-cli 失败: {env.get('error', '未知')}")
    return env


def build_search_filter(min_price: float | None, max_price: float | None) -> str:
    """propValueStr.searchFilter = 'priceRange:<min>,<max>;'（元）。单边用 0 / 99999999 兜底。"""
    if min_price is None and max_price is None:
        return ""
    lo = min_price if min_price is not None else 0
    hi = max_price if max_price is not None else 99999999
    return f"priceRange:{lo},{hi};"


def build_extra_filter(province: str | None, city: str | None) -> str:
    """extraFilterValue = JSON({divisionList:[{province,city}],...})。city 可单独用（province 留空）。"""
    if not province and not city:
        return "{}"
    return json.dumps(
        {
            "divisionList": [{"province": province or "", "city": city or ""}],
            "excludeMultiPlacesSellers": "0",
            "extraDivision": "",
        },
        ensure_ascii=False,
    )


def build_eval_expression(
    keyword: str,
    search_filter: str,
    extra_filter: str,
    page: int,
    from_filter: bool,
) -> str:
    """构造单次 mtop 搜索的 eval 表达式（async IIFE，Playwright evaluate 会 await Promise）。

    所有动态值用 json.dumps 注入，避免字符串拼接注入（借鉴 OpenCLI dc8c75f）。
    browser-guide §5：单一表达式，无顶层 var/let/const —— IIFE 满足。
    """
    data_obj = {
        "pageNumber": page,
        "keyword": keyword,
        "fromFilter": from_filter,
        "rowsPerPage": ROWS_PER_PAGE,
        "sortValue": "",
        "sortField": "",
        "customDistance": "",
        "gps": "",
        "propValueStr": {"searchFilter": search_filter} if search_filter else {},
        "customGps": "",
        "searchReqFromPage": "pcSearch",
        "extraFilterValue": extra_filter,
        "userPositionJson": "{}",
    }
    data_js = json.dumps(data_obj, ensure_ascii=False)
    api_js = json.dumps(MTOP_API)
    # 注意：JS 正则 /\s+/g 在 Python 字符串里需转义反斜杠
    return (
        "(async () => {"
        " const clean = (v) => String(v == null ? '' : v).replace(/\\s+/g, ' ').trim();"
        " const cleanFirst = (...vs) => vs.map(clean).find(Boolean) || '';"
        " if (!window.lib || !window.lib.mtop || typeof window.lib.mtop.request !== 'function')"
        "   return {error: 'mtop-not-ready'};"
        " let response;"
        " try { response = await window.lib.mtop.request({"
        f"   api: {api_js}, data: {data_js},"
        "   type: 'POST', v: '1.0', dataType: 'json',"
        "   needLogin: false, needLoginPC: false,"
        "   sessionOption: 'AutoLoginOnly', ecode: 0"
        " }); } catch (e) {"
        "   const ret = (e && e.ret) || [];"
        "   const detail = clean(Array.isArray(ret) ? ret.join(' | ') : (e && e.message) || String(e));"
        "   return {error: 'mtop-request-failed', detail};"
        " }"
        " const ret = (response && response.ret) || [];"
        " const retCode = clean(Array.isArray(ret) ? ret[0] : '').split('::')[0];"
        " if (retCode && retCode !== 'SUCCESS')"
        "   return {error: 'mtop-response-error', code: retCode, detail: clean(ret.join(' | '))};"
        " const list = (response && response.data && Array.isArray(response.data.resultList))"
        "   ? response.data.resultList : null;"
        " if (!list) return {error: 'malformed-response'};"
        " const items = [];"
        " for (const entry of list) {"
        "   const itemNode = (entry && entry.data && entry.data.item) || {};"
        "   const main = itemNode.main || {};"
        "   const args = (main.clickParam && main.clickParam.args) || {};"
        "   const ex = main.exContent || itemNode.exContent || {};"
        "   const itemId = clean(args.item_id || args.id || '');"
        "   const title = clean(ex.title || (ex.detailParams && ex.detailParams.title) || '');"
        "   if (!itemId || !title) continue;"
        "   const priceYuan = clean(args.price || args.displayPrice || '');"
        "   const city = clean(args.p_city || '');"
        "   const area = clean(ex.area || '');"
        "   items.push({"
        "     item_id: itemId, title,"
        "     price: priceYuan ? ('¥' + priceYuan) : '',"
        "     condition: cleanFirst(ex.condition, ex.stuffStatus, ex.detailParams && ex.detailParams.condition),"
        "     brand: cleanFirst(ex.brand, ex.brandName, ex.detailParams && ex.detailParams.brand),"
        "     location: city || area,"
        "     want: clean(args.wantNum || ex.want || ''),"
        "     url: 'https://www.goofish.com/item?id=' + itemId"
        "   });"
        " }"
        " return {items, page_count: list.length};"
        "})()"
    )


def _eval_result(env: dict) -> dict:
    """从 camoufox --json eval 信封里取 IIFE 返回值。"""
    data = env.get("data") or {}
    result = data.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"mtop eval 返回异常: {env}")
    return result


def search(
    query: str,
    min_price: float | None,
    max_price: float | None,
    province: str | None,
    city: str | None,
    limit: int,
) -> list[dict]:
    search_filter = build_search_filter(min_price, max_price)
    extra_filter = build_extra_filter(province, city)
    from_filter = bool(search_filter or (province or city))
    effective_limit = min(limit, MAX_LIMIT)
    max_pages = max(1, (effective_limit + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

    collected: list[dict] = []
    for page in range(1, max_pages + 1):
        if len(collected) >= effective_limit:
            break
        expr = build_eval_expression(query, search_filter, extra_filter, page, from_filter)
        env = camoufox(["eval", expr])
        result = _eval_result(env)

        err = result.get("error")
        if err:
            detail = result.get("detail", "")
            if err == "mtop-not-ready":
                raise RuntimeError("window.lib.mtop 未就绪——open goofish.com 搜索页加载 mtop lib 后重试")
            if "SESSION_EXPIRED" in detail.upper() or "FAIL_SYS_SESSION_EXPIRED" in detail.upper():
                raise LoginWallError(f"mtop session 失效: {detail}")
            raise RuntimeError(f"mtop 错误 {err}: {detail}")

        items = result.get("items", [])
        if not items:
            break
        collected.extend(items)
        if page < max_pages and len(collected) < effective_limit:
            time.sleep(PAGE_INTERVAL_S)

    return collected[:effective_limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="闲鱼商品搜索 via mtop（服务端价格/地区筛选）")
    ap.add_argument("--query", required=True, help="搜索关键词")
    ap.add_argument("--min-price", type=float, default=None, help="最低价（元）")
    ap.add_argument("--max-price", type=float, default=None, help="最高价（元）")
    ap.add_argument("--province", default=None, help="省份（如 广东）")
    ap.add_argument("--city", default=None, help="城市（如 深圳，可单独用）")
    ap.add_argument("--limit", type=int, default=20, help=f"结果数上限 1..{MAX_LIMIT}")
    ap.add_argument("--no-open", action="store_true", help="不先 open 搜索页（调用方已 open）")
    args = ap.parse_args()

    if args.limit < 1 or args.limit > MAX_LIMIT:
        sys.stderr.write(f"--limit 必须在 1..{MAX_LIMIT}\n")
        sys.exit(1)
    if args.min_price is not None and args.min_price < 0:
        sys.stderr.write("--min-price 不能为负\n")
        sys.exit(1)
    if args.max_price is not None and args.max_price < 0:
        sys.stderr.write("--max-price 不能为负\n")
        sys.exit(1)
    if (
        args.min_price is not None
        and args.max_price is not None
        and args.min_price > args.max_price
    ):
        sys.stderr.write("--min-price 不能大于 --max-price\n")
        sys.exit(1)

    try:
        # 先 open 搜索页加载 mtop lib（若已 open 则快速重入）
        if not args.no_open:
            camoufox(["open", f"https://www.goofish.com/search?q={quote_plus(args.query)}"])
            time.sleep(3)

        results = search(
            args.query,
            args.min_price,
            args.max_price,
            args.province,
            args.city,
            args.limit,
        )
    except SessionBusyError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(3)
    except LoginWallError as e:
        sys.stderr.write(f"🔒 登录态失效: {e}\n")
        print(json.dumps({"ok": False, "error": "SESSION_EXPIRED", "platform": SESSION}, ensure_ascii=False))
        sys.exit(2)

    print(
        json.dumps(
            {
                "ok": True,
                "query": args.query,
                "filters": {
                    "min_price": args.min_price,
                    "max_price": args.max_price,
                    "province": args.province,
                    "city": args.city,
                },
                "count": len(results),
                "items": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
