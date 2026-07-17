#!/usr/bin/env python3
"""
ForecastRank daily updater.

Each run performs two jobs:

1. Capture maximum-temperature forecasts for the next Toronto calendar day.
2. Verify previously captured forecasts when the official ECCC daily maximum
   becomes available.

No API key is required for the configured non-commercial data sources.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPOSITORY_ROOT / "data"
ARCHIVE_PATH = DATA_DIR / "forecast_archive.json"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_JSON_PATH = DATA_DIR / "history.json"
HISTORY_CSV_PATH = DATA_DIR / "history.csv"

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

USER_AGENT = (
    "ForecastRank/1.0 "
    "(Day-1 maximum-temperature verification; public educational project)"
)


@dataclass(frozen=True)
class Provider:
    provider_id: str
    agency: str
    model: str
    endpoint: str


PROVIDERS = (
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


def fetch_json(url: str, *, retries: int = 3, timeout: int = 35) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, application/geo+json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise RuntimeError("API response was not a JSON object")
                return data
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                wait_seconds = attempt * 3
                log(f"Request failed (attempt {attempt}/{retries}); retrying in {wait_seconds}s: {exc}")
                time.sleep(wait_seconds)

    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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


def fetch_provider_forecast(provider: Provider, target_date: date) -> float:
    payload = fetch_json(forecast_url(provider))
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise RuntimeError("Response did not contain a daily object")

    dates = daily.get("time")
    values = daily.get("temperature_2m_max")
    if not isinstance(dates, list) or not isinstance(values, list):
        raise RuntimeError("Response did not contain daily time and temperature_2m_max lists")

    target_text = target_date.isoformat()
    try:
        index = dates.index(target_text)
    except ValueError as exc:
        raise RuntimeError(f"Target date {target_text} was absent from the response") from exc

    value = finite_number(values[index] if index < len(values) else None)
    if value is None:
        raise RuntimeError(f"No finite maximum temperature was returned for {target_text}")

    return round(value, 1)


def capture_tomorrow_forecasts(
    archive: dict[str, Any],
    now_local: datetime,
) -> dict[str, Any]:
    target_date = now_local.date() + timedelta(days=1)
    target_key = target_date.isoformat()

    existing = archive.setdefault("forecasts", {}).get(target_key)
    if isinstance(existing, dict) and existing.get("providers"):
        log(f"Forecasts for {target_key} already exist; replacing them with this fixed-time capture.")

    available: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []

    for provider in PROVIDERS:
        try:
            forecast_high = fetch_provider_forecast(provider, target_date)
            available.append(
                {
                    "provider_id": provider.provider_id,
                    "agency": provider.agency,
                    "model": provider.model,
                    "forecast_high_c": forecast_high,
                }
            )
            log(f"Captured {provider.agency} {provider.model}: {forecast_high:.1f}°C")
        except Exception as exc:  # Continue so one provider cannot stop the daily update.
            unavailable.append(
                {
                    "provider_id": provider.provider_id,
                    "agency": provider.agency,
                    "model": provider.model,
                    "reason": str(exc),
                }
            )
            log(f"Unavailable: {provider.agency} {provider.model}: {exc}")

    record = {
        "target_date": target_key,
        "forecast_capture_date": now_local.date().isoformat(),
        "captured_at": now_local.isoformat(timespec="seconds"),
        "lead_definition": "Following local calendar day (Day-1)",
        "providers": available,
        "unavailable": unavailable,
    }
    archive["forecasts"][target_key] = record
    archive["last_capture_at"] = now_local.isoformat(timespec="seconds")
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
        # Some OGC responses may wrap a single result in a feature collection.
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
            row["agency"].casefold(),
            row["model"].casefold(),
        )
    )

    previous_error: float | None = None
    previous_rank = 0

    for index, row in enumerate(results, start=1):
        current_error = row["absolute_error_c"]
        if previous_error is not None and math.isclose(
            current_error,
            previous_error,
            abs_tol=0.0001,
        ):
            row["rank"] = previous_rank
        else:
            row["rank"] = index
            previous_rank = index
            previous_error = current_error


def build_verification(
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
        "published_at": published_at.isoformat(timespec="seconds"),
        "results": results,
        "unavailable_models": unavailable_models,
    }


def verification_exists(history: list[dict[str, Any]], verification_date: str) -> bool:
    return any(item.get("verification_date") == verification_date for item in history)


def verify_pending_dates(
    archive: dict[str, Any],
    history: list[dict[str, Any]],
    now_local: datetime,
    lookback_days: int = 10,
) -> list[dict[str, Any]]:
    verified_now: list[dict[str, Any]] = []
    forecasts = archive.get("forecasts", {})

    for days_back in range(1, lookback_days + 1):
        candidate = now_local.date() - timedelta(days=days_back)
        candidate_key = candidate.isoformat()

        record = forecasts.get(candidate_key)
        if not isinstance(record, dict):
            continue
        if verification_exists(history, candidate_key):
            continue

        actual = fetch_eccc_observed_max(candidate)
        if actual is None:
            continue

        verification = build_verification(record, actual, now_local)
        history.append(verification)
        verified_now.append(verification)
        log(
            f"Verified {candidate_key}: observed maximum {actual:.1f}°C "
            f"against {len(verification['results'])} forecasts."
        )

    history.sort(key=lambda item: item.get("verification_date", ""))
    return verified_now


def write_history_csv(history: list[dict[str, Any]]) -> None:
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
                        "station_code": verification.get("location", {}).get("station_code"),
                        "actual_high_c": verification.get("actual_high_c"),
                        "provider_id": result.get("provider_id"),
                        "agency": result.get("agency"),
                        "model": result.get("model"),
                        "forecast_high_c": result.get("forecast_high_c"),
                        "error_c": result.get("error_c"),
                        "absolute_error_c": result.get("absolute_error_c"),
                        "rating": result.get("rating"),
                        "rank": result.get("rank"),
                        "forecast_captured_at": verification.get("forecast_captured_at"),
                        "published_at": verification.get("published_at"),
                    }
                )

    temporary.replace(HISTORY_CSV_PATH)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_local = datetime.now(TORONTO_TZ).replace(microsecond=0)

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

    if not isinstance(archive, dict):
        raise RuntimeError("forecast_archive.json must contain a JSON object")
    if not isinstance(history, list):
        raise RuntimeError("history.json must contain a JSON list")

    archive["location"] = LOCATION

    log("Beginning ForecastRank daily update.")
    capture_record = capture_tomorrow_forecasts(archive, now_local)
    verified_now = verify_pending_dates(archive, history, now_local)

    write_json(ARCHIVE_PATH, archive)
    write_json(HISTORY_JSON_PATH, history)
    write_history_csv(history)

    if verified_now:
        latest = max(
            verified_now,
            key=lambda item: item.get("verification_date", ""),
        )
        write_json(LATEST_PATH, latest)
        log(f"Published latest leaderboard for {latest['verification_date']}.")
    elif history:
        latest = max(
            history,
            key=lambda item: item.get("verification_date", ""),
        )
        # Preserve the newest verified result while still updating its publication
        # only when the verification itself changes.
        write_json(LATEST_PATH, latest)
        log(f"No new verification; retained leaderboard for {latest['verification_date']}.")
    else:
        # Keep the included demonstration page until a real verification exists.
        log(
            "No verified result exists yet. The demonstration latest.json remains "
            "in place until the first official result can be published."
        )

    log(
        f"Captured {len(capture_record['providers'])} forecasts for "
        f"{capture_record['target_date']}."
    )
    log("ForecastRank daily update completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FATAL: {exc}")
        raise
