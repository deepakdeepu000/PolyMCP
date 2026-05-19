"""
mcp_servers/weather_server/handlers/fetch_weather_data.py
──────────────────────────────────────────────────────────
Handler: fetch real-time weather using WeatherAPI.com

API endpoint : https://api.weatherapi.com/v1/current.json
Docs         : https://www.weatherapi.com/docs/
Env key      : WEATHERAPI_KEY  (in .env)
Free tier    : 1 million calls/month — https://www.weatherapi.com/pricing.aspx

Response shape this handler is written for (verified against live response):
{
  "location": { name, region, country, lat, lon, tz_id, localtime, ... },
  "current": {
    "temp_c", "temp_f", "feelslike_c", "feelslike_f",
    "windchill_c", "heatindex_c", "dewpoint_c",
    "wind_kph", "wind_mph", "wind_degree", "wind_dir", "gust_kph",
    "pressure_mb", "precip_mm", "humidity", "cloud", "vis_km",
    "uv", "is_day",
    "condition": { "text", "icon", "code" },
    "air_quality": { "co","no2","o3","so2","pm2_5","pm10",
                     "us-epa-index","gb-defra-index" }
  }
}

Called by : mcp_servers/weather_server/server.py  via @app.tool()
Updated in: config/settings.py  →  WEATHERAPI_KEY
"""

import httpx
    
from config.settings import WEATHERAPI_KEY


# ── US EPA Air Quality Index labels ──────────────────────────────────────────
_EPA_AQI: dict[int, str] = {
    1: "Good",
    2: "Moderate",
    3: "Unhealthy for sensitive groups",
    4: "Unhealthy",
    5: "Very Unhealthy",
    6: "Hazardous",
}

# ── GB DEFRA Index labels ─────────────────────────────────────────────────────
_DEFRA: dict[int, str] = {
    1: "Low (1)",   2: "Low (2)",   3: "Low (3)",
    4: "Moderate (4)", 5: "Moderate (5)", 6: "Moderate (6)",
    7: "High (7)",  8: "High (8)",  9: "High (9)",
    10: "Very High (10)",
}


def _uv_label(uv: float) -> str:
    """Attach a risk label to the raw UV index number."""
    uv = float(uv)
    if uv == 0:      return "0 (None — night)"
    if uv <= 2:      return f"{uv} (Low)"
    if uv <= 5:      return f"{uv} (Moderate)"
    if uv <= 7:      return f"{uv} (High)"
    if uv <= 10:     return f"{uv} (Very High)"
    return f"{uv} (Extreme)"


def _pm25_label(pm25: float) -> str:
    """WHO 2021 PM2.5 breakpoints → plain-English health note."""
    if pm25 <= 15:   return f"{pm25:.1f} µg/m³ (Good)"
    if pm25 <= 35:   return f"{pm25:.1f} µg/m³ (Moderate)"
    if pm25 <= 55:   return f"{pm25:.1f} µg/m³ (Unhealthy for sensitive)"
    if pm25 <= 150:  return f"{pm25:.1f} µg/m³ (Unhealthy)"
    return f"{pm25:.1f} µg/m³ (Very Unhealthy)"


async def fetch_weather_data(city: str) -> str:
    """
    Fetch real-time weather conditions for any city using WeatherAPI.com.

    Use this for ANY weather question:
      'weather in Bengaluru', 'is it raining in New Delhi',
      'temperature in Tokyo today', 'how hot is Dubai right now',
      'current conditions in London', 'humidity in Mumbai',
      'air quality in Hyderabad', 'what is the AQI in Delhi'

    Returns full current conditions including temperature, feels-like,
    wind, humidity, UV index, visibility, pressure, dew point,
    heat index, wind chill, and air quality (AQI).

    Args:
        city : city name as the user said it — e.g. 'New Delhi',
               'Bengaluru', 'Rajahmundry', 'London', 'New York', 'Dubai'
     """
    # if not WEATHERAPI_KEY:
    #     return (
    #         "Weather data requires a WeatherAPI.com key.\n"
    #         "Get a free key at https://www.weatherapi.com and set\n"
    #         "WEATHERAPI_KEY=your_key in your .env file."
    #     )

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.weatherapi.com/v1/current.json",
            params={
                "key":  WEATHERAPI_KEY,
                "q":     city,          
                "aqi":   "yes",       
            },
        )

    # ── HTTP-level errors ─────────────────────────────────────────────────
    if resp.status_code == 400:
        return (
            f"City not found: '{city}'.\n"
            "Try a different spelling — e.g. 'New Delhi', 'Bengaluru', 'Mumbai'."
        )
    if resp.status_code == 401:
        return "Invalid WeatherAPI key. Check WEATHERAPI_KEY in your .env file."
    if resp.status_code == 403:
        return "WeatherAPI key has exceeded its monthly quota. Upgrade at weatherapi.com."
    if resp.status_code != 200:
        return f"WeatherAPI error {resp.status_code}. Try again later."

    data = resp.json()

    # ── API-level error block (WeatherAPI embeds errors in 400 responses) ──
    if "error" in data:
        code = data["error"].get("code", "?")
        msg  = data["error"].get("message", str(data["error"]))
        return f"WeatherAPI error [{code}]: {msg}"

    # ── Parse location ────────────────────────────────────────────────────
    loc        = data.get("location", {})
    city_name  = loc.get("name",       city)
    region     = loc.get("region",     "")
    country    = loc.get("country",    "")
    lat        = loc.get("lat",        "")
    lon        = loc.get("lon",        "")
    tz_id      = loc.get("tz_id",      "")
    local_time = loc.get("localtime",  "")

    full_location = ", ".join(filter(None, [city_name, region, country]))

    # ── Parse current conditions ──────────────────────────────────────────
    cur = data.get("current", {})

    # Temperature group
    temp_c       = cur.get("temp_c",       "—")
    temp_f       = cur.get("temp_f",       "—")
    feelslike_c  = cur.get("feelslike_c",  "—")
    feelslike_f  = cur.get("feelslike_f",  "—")
    windchill_c  = cur.get("windchill_c",  "—")   # adjusted for wind cooling
    heatindex_c  = cur.get("heatindex_c",  "—")   # adjusted for humidity heat
    dewpoint_c   = cur.get("dewpoint_c",   "—")   # moisture in air

    # Sky / condition
    condition    = cur.get("condition", {})
    cond_text    = condition.get("text", "—")
    cond_icon    = condition.get("icon", "")       # URL for frontend display
    cond_code    = condition.get("code", "")
    is_day       = cur.get("is_day", 1)
    day_label    = "Day" if is_day else "Night"

    # Wind
    wind_kph     = cur.get("wind_kph",    "—")
    wind_mph     = cur.get("wind_mph",    "—")
    wind_degree  = cur.get("wind_degree", 0)
    wind_dir     = cur.get("wind_dir",    "—")    # e.g. "ESE"
    gust_kph     = cur.get("gust_kph",   "—")

    # Atmosphere
    pressure_mb  = cur.get("pressure_mb", "—")
    pressure_in  = cur.get("pressure_in", "—")
    precip_mm    = cur.get("precip_mm",   "—")
    humidity     = cur.get("humidity",    "—")    # %
    cloud        = cur.get("cloud",       "—")    # % cloud cover
    vis_km       = cur.get("vis_km",      "—")
    uv           = cur.get("uv",          0)

    # Radiation (available from WeatherAPI pro — may be 0 on free)
    short_rad    = cur.get("short_rad",   None)
    diff_rad     = cur.get("diff_rad",    None)

    # ── Parse air quality ─────────────────────────────────────────────────
    aq           = cur.get("air_quality", {})
    co           = aq.get("co",           None)   # µg/m³
    no2          = aq.get("no2",          None)
    o3           = aq.get("o3",           None)
    so2          = aq.get("so2",          None)
    pm2_5        = aq.get("pm2_5",        None)
    pm10         = aq.get("pm10",         None)
    epa_index    = aq.get("us-epa-index", None)
    defra_index  = aq.get("gb-defra-index", None)

    # ── Build output ──────────────────────────────────────────────────────
    lines = [
        f"╔══════════════════════════════════════════════╗",
        f"  REAL-TIME WEATHER — {full_location}",
        f"╚══════════════════════════════════════════════╝",
        f"",
        f"  Local time   : {local_time}  [{day_label}]",
        f"  Timezone     : {tz_id}",
        f"  Coordinates  : {lat}°N, {lon}°E",
        f"",
        f"── CONDITION ───────────────────────────────────",
        f"  Sky          : {cond_text}",
        f"  Cloud cover  : {cloud}%",
        f"  Icon URL     : https:{cond_icon}" if cond_icon else "",
        f"",
        f"── TEMPERATURE ─────────────────────────────────",
        f"  Actual       : {temp_c}°C  /  {temp_f}°F",
        f"  Feels Like   : {feelslike_c}°C  /  {feelslike_f}°F",
        f"  Heat Index   : {heatindex_c}°C    ← humidity-adjusted warmth",
        f"  Wind Chill   : {windchill_c}°C    ← wind-adjusted cold",
        f"  Dew Point    : {dewpoint_c}°C     ← air moisture level",
        f"",
        f"── WIND ────────────────────────────────────────",
        f"  Speed        : {wind_kph} km/h  ({wind_mph} mph)",
        f"  Direction    : {wind_dir}  ({wind_degree}°)",
        f"  Gusts        : {gust_kph} km/h",
        f"",
        f"── ATMOSPHERE ──────────────────────────────────",
        f"  Humidity     : {humidity}%",
        f"  Pressure     : {pressure_mb} mb  ({pressure_in} in)",
        f"  Precipitation: {precip_mm} mm",
        f"  Visibility   : {vis_km} km",
        f"  UV Index     : {_uv_label(uv)}",
    ]

    # Radiation block — only show if non-zero (pro tier or daytime)
    if short_rad is not None and (short_rad or diff_rad):
        lines += [
            f"",
            f"── SOLAR RADIATION ─────────────────────────────",
            f"  Shortwave    : {short_rad} W/m²",
            f"  Diffuse      : {diff_rad} W/m²",
        ]

    # Air quality block — show if data present
    has_aq = any(v is not None for v in [co, no2, o3, so2, pm2_5, pm10])
    if has_aq:
        lines += [
            f"",
            f"── AIR QUALITY ─────────────────────────────────",
        ]
        if epa_index is not None:
            lines.append(f"  US EPA AQI   : {_EPA_AQI.get(epa_index, str(epa_index))}")
        if defra_index is not None:
            lines.append(f"  GB DEFRA     : {_DEFRA.get(defra_index, str(defra_index))}")
        if pm2_5 is not None:
            lines.append(f"  PM2.5        : {_pm25_label(pm2_5)}")
        if pm10 is not None:
            lines.append(f"  PM10         : {pm10:.1f} µg/m³")
        if co is not None:
            lines.append(f"  CO           : {co:.2f} µg/m³")
        if no2 is not None:
            lines.append(f"  NO₂          : {no2:.2f} µg/m³")
        if o3 is not None:
            lines.append(f"  O₃           : {o3:.2f} µg/m³")
        if so2 is not None:
            lines.append(f"  SO₂          : {so2:.2f} µg/m³")

    lines.append("")
    return "\n".join(l for l in lines if l is not None)

if __name__ == "__main__":
    import asyncio
    city = "rajahmundry"
    print(f"Fetching weather for {city}...\n")
    result = asyncio.run(fetch_weather_data(city))
    print(result)