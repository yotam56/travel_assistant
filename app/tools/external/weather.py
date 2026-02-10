import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
from langchain.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

USER_AGENT = "TravelAssistant/1.0"
_last_geocode = 0.0

_http_client = httpx.Client(
    timeout=15.0,
    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
)


class ForecastDay(BaseModel):
    """One day of forecast aggregated in UTC."""
    date_utc: str = Field(..., description="Date in UTC, ISO format YYYY-MM-DD.")
    tmin_c: float = Field(..., description="Minimum air temperature (°C) observed in the day's timeseries.")
    tmax_c: float = Field(..., description="Maximum air temperature (°C) observed in the day's timeseries.")


class WeatherForecastResult(BaseModel):
    """
    Structured tool result for a simple multi-day forecast.

    Designed for LLM tool use:
    - Always returns machine-readable fields for rendering or reasoning.
    - On failure, `ok=False` and `error` explains what happened.
    """
    ok: bool = Field(..., description="True if forecast was retrieved and parsed; false otherwise.")
    query: str = Field(..., description="The user-provided location string.")
    place: Optional[str] = Field(None, description="Resolved display name from geocoding.")
    lat: Optional[float] = Field(None, description="Resolved latitude.")
    lon: Optional[float] = Field(None, description="Resolved longitude.")
    timezone: str = Field("UTC", description="Forecast aggregation timezone. This tool aggregates by UTC date.")
    days: List[ForecastDay] = Field(default_factory=list, description="Up to 7 days of daily min/max temps.")
    error: Optional[str] = Field(None, description="Error message when ok=False.")


def _geocode_city(city: str) -> Tuple[str, float, float]:
    """
    Resolve a free-text location (e.g. "Paris", "Tel Aviv, Israel") into coordinates.

    Uses the public Nominatim instance (OpenStreetMap).
    This function includes a very small throttle (~1 request/second) to be polite.
    """
    global _last_geocode

    elapsed = time.monotonic() - _last_geocode
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    _last_geocode = time.monotonic()

    logger.info("Geocoding city: %s", city)
    r = _http_client.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city, "format": "jsonv2", "limit": 1},
    )
    r.raise_for_status()
    results = r.json()

    if not results:
        raise ValueError(f"Could not find '{city}'. Try 'City, Country' (e.g. 'Paris, France').")

    top = results[0]
    return top.get("display_name", city), float(top["lat"]), float(top["lon"])


def _fetch_7day_forecast(place: str, lat: float, lon: float) -> List[ForecastDay]:
    """
    Fetch MET Norway compact forecast and aggregate into daily min/max temperatures.

    Aggregation:
    - Groups forecast points by UTC date (YYYY-MM-DD).
    - Computes min/max of `air_temperature` for each day.
    - Returns up to the first 7 available days.
    """
    logger.info("Fetching forecast for %s (%.4f, %.4f)", place, lat, lon)
    r = _http_client.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/compact",
        params={"lat": lat, "lon": lon},
    )
    r.raise_for_status()

    timeseries = r.json()["properties"]["timeseries"]

    daily: Dict[str, List[float]] = {}
    for item in timeseries:
        day = (
            datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .date()
            .isoformat()
        )
        temp = item["data"]["instant"]["details"].get("air_temperature")
        if isinstance(temp, (int, float)):
            if day not in daily:
                daily[day] = [float(temp), float(temp)]
            else:
                daily[day][0] = min(daily[day][0], float(temp))
                daily[day][1] = max(daily[day][1], float(temp))

    days = sorted(daily.keys())[:7]
    return [
        ForecastDay(date_utc=d, tmin_c=daily[d][0], tmax_c=daily[d][1])
        for d in days
    ]


@tool
def get_weather_forecast(city: str) -> str:
    """
    Get a simple 7-day weather forecast for a city (NO API KEY required).

    When to use:
    - The user asks for a forecast or weather outlook for a named place (city/region/country).
    - Examples: "Weather in Paris", "7 day forecast for Tokyo", "Do I need a jacket in Berlin next week?"

    Input:
    - city: A human-readable location string.
      Prefer "City, Country" when ambiguous (e.g., "Paris, France" vs "Paris, Texas").

    What this tool does:
    1) Geocodes the input string to latitude/longitude using OpenStreetMap Nominatim.
    2) Fetches forecast data from MET Norway (locationforecast).
    3) Aggregates forecast points by UTC date and returns up to 7 days of min/max temperatures.

    Output (machine-readable):
    - Returns a JSON object matching `WeatherForecastResult`.
      On success:
        - ok=true
        - place/lat/lon are set
        - days contains up to 7 entries with {date_utc, tmin_c, tmax_c}
      On failure:
        - ok=false
        - error contains a user-safe explanation
    """
    try:
        place, lat, lon = _geocode_city(city)
        forecast_days = _fetch_7day_forecast(place, lat, lon)
        result = WeatherForecastResult(
            ok=True,
            query=city,
            place=place,
            lat=lat,
            lon=lon,
            days=forecast_days,
        )
    except httpx.TimeoutException:
        result = WeatherForecastResult(
            ok=False, query=city, error=f"Timeout while fetching forecast for '{city}'."
        )
    except ValueError as e:
        result = WeatherForecastResult(ok=False, query=city, error=str(e))
    except Exception as e:
        logger.exception("Unexpected error in get_weather_forecast for '%s'", city)
        result = WeatherForecastResult(
            ok=False, query=city, error=f"Unexpected error: {e}"
        )

    return result.model_dump_json()
