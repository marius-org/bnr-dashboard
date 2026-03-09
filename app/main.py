from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = FastAPI()
templates = Jinja2Templates(directory="templates")

tz = ZoneInfo("Europe/Bucharest")

CITIES = [
    {"name": "București",   "lat": 44.4268, "lon": 26.1025},
    {"name": "Cluj-Napoca", "lat": 46.7712, "lon": 23.6236},
    {"name": "Timișoara",   "lat": 45.7489, "lon": 21.2087},
    {"name": "Iași",        "lat": 47.1585, "lon": 27.6014},
]

WMO_CODES = {
    0:"Senin", 1:"Predominant senin", 2:"Parțial noros", 3:"Noros",
    45:"Ceață", 48:"Ceață cu chiciură",
    51:"Burniță ușoară", 53:"Burniță moderată", 55:"Burniță densă",
    61:"Ploaie ușoară", 63:"Ploaie moderată", 65:"Ploaie puternică",
    71:"Ninsoare ușoară", 73:"Ninsoare moderată", 75:"Ninsoare puternică",
    80:"Averse ușoare", 81:"Averse moderate", 82:"Averse violente",
    95:"Furtună", 96:"Furtună cu grindină", 99:"Furtună puternică cu grindină",
}

WMO_EMOJI = {
    0:"☀️", 1:"🌤️", 2:"⛅", 3:"☁️",
    45:"🌫️", 48:"🌫️",
    51:"🌦️", 53:"🌦️", 55:"🌧️",
    61:"🌧️", 63:"🌧️", 65:"🌧️",
    71:"🌨️", 73:"❄️", 75:"❄️",
    80:"🌦️", 81:"🌧️", 82:"⛈️",
    95:"⛈️", 96:"⛈️", 99:"⛈️",
}


async def fetch_bnr():
    url = "https://www.bnr.ro/nbrfxrates.xml"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=10)
    root = ET.fromstring(r.text)
    ns = {"bnr": "http://www.bnr.ro/xsd"}
    rates = {}
    gold_ron = None
    xdr_ron = None
    date = root.find(".//bnr:PublishingDate", ns)
    bnr_date = date.text if date is not None else ""
    for cube in root.findall(".//bnr:Rate", ns):
        currency = cube.attrib.get("currency", "")
        multiplier = int(cube.attrib.get("multiplier", 1))
        try:
            value = round(float(cube.text) / multiplier, 4)
        except:
            continue
        if currency == "XAU":
            gold_ron = value
        elif currency == "XDR":
            xdr_ron = value
        else:
            rates[currency] = value
    return rates, gold_ron, xdr_ron, bnr_date


async def fetch_news():
    url = "https://www.digi24.ro/rss"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10)
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "")
            link  = item.findtext("link", "#")
            date  = item.findtext("pubDate", "")
            items.append({"title": title, "link": link, "date": date})
        return items
    except:
        return []


async def fetch_weather():
    results = []
    try:
        async with httpx.AsyncClient() as client:
            for city in CITIES:
                r = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude":        city["lat"],
                        "longitude":       city["lon"],
                        "current":         "temperature_2m,apparent_temperature,weathercode,windspeed_10m,precipitation",
                        "wind_speed_unit": "kmh",
                        "timezone":        "Europe/Bucharest",
                    },
                    timeout=10
                )
                data = r.json()
                cur  = data.get("current", {})
                code = cur.get("weathercode", 0)
                results.append({
                    "city":   city["name"],
                    "temp":   round(cur.get("temperature_2m", 0)),
                    "feels":  round(cur.get("apparent_temperature", 0)),
                    "wind":   round(cur.get("windspeed_10m", 0)),
                    "precip": cur.get("precipitation", 0),
                    "desc":   WMO_CODES.get(code, "—"),
                    "emoji":  WMO_EMOJI.get(code, "🌡️"),
                })
    except:
        pass
    return results


async def fetch_holidays():
    try:
        year = datetime.now(tz).year
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/RO",
                timeout=10
            )
        holidays = r.json()
        today    = datetime.now(tz).date()
        upcoming = []
        for h in holidays:
            hdate = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if hdate >= today:
                delta = (hdate - today).days
                upcoming.append({
                    "date": h["date"],
                    "name": h["localName"],
                    "days": delta,
                })
        return upcoming[:4]
    except:
        return []


async def fetch_earthquakes():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://earthquake.usgs.gov/fdsnws/event/1/query",
                params={
                    "format":       "geojson",
                    "minmagnitude": "2.0",
                    "orderby":      "time",
                    "limit":        "6",
                    "minlatitude":  "43.5",
                    "maxlatitude":  "48.3",
                    "minlongitude": "20.2",
                    "maxlongitude": "30.0",
                },
                timeout=10
            )
        data   = r.json()
        quakes = []
        for f in data.get("features", []):
            props  = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [])
            mag    = props.get("mag", 0)
            place  = props.get("place", "România")
            ts     = props.get("time", 0)
            depth  = round(coords[2]) if len(coords) > 2 else "?"
            dt     = datetime.fromtimestamp(ts / 1000, tz=tz).strftime("%d %b, %H:%M")
            level  = "danger" if mag >= 4.0 else ("warning" if mag >= 3.0 else "ok")
            quakes.append({
                "mag":   mag,
                "place": place,
                "depth": depth,
                "time":  dt,
                "level": level,
            })
        return quakes
    except:
        return []


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rates, gold_ron, xdr_ron, bnr_date = await fetch_bnr()
    news        = await fetch_news()
    weather     = await fetch_weather()
    holidays    = await fetch_holidays()
    earthquakes = await fetch_earthquakes()
    return templates.TemplateResponse("index.html", {
        "request":     request,
        "rates":       rates,
        "gold_ron":    gold_ron,
        "xdr_ron":     xdr_ron,
        "bnr_date":    bnr_date,
        "updated":     datetime.now(tz).strftime("%d %b %Y, %H:%M"),
        "news":        news,
        "weather":     weather,
        "holidays":    holidays,
        "earthquakes": earthquakes,
    })


@app.get("/health")
async def health():
    return {"status": "healthy"}
