# SRC/tools/weather_tool.py

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, List

import requests




def _j(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


class WeatherTool:
    """
    OpenWeather tool (CrewAI BaseTool).

    Inputs (kwargs):
      - location: str (e.g., "Hisar, Haryana, India")  OR
      - latitude: float + longitude: float
      - days: int (1-5), default 3
      - units: "metric"|"imperial"|"standard", default "metric"
      - lang: optional language code for weather descriptions

    Output: JSON string:
      {
        "tool": "weather_tool",
        "status": "ok|missing_data|not_configured|error",
        "message": "...",
        "inputs_received": {...},
        "missing_data": [...],
        "data": {...},
        "sources": [...]
      }
    """

    name: str = "weather_tool"
    description: str = (
        "Fetches 1–5 day weather forecast using OpenWeather geocoding + 5-day/3-hour forecast. "
        "Provide location OR latitude+longitude. Optional days/units/lang."
    )

    base_url: str = "https://api.openweathermap.org"
    timeout_sec: int = 12

    def _api_key(self) -> Optional[str]:
        return os.getenv("OPENWEATHER_API_KEY")

    def _geocode(self, location: str, api_key: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/geo/1.0/direct"
        params = {"q": location, "limit": 1, "appid": api_key}
        try:
            r = requests.get(url, params=params, timeout=self.timeout_sec)
            if r.status_code != 200:
                return None, f"geocode_http_{r.status_code}"
            arr = r.json()
            if not arr:
                return None, "geocode_no_results"
            return arr[0], None
        except requests.RequestException:
            return None, "geocode_network_error"
        except Exception:
            return None, "geocode_parse_error"

    def _forecast(self, lat: float, lon: float, api_key: str, units: str, lang: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/data/2.5/forecast"
        params = {"lat": lat, "lon": lon, "appid": api_key, "units": units}
        if lang:
            params["lang"] = lang
        try:
            r = requests.get(url, params=params, timeout=self.timeout_sec)
            if r.status_code != 200:
                return None, f"forecast_http_{r.status_code}"
            return r.json(), None
        except requests.RequestException:
            return None, "forecast_network_error"
        except Exception:
            return None, "forecast_parse_error"

    def _daily_summary(self, forecast_json: Dict[str, Any], days: int) -> List[Dict[str, Any]]:
        entries = forecast_json.get("list", []) or []
        by_date: Dict[str, List[Dict[str, Any]]] = {}

        for e in entries:
            dt_txt = e.get("dt_txt")
            dt_unix = e.get("dt")
            if dt_txt:
                date_key = dt_txt.split(" ")[0]
            elif dt_unix:
                date_key = datetime.fromtimestamp(int(dt_unix), tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                continue
            by_date.setdefault(date_key, []).append(e)

        dates_sorted = sorted(by_date.keys())[: max(1, min(days, 5))]

        out: List[Dict[str, Any]] = []
        for d in dates_sorted:
            chunk = by_date[d]

            temps = [c.get("main", {}).get("temp") for c in chunk if isinstance(c.get("main", {}).get("temp"), (int, float))]
            tmins = [c.get("main", {}).get("temp_min") for c in chunk if isinstance(c.get("main", {}).get("temp_min"), (int, float))]
            tmaxs = [c.get("main", {}).get("temp_max") for c in chunk if isinstance(c.get("main", {}).get("temp_max"), (int, float))]

            rain_3h = []
            for c in chunk:
                v = (c.get("rain") or {}).get("3h")
                if isinstance(v, (int, float)):
                    rain_3h.append(v)

            descs = []
            for c in chunk:
                w = c.get("weather") or []
                if w and isinstance(w, list) and isinstance(w[0], dict):
                    desc = w[0].get("description")
                    if isinstance(desc, str) and desc.strip():
                        descs.append(desc.strip().lower())
            dominant = max(set(descs), key=descs.count) if descs else None

            out.append(
                {
                    "date": d,
                    "temp_min": min(tmins) if tmins else (min(temps) if temps else None),
                    "temp_max": max(tmaxs) if tmaxs else (max(temps) if temps else None),
                    "rain_total_mm_est": round(sum(rain_3h), 2) if rain_3h else 0.0,
                    "dominant_condition": dominant,
                }
            )

        return out

    def run(self, **kwargs) -> str:
        api_key = self._api_key()
        if not api_key:
            return _j(
                {
                    "tool": self.name,
                    "status": "not_configured",
                    "message": "OPENWEATHER_API_KEY is not set in environment.",
                    "inputs_received": kwargs,
                    "missing_data": ["OPENWEATHER_API_KEY"],
                    "data": {},
                    "sources": ["https://openweathermap.org/appid"],
                }
            )

        location = kwargs.get("location")
        lat = kwargs.get("latitude")
        lon = kwargs.get("longitude")
        units = kwargs.get("units", "metric")
        lang = kwargs.get("lang")

        days = kwargs.get("days", 3)
        try:
            days = int(days)
        except Exception:
            days = 3
        days = max(1, min(days, 5))

        geo_meta = None
        if (lat is None or lon is None) and location:
            geo_meta, geo_err = self._geocode(str(location), api_key)
            if geo_err:
                return _j(
                    {
                        "tool": self.name,
                        "status": "missing_data",
                        "message": "Could not resolve location to coordinates.",
                        "inputs_received": {"location": location, "days": days, "units": units, "lang": lang},
                        "missing_data": ["valid_location OR latitude+longitude"],
                        "data": {"geocoding_error": geo_err},
                        "sources": ["https://openweathermap.org/api/geocoding-api"],
                    }
                )
            lat = geo_meta.get("lat")
            lon = geo_meta.get("lon")

        if lat is None or lon is None:
            return _j(
                {
                    "tool": self.name,
                    "status": "missing_data",
                    "message": "Need either location OR latitude+longitude.",
                    "inputs_received": {"location": location, "latitude": lat, "longitude": lon, "days": days},
                    "missing_data": ["location OR latitude+longitude"],
                    "data": {},
                    "sources": [],
                }
            )

        forecast_json, ferr = self._forecast(float(lat), float(lon), api_key, units, lang)
        if ferr or not forecast_json:
            return _j(
                {
                    "tool": self.name,
                    "status": "error",
                    "message": "Failed to fetch forecast from OpenWeather.",
                    "inputs_received": {"location": location, "latitude": lat, "longitude": lon, "days": days, "units": units, "lang": lang},
                    "missing_data": ["check_api_key_quota_or_retry"],
                    "data": {"forecast_error": ferr},
                    "sources": ["https://openweathermap.org/forecast5"],
                }
            )

        city = forecast_json.get("city", {}) or {}
        daily = self._daily_summary(forecast_json, days)

        return _j(
            {
                "tool": self.name,
                "status": "ok",
                "message": "Forecast fetched successfully.",
                "inputs_received": {"location": location, "latitude": lat, "longitude": lon, "days": days, "units": units, "lang": lang},
                "missing_data": [],
                "data": {
                    "resolved_location": {
                        "name": city.get("name") or (geo_meta.get("name") if isinstance(geo_meta, dict) else None),
                        "country": city.get("country") or (geo_meta.get("country") if isinstance(geo_meta, dict) else None),
                        "state": (geo_meta.get("state") if isinstance(geo_meta, dict) else None),
                        "lat": float(lat),
                        "lon": float(lon),
                    },
                    "forecast_window_days": days,
                    "daily_summary": daily,
                    "raw_meta": {"cnt": forecast_json.get("cnt")},
                },
                "sources": [
                    "https://openweathermap.org/api/geocoding-api",
                    "https://openweathermap.org/forecast5",
                ],
            }
        )
