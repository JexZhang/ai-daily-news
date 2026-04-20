#!/usr/bin/env python3
"""
AI 新闻 JSON 七层校验脚本（独立可复用）

校验层：
  1. JSON Schema：结构、必填字段、类型、长度、URL 格式、唯一性
  2. 日期校验：每条新闻 date 字段必须等于【北京时间】昨天 (YYYY-MM-DD)
  3. 今日头条拦截：任何包含 toutiao.com 的链接都会被拒绝
  4. URL 路径特征检查：拦截分类页/搜索页/列表页（非文章页面）
  5. 来源集中度：同一新闻网站（按域名判定）不得出现 ≥3 条新闻
  6. 跨分区查重：国内与国际新闻标题关键词重叠度 ≥50% 视为重复
  7. 链接可达性：并发 HEAD/GET，超时 8s，2xx/3xx 算通过
  8. 页面日期交叉验证：从页面元数据提取真实发布日期，与声称日期比对

用法：
  python3 validate-news.py '<JSON 字符串>'
  python3 validate-news.py /path/to/news.json            # 自动识别文件路径
  echo '<JSON>' | python3 validate-news.py -              # 从 stdin 读取
  python3 validate-news.py --skip-url-check '<JSON>'     # 应急跳过链接检查

退出码：0 = 通过，1 = 失败（错误详情输出到 stderr）

所有输出均走 stderr，便于上游脚本用管道消费 stdout（当前无 stdout 输出）。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import re
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


# ---------- 第三层：今日头条链接拦截 ----------

def validate_no_toutiao(
    all_items: list[tuple[str, dict]],
) -> list[str]:
    """检查所有链接是否包含 toutiao.com，若有则校验不通过。"""
    errors: list[str] = []
    for prefix, item in all_items:
        url = item.get("url", "")
        if isinstance(url, str) and "toutiao.com" in url.lower():
            errors.append(f"{prefix}: 禁止使用今日头条链接 ({url})")
    return errors


# ---------- 第四层：URL 路径特征检查（拦截分类页/搜索页/列表页）----------

# 常见的非文章页面路径模式
NON_ARTICLE_PATH_PATTERNS = [
    r'/search/',      # 搜索页
    r'/category/',    # 分类页
    r'/tag/',         # 标签页
    r'/topic/',       # 专题页
    r'/information/', # 信息列表页（如 36kr）
    r'/news_list/',   # 新闻列表
    r'/article_list/',# 文章列表
    r'/list/',        # 通用列表页
    r'/archive/',     # 归档页
    r'/page/\d+',     # 分页页（如 /page/2）
]

# 常见的查询参数（列表页特征）
NON_ARTICLE_QUERY_PARAMS = [
    'page=',     # 分页
    'p=',        # 分页
    's=',        # 搜索关键词
    'type=',     # 类型筛选
    'cat=',      # 分类
    'tag=',      # 标签
    'keyword=',  # 关键词
    'q=',        # 搜索
    'sort=',     # 排序
    'filter=',   # 筛选
]


def _is_non_article_url(url: str) -> tuple[bool, str | None]:
    """
    检查 URL 是否为非文章页面（分类页/搜索页/列表页）。
    返回 (是否为非文章页, 原因说明)。
    
    示例：
    - https://www.aibase.com/search/OpenAI&type=0 → 是（搜索页）
    - https://www.36kr.com/information/AI/ → 是（分类列表页）
    - https://news.aibase.com/news/27236 → 否（文章页）
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    
    # 检查路径模式
    for pattern in NON_ARTICLE_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return True, f"路径包含列表页特征 '{pattern}'"
    
    # 检查查询参数
    for param in NON_ARTICLE_QUERY_PARAMS:
        if param in query:
            return True, f"查询参数包含列表页特征 '{param}'"
    
    return False, None


def validate_url_path_features(
    all_items: list[tuple[str, dict]],
) -> list[str]:
    """检查所有链接是否为真正的文章页面，拦截分类页/搜索页/列表页。"""
    errors: list[str] = []
    for prefix, item in all_items:
        url = item.get("url", "")
        if isinstance(url, str) and url.strip():
            is_non_article, reason = _is_non_article_url(url.strip())
            if is_non_article:
                errors.append(f"{prefix}: 链接指向非文章页面 - {reason} ({url})")
    return errors


MAX_SAME_DOMAIN = 3


def _extract_site_domain(url: str) -> str:
    """
    提取新闻网站的主域名，用于判断是否来自同一网站。
    例如：
      https://www.qbitai.com/2026/04/401094.html → qbitai.com
      https://www.qbitai.com/2026/04/401507.html → qbitai.com
      https://www.36kr.com/p/123456             → 36kr.com
    """
    netloc = urllib.parse.urlparse(url.strip()).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


# ---------- 第五层：来源集中度（同一网站 ≥3 条则拦截）----------

def validate_source_diversity(
    all_items: list[tuple[str, dict]],
) -> list[str]:
    """检查所有新闻的链接域名，同一网站不得出现 ≥ MAX_SAME_DOMAIN 条。"""
    domain_items: dict[str, list[str]] = {}
    for prefix, item in all_items:
        url = item.get("url", "")
        if not isinstance(url, str) or not url.strip():
            continue
        domain = _extract_site_domain(url)
        if not domain:
            continue
        domain_items.setdefault(domain, []).append(prefix)

    errors: list[str] = []
    for domain, prefixes in sorted(domain_items.items()):
        if len(prefixes) >= MAX_SAME_DOMAIN:
            refs = ", ".join(prefixes)
            errors.append(
                f"来自 {domain} 的新闻有 {len(prefixes)} 条（{refs}），"
                f"同一网站不得 ≥{MAX_SAME_DOMAIN} 条"
            )
    return errors


DEDUP_OVERLAP_THRESHOLD = 0.50


# ---------- 第六层：跨分区内容查重 ----------

def _extract_keywords(title: str) -> set[str]:
    """
    从标题中提取关键词集合，用于跨分区重复检测。
    提取规则：
      - 英文单词/缩写（≥2 字符），统一小写
      - 连续数字串（如 200、5.4、2030）
      - 中文使用 bigram（相邻二字组合）切分，解决中文无空格分词问题
        例如 "斯坦福发布" → {"斯坦", "坦福", "福发", "发布"}
    """
    keywords: set[str] = set()
    for en_word in re.findall(r"[A-Za-z]{2,}", title):
        keywords.add(en_word.lower())
    for num in re.findall(r"\d+(?:\.\d+)?", title):
        keywords.add(num)
    for cjk_seq in re.findall(r"[\u4e00-\u9fff]{2,}", title):
        for i in range(len(cjk_seq) - 1):
            keywords.add(cjk_seq[i : i + 2])
    return keywords


def validate_no_cross_duplicates(
    all_items: list[tuple[str, dict]],
) -> list[str]:
    """
    检测国内与国际新闻之间是否存在描述同一事件的重复条目。
    对每一对 (chi[i], foreign[j])，计算标题关键词重叠度，
    超过阈值则判定为重复。
    """
    chi_items = [(p, it) for p, it in all_items if p.startswith("chi")]
    foreign_items = [(p, it) for p, it in all_items if p.startswith("foreign")]

    errors: list[str] = []
    for cp, ci in chi_items:
        ck = _extract_keywords(ci.get("title", ""))
        if not ck:
            continue
        for fp, fi in foreign_items:
            fk = _extract_keywords(fi.get("title", ""))
            if not fk:
                continue
            overlap = ck & fk
            smaller = min(len(ck), len(fk))
            if smaller == 0:
                continue
            ratio = len(overlap) / smaller
            if ratio >= DEDUP_OVERLAP_THRESHOLD:
                shared = ", ".join(sorted(overlap))
                errors.append(
                    f"{cp} 与 {fp} 疑似描述同一事件"
                    f"（关键词重叠 {ratio:.0%}：{shared}）"
                )
    return errors


# ---------- 第七层：链接可达性 ----------

def _get_is_alive(status: int) -> bool:
    """
    GET 阶段判断资源是否真实存在：
    - 2xx/3xx：明确存在
    - 405：方法不允许（极罕见于 GET，容忍）
    - 401/403/429：无法确认页面存在（Cloudflare/WAF 对不存在的路径也返回
      403/429），视为失败——宁可误杀也不放过假链接
    - 404/410：明确死链
    - 5xx：服务端错误
    """
    if 200 <= status < 400:
        return True
    if status == 405:
        return True
    return False


# 优先级从高到低：结构化元数据 > HTML 正文中的日期标签
_DATE_META_PATTERNS = [
    # Open Graph / article meta
    re.compile(r'property=["\'](?:og:release_date|article:published_time)["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\']\s+property=["\'](?:og:release_date|article:published_time)["\']', re.I),
    # JSON-LD
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I),
    # name=publishdate 变体
    re.compile(r'name=["\'](?:publishdate|publish_date|PubDate)["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\']\s+name=["\'](?:publishdate|publish_date|PubDate)["\']', re.I),
]

# HTML body 中常见的日期容器（WordPress 主题、新闻 CMS 等）
_DATE_BODY_PATTERNS = [
    # <span class="date">2026-04-14</span>  (量子位等 WordPress 主题)
    re.compile(r'<(?:span|time|div)[^>]*class=["\'][^"\']*\b(?:date|publish|pubdate|post-date|entry-date|article-date)\b[^"\']*["\'][^>]*>\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', re.I),
    # <time datetime="2026-04-14T...">
    re.compile(r'<time[^>]*datetime=["\'](\d{4}[-/]\d{1,2}[-/]\d{1,2})[^"\']*["\']', re.I),
    # <meta itemprop="datePublished" content="...">
    re.compile(r'itemprop=["\']datePublished["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\']\s+itemprop=["\']datePublished["\']', re.I),
]

_DATE_EXTRACT_RE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")


def _extract_page_date(html: str) -> str | None:
    """
    从页面 HTML 中提取发布日期。
    优先从 meta 标签/JSON-LD 提取，其次从 HTML body 的日期容器提取。
    返回 YYYY-MM-DD 或 None（提取不到则不做判定）。
    """
    for pat in _DATE_META_PATTERNS + _DATE_BODY_PATTERNS:
        m = pat.search(html)
        if m:
            raw = m.group(1).strip()
            dm = _DATE_EXTRACT_RE.search(raw)
            if dm:
                try:
                    d = datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
                    return d.isoformat()
                except ValueError:
                    continue
    return None


def check_single_url(url: str) -> tuple[bool, str, str | None]:
    """
    直接用 GET 请求验证链接可达性并提取页面发布日期。
    不再使用 HEAD 预探测——因为需要读取 body 来提取日期元数据。
    返回 (是否可达, 状态说明, 页面提取的发布日期或 None)。
    """
    try:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
    except ValueError as e:
        return False, f"URL 非法: {e}", None

    try:
        with urllib.request.urlopen(req, timeout=URL_TIMEOUT_SEC) as resp:
            status = getattr(resp, "status", 200)
            page_date = None
            if _get_is_alive(status):
                try:
                    body = resp.read(32768).decode("utf-8", errors="replace")
                    page_date = _extract_page_date(body)
                except Exception:
                    pass
                return True, f"HTTP {status}", page_date
            return False, f"HTTP {status}", None
    except urllib.error.HTTPError as e:
        if _get_is_alive(e.code):
            return True, f"HTTP {e.code}", None
        return False, f"HTTP {e.code}", None
    except urllib.error.URLError as e:
        return False, f"网络错误: {e.reason}", None
    except TimeoutError:
        return False, f"超时 (>{URL_TIMEOUT_SEC}s)", None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def validate_urls(
    all_items: list[tuple[str, dict]],
    expected_date: str,
) -> tuple[list[str], list[str], int, int]:
    """
    并发校验链接可达性，同时提取页面日期做交叉验证。
    返回 (url_errors, page_date_errors, passed_count, total_count)。
    """
    urls: list[tuple[str, str]] = [
        (prefix, item["url"].strip())
        for prefix, item in all_items
        if isinstance(item.get("url"), str) and item["url"].strip()
    ]
    if not urls:
        return [], [], 0, 0

    url_errors: list[str] = []
    page_date_errors: list[str] = []
    passed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=URL_MAX_WORKERS) as ex:
        future_map = {
            ex.submit(check_single_url, url): (prefix, url)
            for prefix, url in urls
        }
        for fut in concurrent.futures.as_completed(future_map):
            prefix, url = future_map[fut]
            ok, msg, page_date = fut.result()
            if ok:
                passed += 1
                if page_date and page_date != expected_date:
                    page_date_errors.append(
                        f"{prefix}: 页面元数据日期 {page_date} ≠ "
                        f"北京时间昨天 {expected_date}（{url}）"
                    )
            else:
                url_errors.append(f"{prefix}: {url} — {msg}")
    return url_errors, page_date_errors, passed, len(urls)


# ---------- 主入口 ----------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI 新闻 JSON 校验（schema / 日期 / 链接可达性）",
    )
    parser.add_argument(
        "json_input",
        help="JSON 字符串、JSON 文件路径、或 `-`（从 stdin 读取）",
    )
    parser.add_argument(
        "--skip-url-check",
        action="store_true",
        help="跳过链接可达性校验（应急/离线环境）",
    )
    args = parser.parse_args()

    inp = args.json_input
    if inp == "-":
        raw = sys.stdin.read()
    elif os.path.isfile(inp):
        with open(inp, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = inp

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

    # 3. 今日头条拦截
    toutiao_errors = validate_no_toutiao(all_items) if all_items else []

    # 4. URL 路径特征检查
    url_path_errors = validate_url_path_features(all_items) if all_items else []

    # 5. 来源集中度
    diversity_errors = validate_source_diversity(all_items) if all_items else []

    # 6. 跨分区查重
    dedup_errors = validate_no_cross_duplicates(all_items) if all_items else []

    # 7. 链接可达性 + 8. 页面日期交叉验证（合并在一次请求中）
    if args.skip_url_check:
        url_errors, page_date_errors, url_passed, url_total = [], [], 0, 0
    else:
        url_errors, page_date_errors, url_passed, url_total = (
            validate_urls(all_items, expected_date) if all_items else ([], [], 0, 0)
        )

    # 摘要行
    def mark(errs: list[str]) -> str:
        return "✓" if not errs else "✗"

    url_summary = (
        "⊘ (已跳过)"
        if args.skip_url_check
        else f"{mark(url_errors)} ({url_passed}/{url_total})"
    )
    page_date_summary = "⊘ (已跳过)" if args.skip_url_check else mark(page_date_errors)
    url_path_summary = mark(url_path_errors)
    log(
        f"[validate] schema {mark(schema_errors)}  "
        f"日期 {mark(date_errors)} (期望北京时间 {expected_date})  "
        f"今日头条 {mark(toutiao_errors)}  "
        f"URL 路径特征 {url_path_summary}  "
        f"来源集中度 {mark(diversity_errors)}  "
        f"跨分区查重 {mark(dedup_errors)}  "
        f"链接 {url_summary}  "
        f"页面日期 {page_date_summary}"
    )

    # 错误汇总
    sections = []
    if schema_errors:
        sections.append(("JSON schema", schema_errors))
    if date_errors:
        sections.append(("日期校验", date_errors))
    if toutiao_errors:
        sections.append(("今日头条拦截", toutiao_errors))
    if url_path_errors:
        sections.append(("URL 路径特征", url_path_errors))
    if diversity_errors:
        sections.append(("来源集中度", diversity_errors))
    if dedup_errors:
        sections.append(("跨分区查重", dedup_errors))
    if url_errors:
        sections.append(("链接可达性", url_errors))
    if page_date_errors:
        sections.append(("页面日期交叉验证", page_date_errors))

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
