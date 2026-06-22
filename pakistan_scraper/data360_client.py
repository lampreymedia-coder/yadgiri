"""
کلاینت کوچک برای API رسمی World Bank Data360.

نکته آموزشی:
صفحه https://data360.worldbank.org/en/economy/PAK?tab=Prosperity
داده‌ها را با JavaScript از endpointهای زیر می‌گیرد. ما به جای scrape کردن HTML
از همین endpointهای JSON استفاده می‌کنیم؛ این روش پایدارتر و تمیزتر است.
"""

from __future__ import annotations

import json
from typing import Any

import requests


BASE_URL = "https://data360api.worldbank.org/data360/portal/v1"
DEFAULT_DATABASE_ID = "WB_WDI"
DEFAULT_COUNTRY = "PAK"
DEFAULT_START_YEAR = 2010
DEFAULT_END_YEAR = 2026

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; pakistan-data360-scraper/1.0)",
    "Origin": "https://data360.worldbank.org",
    "Referer": "https://data360.worldbank.org/en/economy/PAK?tab=Prosperity",
}


def world_bank_code_to_data360_id(code: str) -> str:
    """کد World Bank مثل NY.GDP.PCAP.CD را به شناسه Data360 تبدیل می‌کند."""
    return f"{DEFAULT_DATABASE_ID}_{code.replace('.', '_')}"


def get_session() -> requests.Session:
    """یک session مشترک برای reuse کردن connectionها می‌سازد."""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def _json_response(response: requests.Response) -> Any:
    """
    بعضی پاسخ‌های Data360 با BOM شروع می‌شوند؛ قبل از json.loads آن را حذف می‌کنیم.
    """
    response.raise_for_status()
    return json.loads(response.text.lstrip("\ufeff"))


def fetch_indicator_data(
    indicator_id: str,
    *,
    database_id: str = DEFAULT_DATABASE_ID,
    country: str = DEFAULT_COUNTRY,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """
    داده خام یک شاخص را از Data360 می‌گیرد و فقط REF_AREA کشور موردنظر را درخواست می‌کند.
    """
    session = session or get_session()
    filters = json.dumps(
        [{"filterColumn": "REF_AREA", "filterValue": country}],
        separators=(",", ":"),
    )
    response = session.get(
        f"{BASE_URL}/data",
        params={
            "database_id": database_id,
            "indicator_id": indicator_id,
            "filters": filters,
        },
        timeout=60,
    )
    data = _json_response(response)
    return data if isinstance(data, list) else []


def _row_score(row: dict[str, Any]) -> int:
    """
    اگر برای یک شاخص چند سری وجود داشته باشد، سری سالانه و کل/نامشخص را ترجیح می‌دهیم.
    """
    score = 0
    if row.get("FREQ") == "A":
        score += 20
    if row.get("REF_AREA") == DEFAULT_COUNTRY:
        score += 20

    for field in ("SEX", "AGE", "URBANISATION"):
        if row.get(field) in ("_T", "_Z", None):
            score += 3
        else:
            score -= 3

    for field in ("COMP_BREAKDOWN_1", "COMP_BREAKDOWN_2", "COMP_BREAKDOWN_3"):
        if row.get(field) in ("_T", "_Z", None):
            score += 2
        else:
            score -= 2

    y_axis = row.get("data", {}).get("yAxis") or []
    score += sum(1 for value in y_axis if value not in (None, "", "NaN"))
    return score


def select_best_series(rows: list[dict[str, Any]], country: str = DEFAULT_COUNTRY) -> dict[str, Any] | None:
    """از بین ردیف‌های برگشتی، سری مناسب کشور را انتخاب می‌کند."""
    country_rows = [row for row in rows if row.get("REF_AREA") == country]
    candidates = country_rows or rows
    if not candidates:
        return None
    return max(candidates, key=_row_score)


def normalize_series(
    row: dict[str, Any] | None,
    *,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
) -> dict[int, float | None]:
    """سری خام Data360 را به دیکشنری کامل سال‌ها تبدیل می‌کند."""
    values: dict[int, float | None] = {year: None for year in range(start_year, end_year + 1)}
    if not row:
        return values

    x_axis = row.get("data", {}).get("xAxis") or []
    y_axis = row.get("data", {}).get("yAxis") or []
    for year_label, raw_value in zip(x_axis, y_axis):
        try:
            year = int(str(year_label)[:4])
        except (TypeError, ValueError):
            continue

        if start_year <= year <= end_year:
            values[year] = _to_float_or_none(raw_value)

    return values


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "NaN"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_admin_metadata(
    indicator_ids: list[str],
    *,
    session: requests.Session | None = None,
    chunk_size: int = 80,
) -> dict[str, dict[str, Any]]:
    """metadata و topicهای Data360 را برای چند شاخص می‌گیرد."""
    session = session or get_session()
    metadata: dict[str, dict[str, Any]] = {}

    for start in range(0, len(indicator_ids), chunk_size):
        chunk = indicator_ids[start : start + chunk_size]
        response = session.post(
            f"{BASE_URL}/adminmetadata",
            json={"type": "indicator", "ids": chunk},
            timeout=60,
        )
        payload = _json_response(response)
        for item in payload.get("data", []):
            metadata[item.get("id")] = item.get("admin_metadata", {})

    return metadata


def extract_data360_topics(admin_metadata: dict[str, Any]) -> tuple[str, str]:
    """topic labels و ids را از metadata یک شاخص استخراج می‌کند."""
    topics = admin_metadata.get("data360", {}).get("topics", [])
    labels = []
    ids = []
    for topic in topics:
        label = topic.get("label") or topic.get("name")
        topic_id = topic.get("id")
        if label:
            labels.append(label)
        if topic_id:
            ids.append(topic_id)
    return " > ".join(labels), " > ".join(ids)
