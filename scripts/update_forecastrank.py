#!/usr/bin/env python3
"""
ForecastRank V2.0 Phase 1 updater.

Goals:
1. Preserve the existing model-verification history.
2. Capture NEW Day-1 numerical-model forecasts at approximately 4:00 p.m.
   Toronto local time.
3. Capture Environment and Climate Change Canada's official PUBLIC city
   forecast for tomorrow's maximum temperature from MSC Open Data.
4. Verify model forecasts as before.
5. Verify public forecasts into separate public-history files so the current
   V1.2 website is not changed until the new public-forecast pipeline is proven.
6. Provide a safe manual validation mode that reads the ECCC public forecast
   but does not modify any repository data.

Day-1 V2 definition:
    The published/model maximum-temperature forecast for the following local
    calendar day, captured during the standardized 4:00 p.m. local-time window.

No API key is required for the configured sources.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPOSITORY_ROOT / "data"

ARCHIVE_PATH = DATA_DIR / "forecast_archive.json"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_JSON_PATH = DATA_DIR / "history.json"
HISTORY_CSV_PATH = DATA_DIR / "history.csv"

PUBLIC_HISTORY_JSON_PATH = DATA_DIR / "public_history.json"
PUBLIC_HISTORY_CSV_PATH = DATA_DIR / "public_history.csv"

TORONTO_TZ = ZoneInfo("America/Toronto")

LOCATION = {
    "name": "Toronto Pearson International Airport",
    "city": "Toronto",
    "province": "Ontario",
    "country": "Canada",
    "climate_identifier": "6158731",
    "station_code": "YYZ",
    "latitude": 43.677,
    "longitude": -79.631,
}

# Environment Canada public city forecast location.
ECCC_PUBLIC_SITE = {
    "site_code": "s0000458",
    "province_code": "ON",
    "display_name": "Toronto",
}

METHODOLOGY_V2 = "day1_1600_local_v2"
CAPTURE_TARGET_LOCAL_TIME = "16:00"
CAPTURE_WINDOW_START_MINUTES = 16 * 60
CAPTURE_WINDOW_END_MINUTES = 17 * 60  # exclusive; up to 16:59:59

USER_AGENT = (
    "ForecastRank/2.0 "
    "(Day-1 maximum-temperature forecast verification; "
    "contact via ForecastRank GitHub repository)"
)


@dataclass(frozen=True)
class Provider:
    provider_id: str
    agency: str
    model: str
    endpoint: str


MODEL_PROVIDERS = (
    Provider(
        "open_meteo_best_match",
        "Open-Meteo",
        "Best Match",
        "https://api.open-meteo.com/v1/forecast",
    ),
    Provider(
        "eccc_gem",
        "Environment and Climate Change Canada",
        "GEM Seamless",
        "https://api.open-meteo.com/v1/gem",
    ),
    Provider(
        "noaa_gfs",
        "NOAA",
        "GFS",
        "https://api.open-meteo.com/v1/gfs",
    ),
    Provider(
        "ecmwf_ifs",
        "ECMWF",
        "IFS",
        "https://api.open-meteo.com/v1/ecmwf",
    ),
    Provider(
        "dwd_icon",
        "Deutscher Wetterdienst",
        "ICON Global",
        "https://api.open-meteo.com/v1/dwd-icon",
    ),
    Provider(
        "meteofrance_arpege",
        "Météo-France",
        "ARPEGE World",
        "https://api.open-meteo.com/v1/meteofrance",
    ),
    Provider(
        "jma_gsm",
        "Japan Meteorological Agency",
        "GSM",
        "https://api.open-meteo.com/v1/jma",
    ),
)


def log(message: str) -> None:
    timestamp = datetime.now(TORONTO_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{timestamp}] {message}", flush=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Could not read {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def fetch_text(url: str, *, retries: int = 3, timeout: int = 35) -> str:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/xml, text/xml, */*",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                wait_seconds = attempt * 3
                log(
                    f"Request failed (attempt {attempt}/{retries}); "
                    f"retrying in {wait_seconds}s: {exc}"
                )
                time.sleep(wait_seconds)

    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def fetch_json(url: str, *, retries: int = 3, timeout: int = 35) -> dict[str, Any]:
    raw = fetch_text(url, retries=retries, timeout=timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Response from {url} was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Response from {url} was not a JSON object")
    return payload


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(part.strip() for part in element.itertext() if part.strip())


def find_descendant(parent: ET.Element, wanted_name: str) -> ET.Element | None:
    wanted_name = wanted_name.lower()
    for element in parent.iter():
        if local_name(element.tag).lower() == wanted_name:
            return element
    return None


def parse_datetime_element(element: ET.Element | None) -> str | None:
    if element is None:
        return None

    values: dict[str, str] = {}
    for child in list(element):
        name = local_name(child.tag).lower()
        text = element_text(child)
        if text:
            values[name] = text

    required = ("year", "month", "day", "hour")
    if not all(name in values for name in required):
        return None

    try:
        year = int(values["year"])
        month = int(values["month"])
        day = int(values["day"])
        hour = int(values["hour"])
        minute = int(values.get("minute", "0"))
        second = int(float(values.get("second", "0")))
    except ValueError:
        return None

    offset_raw = element.attrib.get("UTCOffset", element.attrib.get("utcOffset", "0"))
    try:
        offset_hours = float(offset_raw)
    except (TypeError, ValueError):
        offset_hours = 0.0

    offset_minutes = int(round(offset_hours * 60))
    tz = timezone(timedelta(minutes=offset_minutes))

    try:
        parsed = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    except ValueError:
        return None

    # Normalize Environment Canada's forecast issue timestamp to the
    # ForecastRank location's local timezone. The source XML can express the
    # issue time in UTC; storing it in America/Toronto makes the audit record
    # immediately understandable and automatically handles EDT/EST.
    parsed_local = parsed.astimezone(TORONTO_TZ)
    return parsed_local.isoformat(timespec="seconds")


def forecast_url(provider: Provider) -> str:
    params = {
        "latitude": LOCATION["latitude"],
        "longitude": LOCATION["longitude"],
        "daily": "temperature_2m_max",
        "temperature_unit": "celsius",
        "timezone": "America/Toronto",
        "forecast_days": 3,
    }
    return f"{provider.endpoint}?{urlencode(params)}"


def fetch_model_forecast(provider: Provider, target_date: date) -> float:
    payload = fetch_json(forecast_url(provider))
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise RuntimeError("Response did not contain a daily object")

    dates = daily.get("time")
    values = daily.get("temperature_2m_max")
    if not isinstance(dates, list) or not isinstance(values, list):
        raise RuntimeError(
            "Response did not contain daily time and temperature_2m_max lists"
        )

    target_text = target_date.isoformat()
    try:
        index = dates.index(target_text)
    except ValueError as exc:
        raise RuntimeError(
            f"Target date {target_text} was absent from the response"
        ) from exc

    value = finite_number(values[index] if index < len(values) else None)
    if value is None:
        raise RuntimeError(
            f"No finite maximum temperature was returned for {target_text}"
        )

    return round(value, 1)


def current_eccc_citypage_directory() -> str:
    utc_hour = datetime.now(timezone.utc).strftime("%H")
    province = ECCC_PUBLIC_SITE["province_code"]
    return f"https://dd.weather.gc.ca/today/citypage_weather/{province}/{utc_hour}/"


def find_latest_eccc_citypage_file() -> str:
    directory_url = current_eccc_citypage_directory()
    listing = fetch_text(directory_url)

    site_code = re.escape(ECCC_PUBLIC_SITE["site_code"])
    pattern = re.compile(
        rf'href=["\']([^"\']*_MSC_CitypageWeather_{site_code}_en\.xml)["\']',
        re.IGNORECASE,
    )

    candidates = [html.unescape(match) for match in pattern.findall(listing)]
    if not candidates:
        # Some directory indexes can be rendered without quoted href text in
        # unusual ways. Fall back to scanning filenames directly.
        filename_pattern = re.compile(
            rf'(\d{{8}}T\d{{6}}\.\d+Z_MSC_CitypageWeather_{site_code}_en\.xml)',
            re.IGNORECASE,
        )
        candidates = filename_pattern.findall(listing)

    if not candidates:
        raise RuntimeError(
            f"No current ECCC citypage XML file was found for "
            f"{ECCC_PUBLIC_SITE['display_name']} ({ECCC_PUBLIC_SITE['site_code']}) "
            f"in {directory_url}"
        )

    latest_filename = sorted(set(candidates))[-1]
    return urljoin(directory_url, latest_filename)


def fetch_eccc_public_forecast(target_date: date) -> dict[str, Any]:
    source_url = find_latest_eccc_citypage_file()
    xml_text = fetch_text(source_url)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError("ECCC citypage response was not valid XML") from exc

    issue_time: str | None = None
    for element in root.iter():
        if local_name(element.tag).lower() != "datetime":
            continue
        name = str(element.attrib.get("name", "")).lower()
        if name == "forecastissue":
            issue_time = parse_datetime_element(element)
            break

    target_weekday = target_date.strftime("%A").lower()
    forecast_candidates: list[dict[str, Any]] = []

    for forecast in root.iter():
        if local_name(forecast.tag).lower() != "forecast":
            continue

        period = find_descendant(forecast, "period")
        if period is None:
            continue

        period_name = (
            period.attrib.get("textForecastName")
            or period.attrib.get("textforecastname")
            or element_text(period)
        ).strip()

        high_value: float | None = None
        for element in forecast.iter():
            if local_name(element.tag).lower() != "temperature":
                continue
            temp_class = str(element.attrib.get("class", "")).lower()
            if temp_class != "high":
                continue
            value = finite_number(element_text(element))
            if value is not None:
                high_value = round(value, 1)
                break

        if high_value is not None:
            forecast_candidates.append(
                {
                    "period_name": period_name,
                    "forecast_high_c": high_value,
                }
            )

    if not forecast_candidates:
        raise RuntimeError(
            "No daytime high-temperature forecast was found in the ECCC citypage XML"
        )

    selected = None
    for candidate in forecast_candidates:
        if candidate["period_name"].lower().startswith(target_weekday):
            selected = candidate
            break

    # At the 4 p.m. capture, the first remaining "high" period should normally
    # be tomorrow. This fallback is retained so an unexpected period label does
    # not cause silent loss of the entire daily capture.
    if selected is None:
        selected = forecast_candidates[0]
        log(
            "WARNING: ECCC target weekday label was not matched exactly; "
            f"using first available high period '{selected['period_name']}'."
        )

    return {
        "provider_id": "eccc_public",
        "provider_type": "public_forecast",
        "agency": "Environment and Climate Change Canada",
        "product": "Official City Forecast",
        "forecast_location": ECCC_PUBLIC_SITE["display_name"],
        "site_code": ECCC_PUBLIC_SITE["site_code"],
        "valid_date": target_date.isoformat(),
        "period_name": selected["period_name"],
        "forecast_high_c": selected["forecast_high_c"],
        "forecast_issue_time": issue_time,
        "source_url": source_url,
    }


def is_capture_window(now_local: datetime) -> bool:
    local_minutes = now_local.hour * 60 + now_local.minute
    return CAPTURE_WINDOW_START_MINUTES <= local_minutes < CAPTURE_WINDOW_END_MINUTES


def prepare_v2_capture_record(
    archive: dict[str, Any],
    target_date: date,
    now_local: datetime,
) -> dict[str, Any]:
    target_key = target_date.isoformat()
    forecasts = archive.setdefault("forecasts", {})
    existing = forecasts.get(target_key)

    if (
        isinstance(existing, dict)
        and existing.get("capture_methodology") == METHODOLOGY_V2
    ):
        return existing

    legacy_capture = None
    if isinstance(existing, dict) and existing:
        legacy_capture = {
            "captured_at": existing.get("captured_at"),
            "forecast_capture_date": existing.get("forecast_capture_date"),
            "lead_definition": existing.get("lead_definition"),
            "providers": existing.get("providers", []),
            "unavailable": existing.get("unavailable", []),
        }
        log(
            f"Transitioning {target_key} from the previous capture methodology "
            "to the V2 4:00 p.m. methodology. The earlier capture is preserved "
            "inside legacy_capture."
        )

    record = {
        "target_date": target_key,
        "forecast_capture_date": now_local.date().isoformat(),
        "captured_at": now_local.isoformat(timespec="seconds"),
        "lead_definition": (
            "Following local calendar day (Day-1), standardized 4:00 p.m. "
            "local-time capture"
        ),
        "capture_methodology": METHODOLOGY_V2,
        "capture_target_local_time": CAPTURE_TARGET_LOCAL_TIME,
        "providers": [],
        "unavailable": [],
        "public_forecasts": [],
        "public_unavailable": [],
    }
    if legacy_capture is not None:
        record["legacy_capture"] = legacy_capture

    forecasts[target_key] = record
    return record


def capture_models_into_record(
    record: dict[str, Any],
    target_date: date,
    now_local: datetime,
) -> None:
    existing_ids = {
        item.get("provider_id")
        for item in record.get("providers", [])
        if isinstance(item, dict)
    }

    unavailable_by_id = {
        item.get("provider_id"): item
        for item in record.get("unavailable", [])
        if isinstance(item, dict)
    }

    for provider in MODEL_PROVIDERS:
        if provider.provider_id in existing_ids:
            continue

        try:
            forecast_high = fetch_model_forecast(provider, target_date)
            record.setdefault("providers", []).append(
                {
                    "provider_id": provider.provider_id,
                    "provider_type": "numerical_model",
                    "agency": provider.agency,
                    "model": provider.model,
                    "forecast_high_c": forecast_high,
                    "captured_at": now_local.isoformat(timespec="seconds"),
                }
            )
            unavailable_by_id.pop(provider.provider_id, None)
            log(
                f"Captured model: {provider.agency} {provider.model}: "
                f"{forecast_high:.1f}°C"
            )
        except Exception as exc:
            unavailable_by_id[provider.provider_id] = {
                "provider_id": provider.provider_id,
                "agency": provider.agency,
                "model": provider.model,
                "reason": str(exc),
                "last_attempt_at": now_local.isoformat(timespec="seconds"),
            }
            log(f"Model unavailable: {provider.agency} {provider.model}: {exc}")

    record["unavailable"] = list(unavailable_by_id.values())


def capture_eccc_public_into_record(
    record: dict[str, Any],
    target_date: date,
    now_local: datetime,
) -> None:
    existing_ids = {
        item.get("provider_id")
        for item in record.get("public_forecasts", [])
        if isinstance(item, dict)
    }
    if "eccc_public" in existing_ids:
        return

    try:
        public = fetch_eccc_public_forecast(target_date)
        public["captured_at"] = now_local.isoformat(timespec="seconds")
        record.setdefault("public_forecasts", []).append(public)
        record["public_unavailable"] = [
            item
            for item in record.get("public_unavailable", [])
            if item.get("provider_id") != "eccc_public"
        ]
        log(
            "Captured PUBLIC forecast: Environment and Climate Change Canada "
            f"{public['period_name']} high {public['forecast_high_c']:.1f}°C"
        )
        log(f"ECCC public source file: {public['source_url']}")
        if public.get("forecast_issue_time"):
            log(f"ECCC forecast issue time: {public['forecast_issue_time']}")
    except Exception as exc:
        other = [
            item
            for item in record.get("public_unavailable", [])
            if item.get("provider_id") != "eccc_public"
        ]
        other.append(
            {
                "provider_id": "eccc_public",
                "agency": "Environment and Climate Change Canada",
                "product": "Official City Forecast",
                "reason": str(exc),
                "last_attempt_at": now_local.isoformat(timespec="seconds"),
            }
        )
        record["public_unavailable"] = other
        log(f"ECCC PUBLIC forecast unavailable: {exc}")


def capture_v2_forecasts(
    archive: dict[str, Any],
    now_local: datetime,
) -> dict[str, Any]:
    if not is_capture_window(now_local):
        raise RuntimeError(
            "V2 capture refused because the current Toronto local time is "
            f"{now_local.strftime('%H:%M')}, outside the standardized "
            "16:00-16:59 capture window."
        )

    target_date = now_local.date() + timedelta(days=1)
    record = prepare_v2_capture_record(archive, target_date, now_local)

    capture_models_into_record(record, target_date, now_local)
    capture_eccc_public_into_record(record, target_date, now_local)

    archive["last_capture_at"] = now_local.isoformat(timespec="seconds")
    archive["current_capture_methodology"] = METHODOLOGY_V2
    archive["capture_target_local_time"] = CAPTURE_TARGET_LOCAL_TIME

    return record


def fetch_eccc_observed_max(target_date: date) -> float | None:
    climate_id = LOCATION["climate_identifier"]
    item_id = (
        f"{climate_id}.{target_date.year}.{target_date.month}.{target_date.day}"
    )
    item_url = (
        "https://api.weather.gc.ca/collections/climate-daily/items/"
        f"{item_id}?f=json&lang=en"
    )

    try:
        payload = fetch_json(item_url, retries=2)
    except Exception as exc:
        log(f"ECCC daily observation is not available for {target_date}: {exc}")
        return None

    properties = payload.get("properties")
    if not isinstance(properties, dict):
        features = payload.get("features")
        if isinstance(features, list) and features:
            first = features[0]
            if isinstance(first, dict):
                properties = first.get("properties")

    if not isinstance(properties, dict):
        log(f"ECCC response for {target_date} did not include properties.")
        return None

    value = finite_number(properties.get("MAX_TEMPERATURE"))
    if value is None:
        log(f"ECCC MAX_TEMPERATURE is missing for {target_date}.")
        return None

    return round(value, 1)


def rating_for_error(absolute_error: float) -> str:
    if absolute_error <= 0.5:
        return "Excellent"
    if absolute_error <= 1.0:
        return "Very good"
    if absolute_error <= 2.0:
        return "Good"
    if absolute_error <= 3.0:
        return "Fair"
    return "Poor"


def assign_ranks(results: list[dict[str, Any]]) -> None:
    results.sort(
        key=lambda row: (
            row["absolute_error_c"],
            row.get("agency", "").casefold(),
            (row.get("model") or row.get("product") or "").casefold(),
        )
    )

    previous_error: float | None = None
    previous_rank = 0

    for index, row in enumerate(results, start=1):
        current_error = row["absolute_error_c"]
        if previous_error is not None and math.isclose(
            current_error, previous_error, abs_tol=0.0001
        ):
            row["rank"] = previous_rank
        else:
            row["rank"] = index
            previous_rank = index
            previous_error = current_error


def build_model_verification(
    forecast_record: dict[str, Any],
    actual_high_c: float,
    published_at: datetime,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for forecast in forecast_record.get("providers", []):
        forecast_high = finite_number(forecast.get("forecast_high_c"))
        if forecast_high is None:
            continue

        signed_error = round(forecast_high - actual_high_c, 1)
        absolute_error = round(abs(signed_error), 1)

        results.append(
            {
                "provider_id": forecast["provider_id"],
                "agency": forecast["agency"],
                "model": forecast["model"],
                "forecast_high_c": round(forecast_high, 1),
                "error_c": signed_error,
                "absolute_error_c": absolute_error,
                "rating": rating_for_error(absolute_error),
            }
        )

    assign_ranks(results)

    unavailable_models = [
        f'{item.get("agency", "Unknown")} — {item.get("model", "Unknown")}'
        for item in forecast_record.get("unavailable", [])
    ]

    return {
        "status": "ready",
        "is_demo": False,
        "location": LOCATION,
        "verification_date": forecast_record["target_date"],
        "actual_high_c": actual_high_c,
        "forecast_capture_date": forecast_record.get("forecast_capture_date"),
        "forecast_captured_at": forecast_record.get("captured_at"),
        "capture_methodology": forecast_record.get("capture_methodology"),
        "capture_target_local_time": forecast_record.get(
            "capture_target_local_time"
        ),
        "published_at": published_at.isoformat(timespec="seconds"),
        "results": results,
        "unavailable_models": unavailable_models,
    }


def build_public_verification(
    forecast_record: dict[str, Any],
    actual_high_c: float,
    published_at: datetime,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    for forecast in forecast_record.get("public_forecasts", []):
        forecast_high = finite_number(forecast.get("forecast_high_c"))
        if forecast_high is None:
            continue

        signed_error = round(forecast_high - actual_high_c, 1)
        absolute_error = round(abs(signed_error), 1)

        results.append(
            {
                "provider_id": forecast.get("provider_id"),
                "provider_type": "public_forecast",
                "agency": forecast.get("agency"),
                "product": forecast.get("product"),
                "forecast_location": forecast.get("forecast_location"),
                "period_name": forecast.get("period_name"),
                "forecast_high_c": round(forecast_high, 1),
                "error_c": signed_error,
                "absolute_error_c": absolute_error,
                "rating": rating_for_error(absolute_error),
                "forecast_issue_time": forecast.get("forecast_issue_time"),
                "captured_at": forecast.get("captured_at"),
                "source_url": forecast.get("source_url"),
            }
        )

    assign_ranks(results)

    return {
        "status": "ready",
        "location": LOCATION,
        "verification_date": forecast_record["target_date"],
        "actual_high_c": actual_high_c,
        "forecast_capture_date": forecast_record.get("forecast_capture_date"),
        "forecast_captured_at": forecast_record.get("captured_at"),
        "capture_methodology": forecast_record.get("capture_methodology"),
        "capture_target_local_time": forecast_record.get(
            "capture_target_local_time"
        ),
        "published_at": published_at.isoformat(timespec="seconds"),
        "results": results,
        "unavailable_public_forecasts": forecast_record.get(
            "public_unavailable", []
        ),
    }


def verification_exists(records: list[dict[str, Any]], verification_date: str) -> bool:
    return any(item.get("verification_date") == verification_date for item in records)


def verify_model_pending_dates(
    archive: dict[str, Any],
    history: list[dict[str, Any]],
    now_local: datetime,
    lookback_days: int = 10,
) -> list[dict[str, Any]]:
    verified_now: list[dict[str, Any]] = []
    forecasts = archive.get("forecasts", {})

    for days_back in range(1, lookback_days + 1):
        candidate = now_local.date() - timedelta(days=days_back)
        key = candidate.isoformat()
        record = forecasts.get(key)

        if not isinstance(record, dict):
            continue
        if verification_exists(history, key):
            continue
        if not record.get("providers"):
            continue

        actual = fetch_eccc_observed_max(candidate)
        if actual is None:
            continue

        verification = build_model_verification(record, actual, now_local)
        history.append(verification)
        verified_now.append(verification)
        log(
            f"Verified MODELS for {key}: observed maximum {actual:.1f}°C "
            f"against {len(verification['results'])} forecasts."
        )

    history.sort(key=lambda item: item.get("verification_date", ""))
    return verified_now


def verify_public_pending_dates(
    archive: dict[str, Any],
    public_history: list[dict[str, Any]],
    now_local: datetime,
    lookback_days: int = 10,
) -> list[dict[str, Any]]:
    verified_now: list[dict[str, Any]] = []
    forecasts = archive.get("forecasts", {})

    for days_back in range(1, lookback_days + 1):
        candidate = now_local.date() - timedelta(days=days_back)
        key = candidate.isoformat()
        record = forecasts.get(key)

        if not isinstance(record, dict):
            continue
        if verification_exists(public_history, key):
            continue
        if not record.get("public_forecasts"):
            continue

        actual = fetch_eccc_observed_max(candidate)
        if actual is None:
            continue

        verification = build_public_verification(record, actual, now_local)
        public_history.append(verification)
        verified_now.append(verification)
        log(
            f"Verified PUBLIC forecasts for {key}: observed maximum "
            f"{actual:.1f}°C against {len(verification['results'])} forecasts."
        )

    public_history.sort(key=lambda item: item.get("verification_date", ""))
    return verified_now


def write_model_history_csv(history: list[dict[str, Any]]) -> None:
    columns = [
        "verification_date",
        "location",
        "station_code",
        "actual_high_c",
        "provider_id",
        "agency",
        "model",
        "forecast_high_c",
        "error_c",
        "absolute_error_c",
        "rating",
        "rank",
        "forecast_captured_at",
        "capture_methodology",
        "published_at",
    ]

    temporary = HISTORY_CSV_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        for verification in history:
            for result in verification.get("results", []):
                writer.writerow(
                    {
                        "verification_date": verification.get("verification_date"),
                        "location": verification.get("location", {}).get("name"),
                        "station_code": verification.get("location", {}).get(
                            "station_code"
                        ),
                        "actual_high_c": verification.get("actual_high_c"),
                        "provider_id": result.get("provider_id"),
                        "agency": result.get("agency"),
                        "model": result.get("model"),
                        "forecast_high_c": result.get("forecast_high_c"),
                        "error_c": result.get("error_c"),
                        "absolute_error_c": result.get("absolute_error_c"),
                        "rating": result.get("rating"),
                        "rank": result.get("rank"),
                        "forecast_captured_at": verification.get(
                            "forecast_captured_at"
                        ),
                        "capture_methodology": verification.get(
                            "capture_methodology"
                        ),
                        "published_at": verification.get("published_at"),
                    }
                )

    temporary.replace(HISTORY_CSV_PATH)


def write_public_history_csv(public_history: list[dict[str, Any]]) -> None:
    columns = [
        "verification_date",
        "location",
        "station_code",
        "actual_high_c",
        "provider_id",
        "agency",
        "product",
        "forecast_location",
        "period_name",
        "forecast_high_c",
        "error_c",
        "absolute_error_c",
        "rating",
        "rank",
        "forecast_issue_time",
        "captured_at",
        "capture_methodology",
        "source_url",
        "published_at",
    ]

    temporary = PUBLIC_HISTORY_CSV_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()

        for verification in public_history:
            for result in verification.get("results", []):
                writer.writerow(
                    {
                        "verification_date": verification.get("verification_date"),
                        "location": verification.get("location", {}).get("name"),
                        "station_code": verification.get("location", {}).get(
                            "station_code"
                        ),
                        "actual_high_c": verification.get("actual_high_c"),
                        "provider_id": result.get("provider_id"),
                        "agency": result.get("agency"),
                        "product": result.get("product"),
                        "forecast_location": result.get("forecast_location"),
                        "period_name": result.get("period_name"),
                        "forecast_high_c": result.get("forecast_high_c"),
                        "error_c": result.get("error_c"),
                        "absolute_error_c": result.get("absolute_error_c"),
                        "rating": result.get("rating"),
                        "rank": result.get("rank"),
                        "forecast_issue_time": result.get("forecast_issue_time"),
                        "captured_at": result.get("captured_at"),
                        "capture_methodology": verification.get(
                            "capture_methodology"
                        ),
                        "source_url": result.get("source_url"),
                        "published_at": verification.get("published_at"),
                    }
                )

    temporary.replace(PUBLIC_HISTORY_CSV_PATH)


def run_validation(now_local: datetime) -> int:
    target_date = now_local.date() + timedelta(days=1)
    log(
        "VALIDATION MODE: reading Environment Canada's public Toronto forecast. "
        "No ForecastRank data files will be changed."
    )
    public = fetch_eccc_public_forecast(target_date)

    log("VALIDATION PASSED.")
    log(f"Target date: {target_date.isoformat()}")
    log(f"Forecast period: {public['period_name']}")
    log(f"Published maximum: {public['forecast_high_c']:.1f}°C")
    issue_time = public.get("forecast_issue_time")
    if issue_time:
        try:
            issue_dt = datetime.fromisoformat(issue_time)
            readable_issue = issue_dt.strftime("%Y-%m-%d %-I:%M %p %Z")
        except (TypeError, ValueError):
            readable_issue = issue_time
    else:
        readable_issue = "not parsed"
    log(f"Forecast issue time: {readable_issue}")
    log(f"Source file: {public['source_url']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("capture-4pm", "verify-only", "validate-public-source"),
        default="capture-4pm",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_local = datetime.now(TORONTO_TZ).replace(microsecond=0)

    if args.mode == "validate-public-source":
        return run_validation(now_local)

    archive = load_json(
        ARCHIVE_PATH,
        {
            "schema_version": 1,
            "location": LOCATION,
            "definition": (
                "Day-1 means the following local calendar day's maximum "
                "temperature, captured once daily."
            ),
            "forecasts": {},
        },
    )
    history = load_json(HISTORY_JSON_PATH, [])
    public_history = load_json(PUBLIC_HISTORY_JSON_PATH, [])

    if not isinstance(archive, dict):
        raise RuntimeError("forecast_archive.json must contain a JSON object")
    if not isinstance(history, list):
        raise RuntimeError("history.json must contain a JSON list")
    if not isinstance(public_history, list):
        raise RuntimeError("public_history.json must contain a JSON list")

    archive["location"] = LOCATION

    log(f"Beginning ForecastRank V2.0 Phase 1 run in mode: {args.mode}")

    capture_record = None
    if args.mode == "capture-4pm":
        capture_record = capture_v2_forecasts(archive, now_local)

    verified_models = verify_model_pending_dates(archive, history, now_local)
    verified_public = verify_public_pending_dates(
        archive, public_history, now_local
    )

    write_json(ARCHIVE_PATH, archive)
    write_json(HISTORY_JSON_PATH, history)
    write_model_history_csv(history)
    write_json(PUBLIC_HISTORY_JSON_PATH, public_history)
    write_public_history_csv(public_history)

    if verified_models:
        latest = max(
            verified_models,
            key=lambda item: item.get("verification_date", ""),
        )
        write_json(LATEST_PATH, latest)
        log(f"Published latest MODEL leaderboard for {latest['verification_date']}.")
    elif history:
        latest = max(
            history,
            key=lambda item: item.get("verification_date", ""),
        )
        write_json(LATEST_PATH, latest)
        log(
            f"No new model verification; retained leaderboard for "
            f"{latest['verification_date']}."
        )

    if capture_record is not None:
        log(
            f"4 p.m. capture status for {capture_record['target_date']}: "
            f"{len(capture_record.get('providers', []))} numerical models; "
            f"{len(capture_record.get('public_forecasts', []))} public forecast(s)."
        )
        if capture_record.get("unavailable"):
            log(
                f"Models still unavailable: "
                f"{len(capture_record['unavailable'])}"
            )
        if capture_record.get("public_unavailable"):
            log(
                f"Public forecasts still unavailable: "
                f"{len(capture_record['public_unavailable'])}"
            )

    if verified_public:
        newest_public = max(
            verified_public,
            key=lambda item: item.get("verification_date", ""),
        )
        log(
            f"New PUBLIC verification stored for "
            f"{newest_public['verification_date']}."
        )

    log("ForecastRank V2.0 Phase 1 run completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FATAL: {exc}")
        raise
