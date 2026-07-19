#!/usr/bin/env python3
"""Crawl public data from Pakistan Bureau of Statistics (https://www.pbs.gov.pk/).

Collects WordPress REST content, sitemap URLs, document media catalog,
and downloadable file links discovered in page HTML. Produces JSON/CSV/Excel
and a Persian+English summary report under ./output/.
"""

from __future__ import annotations

import csv
import html
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.pbs.gov.pk"
API = f"{BASE}/wp-json/wp/v2"
OUT = Path(__file__).resolve().parent / "output"
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "PBS-Public-Data-Crawler/1.0 (+research; respectful crawl)",
        "Accept": "application/json,text/html,*/*",
    }
)

CONTENT_TYPES = [
    "pages",
    "posts",
    "product",
    "docs",
    "awsm_job_openings",
]

DOC_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/zip",
    "text/csv",
]

# WP returns the entire media library when mime_type is unknown/unsupported.
# Probe unfiltered total once and skip bogus filters.
_MEDIA_LIBRARY_TOTAL: int | None = None

FILE_EXT_RE = re.compile(
    r"https?://[^\s\"'<>]+\.(?:pdf|xlsx?|csv|zip|docx?|pptx?)(?:\?[^\s\"'<>]*)?",
    re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_json(url: str, params: dict | None = None, retries: int = 4) -> tuple[Any, dict]:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            headers = {k.lower(): v for k, v in r.headers.items()}
            if "application/json" in headers.get("content-type", ""):
                return r.json(), headers
            return r.text, headers
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed GET {url}: {last_err}")


def get_html(url: str, retries: int = 3) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed HTML GET {url}: {last_err}")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(TAG_RE.sub(" ", value))
    return WS_RE.sub(" ", text).strip()


def fetch_collection(endpoint: str, per_page: int = 100) -> list[dict]:
    items: list[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data, headers = get_json(
            f"{API}/{endpoint}",
            {
                "per_page": per_page,
                "page": page,
                "orderby": "id",
                "order": "asc",
                "context": "view",
            },
        )
        if isinstance(data, dict) and data.get("code"):
            print(f"  skip {endpoint}: {data.get('message')}")
            return items
        if not isinstance(data, list):
            print(f"  unexpected payload for {endpoint}")
            return items
        items.extend(data)
        total_pages = int(headers.get("x-wp-totalpages", page) or page)
        total = headers.get("x-wp-total", "?")
        print(f"  {endpoint}: page {page}/{total_pages} (total={total})")
        page += 1
        time.sleep(0.15)
    return items


def media_library_total() -> int:
    global _MEDIA_LIBRARY_TOTAL
    if _MEDIA_LIBRARY_TOTAL is None:
        _, headers = get_json(
            f"{API}/media",
            {"per_page": 1, "_fields": "id"},
        )
        _MEDIA_LIBRARY_TOTAL = int(headers.get("x-wp-total", 0) or 0)
        print(f"  media library total={_MEDIA_LIBRARY_TOTAL}")
    return _MEDIA_LIBRARY_TOTAL


def fetch_media_by_mime(mime_type: str, per_page: int = 100) -> list[dict]:
    items: list[dict] = []
    page = 1
    total_pages = 1
    lib_total = media_library_total()
    while page <= total_pages:
        data, headers = get_json(
            f"{API}/media",
            {
                "per_page": per_page,
                "page": page,
                "mime_type": mime_type,
                "orderby": "id",
                "order": "asc",
                "_fields": "id,date,modified,slug,link,title,source_url,mime_type,media_type,media_details,alt_text",
            },
        )
        if not isinstance(data, list):
            break
        total = int(headers.get("x-wp-total", 0) or 0)
        # Unsupported mime filters fall back to the full library.
        if page == 1 and lib_total and total == lib_total:
            sample_mimes = {(x.get("mime_type") or "") for x in data[:20]}
            if mime_type not in sample_mimes:
                print(
                    f"  media[{mime_type}]: skipped unsupported filter "
                    f"(API returned full library total={total})"
                )
                return []
        matched = [x for x in data if (x.get("mime_type") or "") == mime_type]
        items.extend(matched)
        total_pages = int(headers.get("x-wp-totalpages", page) or page)
        print(
            f"  media[{mime_type}]: page {page}/{total_pages} "
            f"(total={total}, matched_so_far={len(items)})"
        )
        page += 1
        time.sleep(0.12)
    return items


def normalize_content_item(item: dict, content_type: str) -> dict:
    content_html = (item.get("content") or {}).get("rendered") or ""
    excerpt_html = (item.get("excerpt") or {}).get("rendered") or ""
    title = strip_html((item.get("title") or {}).get("rendered") or "")
    file_links = sorted(set(FILE_EXT_RE.findall(content_html)))
    return {
        "id": item.get("id"),
        "type": content_type,
        "slug": item.get("slug"),
        "link": item.get("link"),
        "status": item.get("status"),
        "date": item.get("date"),
        "modified": item.get("modified"),
        "title": title,
        "excerpt": strip_html(excerpt_html),
        "content_text": strip_html(content_html),
        "content_html": content_html,
        "file_links": file_links,
        "categories": item.get("categories") or item.get("product_cat") or [],
        "tags": item.get("tags") or item.get("product_tag") or [],
    }


def normalize_media(item: dict) -> dict:
    details = item.get("media_details") or {}
    filesize = details.get("filesize")
    return {
        "id": item.get("id"),
        "date": item.get("date"),
        "modified": item.get("modified"),
        "slug": item.get("slug"),
        "title": strip_html((item.get("title") or {}).get("rendered") or ""),
        "alt_text": item.get("alt_text") or "",
        "mime_type": item.get("mime_type"),
        "media_type": item.get("media_type"),
        "source_url": item.get("source_url"),
        "link": item.get("link"),
        "filesize": filesize,
        "width": details.get("width"),
        "height": details.get("height"),
    }


def parse_sitemap_index() -> list[str]:
    xml = get_html(f"{BASE}/sitemap_index.xml")
    return re.findall(r"<loc>(.*?)</loc>", xml)


def parse_sitemap_urls(sitemap_url: str) -> list[dict]:
    xml = get_html(sitemap_url)
    # Support nested sitemap indexes
    if "<sitemapindex" in xml:
        urls = []
        for loc in re.findall(r"<loc>(.*?)</loc>", xml):
            urls.extend(parse_sitemap_urls(loc))
            time.sleep(0.1)
        return urls
    entries = []
    for block in re.findall(r"<url>(.*?)</url>", xml, flags=re.S):
        locs = re.findall(r"<loc>(.*?)</loc>", block)
        lastmods = re.findall(r"<lastmod>(.*?)</lastmod>", block)
        if locs:
            entries.append({"url": locs[0], "lastmod": lastmods[0] if lastmods else ""})
    return entries


def discover_files_from_urls(page_urls: list[str], limit: int | None = None) -> list[dict]:
    discovered: dict[str, dict] = {}
    urls = page_urls[:limit] if limit else page_urls
    for i, url in enumerate(urls, 1):
        try:
            html_text = get_html(url)
        except Exception as e:  # noqa: BLE001
            print(f"  warn fetch {url}: {e}")
            continue
        soup = BeautifulSoup(html_text, "lxml")
        title = strip_html(soup.title.string if soup.title and soup.title.string else "")
        found = set(FILE_EXT_RE.findall(html_text))
        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            abs_url = urljoin(url, href)
            if FILE_EXT_RE.fullmatch(abs_url) or re.search(
                r"\.(pdf|xlsx?|csv|zip|docx?|pptx?)(?:$|\?)", abs_url, re.I
            ):
                found.add(abs_url.split("#")[0])
        for file_url in found:
            rec = discovered.setdefault(
                file_url,
                {
                    "url": file_url,
                    "extension": Path(urlparse(file_url).path).suffix.lower().lstrip("."),
                    "source_pages": [],
                    "anchor_texts": [],
                },
            )
            if url not in rec["source_pages"]:
                rec["source_pages"].append(url)
            # capture nearby anchor text if any
            for a in soup.select(f'a[href="{file_url}"], a[href="{urlparse(file_url).path}"]'):
                txt = strip_html(a.get_text(" "))
                if txt and txt not in rec["anchor_texts"]:
                    rec["anchor_texts"].append(txt)
        if i % 10 == 0 or i == len(urls):
            print(f"  scanned pages for files: {i}/{len(urls)} (unique files={len(discovered)})")
        time.sleep(0.12)
    # attach page title loosely via first source
    for rec in discovered.values():
        rec["source_count"] = len(rec["source_pages"])
        rec["title_guess"] = (rec["anchor_texts"][0] if rec["anchor_texts"] else "") or Path(
            urlparse(rec["url"]).path
        ).name
    return list(discovered.values())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            flat = {}
            for k in fields:
                v = row.get(k)
                if isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                else:
                    flat[k] = v
            w.writerow(flat)


def build_report(
    content_items: list[dict],
    media_docs: list[dict],
    sitemap_entries: list[dict],
    discovered_files: list[dict],
    taxonomies: dict[str, list],
) -> str:
    by_type = Counter(i["type"] for i in content_items)
    mime_counts = Counter(m["mime_type"] for m in media_docs)
    ext_counts = Counter(f.get("extension") for f in discovered_files)
    recent = sorted(
        [i for i in content_items if i.get("date")],
        key=lambda x: x["date"],
        reverse=True,
    )[:25]

    lines = [
        "Pakistan Bureau of Statistics — Crawl Report",
        "اداره آمار پاکستان — گزارش خزش",
        "=" * 60,
        f"Source: {BASE}",
        f"Crawled at (UTC): {utc_now()}",
        "",
        "## Content counts / شمار محتوا",
    ]
    for k, v in sorted(by_type.items()):
        lines.append(f"- {k}: {v}")
    lines += [
        f"- sitemap URLs: {len(sitemap_entries)}",
        f"- media documents cataloged: {len(media_docs)}",
        f"- downloadable files discovered in HTML: {len(discovered_files)}",
        "",
        "## Media by MIME / رسانه بر اساس نوع",
    ]
    for k, v in mime_counts.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Discovered file extensions / پسوند فایل‌های کشف‌شده"]
    for k, v in ext_counts.most_common():
        lines.append(f"- .{k}: {v}")

    lines += ["", "## Taxonomies / رده‌بندی‌ها"]
    for name, items in taxonomies.items():
        lines.append(f"- {name}: {len(items)}")

    lines += ["", "## Latest content / تازه‌ترین مطالب"]
    for item in recent:
        lines.append(f"- [{item['date'][:10]}] {item['title']} — {item['link']}")

    # Key thematic pages
    keywords = {
        "census": ["census", "population"],
        "prices_inflation": ["price", "inflation", "cpi"],
        "trade": ["trade", "export", "import"],
        "labour": ["labour", "labor", "lfs"],
        "agriculture": ["agriculture", "crop", "mouza"],
        "national_accounts": ["national account", "gdp"],
        "pslm_hies": ["pslm", "hies"],
        "industry": ["industry", "qim", "manufactur"],
    }
    theme_hits: dict[str, list[str]] = defaultdict(list)
    for item in content_items:
        blob = f"{item['title']} {item['slug']} {item['excerpt']}".lower()
        for theme, keys in keywords.items():
            if any(k in blob for k in keys):
                theme_hits[theme].append(item["link"])

    lines += ["", "## Thematic index (heuristic) / نمایه موضوعی"]
    for theme, links in sorted(theme_hits.items()):
        uniq = sorted(set(links))
        lines.append(f"- {theme}: {len(uniq)} pages")
        for link in uniq[:8]:
            lines.append(f"  - {link}")

    lines += [
        "",
        "## Output files / فایل‌های خروجی",
        "- all_content.json / all_content.csv",
        "- media_documents.json / media_documents.csv",
        "- discovered_files.json / discovered_files.csv",
        "- sitemap_urls.csv",
        "- taxonomies.json",
        "- pbs_crawl.xlsx",
        "- report.txt (this file)",
        "",
        "Note: Binary files (PDF/Excel) are cataloged with public URLs;",
        "full binary download of thousands of media objects is intentionally",
        "not performed in this pass to keep the dataset portable.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    print(f"Starting PBS crawl at {started}")

    # 1) Content types
    raw_by_type: dict[str, list] = {}
    content_items: list[dict] = []
    for ct in CONTENT_TYPES:
        print(f"Fetching {ct}...")
        try:
            raw = fetch_collection(ct)
        except Exception as e:  # noqa: BLE001
            print(f"  failed {ct}: {e}")
            raw = []
        raw_by_type[ct] = raw
        for item in raw:
            content_items.append(normalize_content_item(item, ct))
        write_json(OUT / f"raw_{ct}.json", raw)

    # 2) Taxonomies
    taxonomies: dict[str, list] = {}
    for tax in ["categories", "tags", "product_cat", "product_tag", "doc_category"]:
        print(f"Fetching taxonomy {tax}...")
        try:
            taxonomies[tax] = fetch_collection(tax)
        except Exception as e:  # noqa: BLE001
            print(f"  failed {tax}: {e}")
            taxonomies[tax] = []
    write_json(OUT / "taxonomies.json", taxonomies)

    # 3) Media documents catalog
    media_docs: list[dict] = []
    seen_media_ids: set[int] = set()
    for mime in DOC_MIME_TYPES:
        print(f"Fetching media mime={mime}...")
        try:
            batch = fetch_media_by_mime(mime)
        except Exception as e:  # noqa: BLE001
            print(f"  failed media {mime}: {e}")
            batch = []
        for item in batch:
            mid = item.get("id")
            if mid in seen_media_ids:
                continue
            seen_media_ids.add(mid)
            media_docs.append(normalize_media(item))

    # 4) Sitemaps
    print("Fetching sitemaps...")
    sitemap_entries: list[dict] = []
    try:
        for sm in parse_sitemap_index():
            print(f"  sitemap: {sm}")
            sitemap_entries.extend(parse_sitemap_urls(sm))
            time.sleep(0.1)
    except Exception as e:  # noqa: BLE001
        print(f"  sitemap failed: {e}")

    # Deduplicate sitemap
    sm_map = {}
    for e in sitemap_entries:
        sm_map[e["url"]] = e
    sitemap_entries = list(sm_map.values())

    # 5) Discover files from key content URLs + sitemap page/product URLs
    crawl_urls = []
    for item in content_items:
        if item.get("link"):
            crawl_urls.append(item["link"])
    for e in sitemap_entries:
        u = e["url"]
        if any(
            x in u
            for x in (
                "/category/",
                "/tag/",
                "/author/",
                "/event_type/",
                "/event_tag/",
                "/product_cat/",
                "/product_tag/",
                "/doc_category/",
                "/cat_",
            )
        ):
            continue
        crawl_urls.append(u)
    # unique preserve order
    seen_u = set()
    uniq_urls = []
    for u in crawl_urls:
        if u not in seen_u:
            seen_u.add(u)
            uniq_urls.append(u)

    print(f"Discovering downloadable files from {len(uniq_urls)} pages...")
    discovered_files = discover_files_from_urls(uniq_urls)

    # Merge file links found in API content bodies
    discovered_map = {d["url"]: d for d in discovered_files}
    for item in content_items:
        for fu in item.get("file_links") or []:
            rec = discovered_map.setdefault(
                fu,
                {
                    "url": fu,
                    "extension": Path(urlparse(fu).path).suffix.lower().lstrip("."),
                    "source_pages": [],
                    "anchor_texts": [],
                    "source_count": 0,
                    "title_guess": Path(urlparse(fu).path).name,
                },
            )
            if item["link"] and item["link"] not in rec["source_pages"]:
                rec["source_pages"].append(item["link"])
            rec["source_count"] = len(rec["source_pages"])
    discovered_files = list(discovered_map.values())

    # 6) Persist outputs
    content_export = [
        {k: v for k, v in item.items() if k != "content_html"} for item in content_items
    ]
    # Keep full HTML separately for completeness
    write_json(OUT / "all_content_full.json", content_items)
    write_json(OUT / "all_content.json", content_export)
    write_csv(
        OUT / "all_content.csv",
        content_export,
        [
            "id",
            "type",
            "slug",
            "link",
            "status",
            "date",
            "modified",
            "title",
            "excerpt",
            "content_text",
            "file_links",
            "categories",
            "tags",
        ],
    )

    write_json(OUT / "media_documents.json", media_docs)
    write_csv(
        OUT / "media_documents.csv",
        media_docs,
        [
            "id",
            "date",
            "modified",
            "slug",
            "title",
            "mime_type",
            "media_type",
            "source_url",
            "link",
            "filesize",
            "width",
            "height",
            "alt_text",
        ],
    )

    write_json(OUT / "discovered_files.json", discovered_files)
    write_csv(
        OUT / "discovered_files.csv",
        discovered_files,
        ["url", "extension", "title_guess", "source_count", "source_pages", "anchor_texts"],
    )
    write_csv(OUT / "sitemap_urls.csv", sitemap_entries, ["url", "lastmod"])

    # Excel workbook
    with pd.ExcelWriter(OUT / "pbs_crawl.xlsx", engine="openpyxl") as xw:
        pd.DataFrame(content_export).drop(columns=["content_text"], errors="ignore").to_excel(
            xw, sheet_name="content_index", index=False
        )
        # content text can be huge; keep truncated sheet
        text_rows = []
        for item in content_export:
            text_rows.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "title": item["title"],
                    "link": item["link"],
                    "date": item["date"],
                    "content_text": (item.get("content_text") or "")[:30000],
                }
            )
        pd.DataFrame(text_rows).to_excel(xw, sheet_name="content_text", index=False)
        pd.DataFrame(media_docs).to_excel(xw, sheet_name="media_documents", index=False)
        pd.DataFrame(discovered_files).to_excel(xw, sheet_name="discovered_files", index=False)
        pd.DataFrame(sitemap_entries).to_excel(xw, sheet_name="sitemap", index=False)
        summary_rows = [
            {"metric": "crawled_at_utc", "value": started},
            {"metric": "finished_at_utc", "value": utc_now()},
            {"metric": "content_items", "value": len(content_items)},
            {"metric": "media_documents", "value": len(media_docs)},
            {"metric": "discovered_files", "value": len(discovered_files)},
            {"metric": "sitemap_urls", "value": len(sitemap_entries)},
        ]
        for k, v in Counter(i["type"] for i in content_items).items():
            summary_rows.append({"metric": f"content_{k}", "value": v})
        pd.DataFrame(summary_rows).to_excel(xw, sheet_name="summary", index=False)

    report = build_report(content_items, media_docs, sitemap_entries, discovered_files, taxonomies)
    (OUT / "report.txt").write_text(report, encoding="utf-8")

    meta = {
        "source": BASE,
        "started_at": started,
        "finished_at": utc_now(),
        "counts": {
            "content_items": len(content_items),
            "by_type": dict(Counter(i["type"] for i in content_items)),
            "media_documents": len(media_docs),
            "discovered_files": len(discovered_files),
            "sitemap_urls": len(sitemap_entries),
            "taxonomies": {k: len(v) for k, v in taxonomies.items()},
        },
        "outputs": sorted(p.name for p in OUT.iterdir() if p.is_file()),
    }
    write_json(OUT / "crawl_meta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"Done. Outputs in {OUT}")


if __name__ == "__main__":
    main()
