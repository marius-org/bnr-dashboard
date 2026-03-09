from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI()
templates = Jinja2Templates(directory="templates")

tz = ZoneInfo("Europe/Bucharest")

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

async def fetch_football():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://v3.football.api-sports.io/fixtures",
                headers={"x-apisports-key": "fc061d99d65cdf07844c947c9873a1a0"},
                params={"league": "283", "season": "2024", "next": "8"},
                timeout=10
            )
        data = r.json()
        matches = []
        for f in data.get("response", []):
            fixture = f.get("fixture", {})
            teams   = f.get("teams", {})
            goals   = f.get("goals", {})
            matches.append({
                "home":       teams.get("home", {}).get("name", ""),
                "away":       teams.get("away", {}).get("name", ""),
                "home_badge": teams.get("home", {}).get("logo", ""),
                "away_badge": teams.get("away", {}).get("logo", ""),
                "date":       fixture.get("date", "")[:10],
                "time":       fixture.get("date", "")[11:16],
                "round":      f.get("league", {}).get("round", ""),
                "score_h":    goals.get("home"),
                "score_a":    goals.get("away"),
                "status":     fixture.get("status", {}).get("long", ""),
            })
        return matches
    except:
        return []

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rates, gold_ron, xdr_ron, bnr_date = await fetch_bnr()
    news = await fetch_news()
    matches = await fetch_football()
    return templates.TemplateResponse("index.html", {
        "request":  request,
        "rates":    rates,
        "gold_ron": gold_ron,
        "xdr_ron":  xdr_ron,
        "bnr_date": bnr_date,
        "updated":  datetime.now(tz).strftime("%d %b %Y, %H:%M"),
        "news":     news,
        "matches":  matches,
    })

@app.get("/health")
async def health():
    return {"status": "healthy"}
