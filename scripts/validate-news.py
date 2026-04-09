#!/usr/bin/env python3
"""
AI 新闻 JSON 三层校验脚本（独立可复用）

校验层：
  1. JSON Schema：结构、必填字段、类型、长度、URL 格式、唯一性
  2. 日期校验：每条新闻 date 字段必须等于【北京时间】昨天 (YYYY-MM-DD)
  3. 链接可达性：并发 HEAD/GET，超时 8s，2xx/3xx 算通过

用法：
  python3 validate-news.py '<JSON字符串>'
  echo '<JSON>' | python3 validate-news.py -
  python3 validate-news.py --skip-url-check '<JSON>'     # 应急跳过链接检查

退出码：0 = 通过，1 = 失败（错误详情输出到 stderr）

所有输出均走 stderr，便于上游脚本用管道消费 stdout（当前无 stdout 输出）。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

REQUIRED_FIELDS = ("title", "summary", "url", "date")
REQUIRED_SECTIONS = ("chi", "foreign")
ITEMS_PER_SECTION = 3

TITLE_MIN, TITLE_MAX = 6, 40
SUMMARY_MIN, SUMMARY_MAX = 30, 120

URL_TIMEOUT_SEC = 8
URL_MAX_WORKERS = 6
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------- 工具 ----------

def beijing_yesterday_iso() -> str:
    """返回北京时间昨天的日期 (YYYY-MM-DD)。"""
    now_bj = datetime.datetime.now(BEIJING_TZ)
    return (now_bj.date() - datetime.timedelta(days=1)).isoformat()


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr)


# ---------- 第一层：JSON Schema ----------

def validate_schema(data) -> tuple[list[str], list[tuple[str, dict]]]:
    """返回 (错误列表, 扁平化的所有 news item: [(prefix, item), ...])"""
    errors: list[str] = []
    all_items: list[tuple[str, dict]] = []

    if not isinstance(data, dict):
        return ["根结构必须是 JSON 对象 {chi:[...], foreign:[...]}"], []

    for section in REQUIRED_SECTIONS:
        if section not in data:
            errors.append(f"缺少顶层字段 `{section}`")
            continue
        arr = data[section]
        if not isinstance(arr, list):
            errors.append(f"`{section}` 必须是数组")
            continue
        if len(arr) != ITEMS_PER_SECTION:
            errors.append(
                f"`{section}` 必须恰好 {ITEMS_PER_SECTION} 条新闻，当前 {len(arr)} 条"
            )

        for idx, item in enumerate(arr):
            prefix = f"{section}[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix}: 必须是 JSON 对象")
                continue

            # 必填字段 + 类型
            for field in REQUIRED_FIELDS:
                if field not in item:
                    errors.append(f"{prefix}: 缺少字段 `{field}`")
                    continue
                if not isinstance(item[field], str) or not item[field].strip():
                    errors.append(f"{prefix}: `{field}` 必须是非空字符串")

            # title 长度
            title = item.get("title")
            if isinstance(title, str) and title.strip():
                tl = len(title)
                if tl < TITLE_MIN or tl > TITLE_MAX:
                    errors.append(
                        f"{prefix}: title 长度 {tl}，要求 {TITLE_MIN}-{TITLE_MAX} 字"
                    )

            # summary 长度
            summary = item.get("summary")
            if isinstance(summary, str) and summary.strip():
                sl = len(summary)
                if sl < SUMMARY_MIN or sl > SUMMARY_MAX:
                    errors.append(
                        f"{prefix}: summary 长度 {sl}，要求 {SUMMARY_MIN}-{SUMMARY_MAX} 字"
                    )

            # url 格式
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                parsed = urllib.parse.urlparse(url.strip())
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append(f"{prefix}: url 格式非法 ({url})")

            all_items.append((prefix, item))

    # 唯一性：URL / 标题
    seen_urls: dict[str, str] = {}
    seen_titles: dict[str, str] = {}
    for prefix, item in all_items:
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            norm = url.strip().rstrip("/")
            if norm in seen_urls:
                errors.append(f"{prefix}: url 与 {seen_urls[norm]} 重复")
            else:
                seen_urls[norm] = prefix

        title = item.get("title")
        if isinstance(title, str) and title.strip():
            norm_t = title.strip()
            if norm_t in seen_titles:
                errors.append(f"{prefix}: title 与 {seen_titles[norm_t]} 重复")
            else:
                seen_titles[norm_t] = prefix

    return errors, all_items


# ---------- 第二层：日期校验 ----------

def validate_dates(
    all_items: list[tuple[str, dict]],
    expected: str,
) -> list[str]:
    errors: list[str] = []
    for prefix, item in all_items:
        d = item.get("date")
        if not isinstance(d, str) or not d.strip():
            # schema 层已经报过，这里不重复
            continue
        try:
            parsed = datetime.date.fromisoformat(d.strip())
        except ValueError:
            errors.append(f"{prefix}: date `{d}` 格式非法，要求 YYYY-MM-DD")
            continue
        if parsed.isoformat() != expected:
            errors.append(
                f"{prefix}: date {parsed.isoformat()} ≠ 北京时间昨天 {expected}"
            )
    return errors


# ---------- 第三层：链接可达性 ----------

def _status_is_alive(status: int) -> bool:
    """
    判断 HTTP 状态码是否代表"资源真实存在"：
    - 2xx/3xx：明确存在
    - 401/403/429：资源存在但被权限或限流拦截（常见于 CF/WAF 反爬），视为存在
    - 405：方法不允许（HEAD 被拒），视为存在
    - 404/410：明确死链，视为失败
    - 5xx：服务端错误，视为失败
    """
    if 200 <= status < 400:
        return True
    if status in (401, 403, 405, 429):
        return True
    return False


def check_single_url(url: str) -> tuple[bool, str]:
    """尝试 HEAD，不支持时降级 GET。返回 (是否可达, 说明)。"""
    last_msg = "未知错误"
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
        except ValueError as e:
            return False, f"URL 非法: {e}"
        try:
            with urllib.request.urlopen(req, timeout=URL_TIMEOUT_SEC) as resp:
                status = getattr(resp, "status", 200)
                if _status_is_alive(status):
                    return True, f"HTTP {status}"
                last_msg = f"HTTP {status}"
                # HEAD 的非存活状态尝试降级 GET
                if method == "HEAD":
                    continue
                return False, last_msg
        except urllib.error.HTTPError as e:
            if _status_is_alive(e.code):
                return True, f"HTTP {e.code}"
            last_msg = f"HTTP {e.code}"
            if method == "HEAD":
                continue
            return False, last_msg
        except urllib.error.URLError as e:
            return False, f"网络错误: {e.reason}"
        except TimeoutError:
            return False, f"超时 (>{URL_TIMEOUT_SEC}s)"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
    return False, last_msg


def validate_urls(
    all_items: list[tuple[str, dict]],
) -> tuple[list[str], int, int]:
    urls: list[tuple[str, str]] = [
        (prefix, item["url"].strip())
        for prefix, item in all_items
        if isinstance(item.get("url"), str) and item["url"].strip()
    ]
    if not urls:
        return [], 0, 0

    errors: list[str] = []
    passed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=URL_MAX_WORKERS) as ex:
        future_map = {ex.submit(check_single_url, url): (prefix, url) for prefix, url in urls}
        for fut in concurrent.futures.as_completed(future_map):
            prefix, url = future_map[fut]
            ok, msg = fut.result()
            if ok:
                passed += 1
            else:
                errors.append(f"{prefix}: {url} — {msg}")
    return errors, passed, len(urls)


# ---------- 主入口 ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI 新闻 JSON 校验（schema / 日期 / 链接可达性）",
    )
    parser.add_argument(
        "json_input",
        help="JSON 字符串；传 `-` 则从 stdin 读取",
    )
    parser.add_argument(
        "--skip-url-check",
        action="store_true",
        help="跳过链接可达性校验（应急/离线环境）",
    )
    args = parser.parse_args()

    raw = sys.stdin.read() if args.json_input == "-" else args.json_input

    # 解析 JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log("[validate] JSON 解析失败 ✗")
        log(f"  - {e.msg} (line {e.lineno} col {e.colno})")
        log("\n❌ 校验失败：JSON 本身无法解析。")
        return 1

    # 1. schema
    schema_errors, all_items = validate_schema(data)

    # 2. 日期
    expected_date = beijing_yesterday_iso()
    date_errors = validate_dates(all_items, expected_date) if all_items else []

    # 3. 链接
    if args.skip_url_check:
        url_errors, url_passed, url_total = [], 0, 0
    else:
        url_errors, url_passed, url_total = (
            validate_urls(all_items) if all_items else ([], 0, 0)
        )

    # 摘要行
    def mark(errs: list[str]) -> str:
        return "✓" if not errs else "✗"

    url_summary = (
        "⊘ (已跳过)"
        if args.skip_url_check
        else f"{mark(url_errors)} ({url_passed}/{url_total})"
    )
    log(
        f"[validate] schema {mark(schema_errors)}  "
        f"日期 {mark(date_errors)} (期望北京时间 {expected_date})  "
        f"链接 {url_summary}"
    )

    # 错误汇总
    sections = []
    if schema_errors:
        sections.append(("JSON schema", schema_errors))
    if date_errors:
        sections.append(("日期校验", date_errors))
    if url_errors:
        sections.append(("链接可达性", url_errors))

    if sections:
        log("")
        for name, errs in sections:
            log(f"[{name}] 共 {len(errs)} 个问题：")
            for e in errs:
                log(f"  - {e}")
        log("\n❌ 校验失败，请修正 JSON 后重试。")
        return 1

    log("✅ 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
