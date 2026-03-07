from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

BNR_URL = "https://www.bnr.ro/nbrfxrates.xml"
DIGI24_URL = "https://www.digi24.ro/rss"

CURRENCIES = ["EUR", "USD", "GBP", "CHF", "HUF", "MDL", "XAU", "XDR"]

async def fetch_bnr():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(BNR_URL)
            root = ET.fromstring(response.text)
            ns = {"bnr": "http://www.bnr.ro/xsd"}
            rates = {}
            date = ""
            for cube in root.findall(".//bnr:Cube", ns):
                cube_date = cube.get("date")
                if cube_date:
                    date = cube_date
                for rate in cube.findall("bnr:Rate", ns):
                    currency = rate.get("currency")
                    multiplier = int(rate.get("multiplier", 1))
                    if currency in CURRENCIES and rate.text:
                        value = float(rate.text) / multiplier
                        rates[currency] = round(value, 4)
            return rates, date
    except Exception as e:
        return {}, str(e)

async def fetch_news():
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(DIGI24_URL)
            root = ET.fromstring(response.content)
            news = []
            for item in root.findall(".//item")[:5]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                if title:
                    news.append({
                        "title": title,
                        "link": link,
                        "date": pub_date
                    })
            return news
    except Exception as e:
        return []

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rates, bnr_date = await fetch_bnr()
    news = await fetch_news()
    gold_ron = rates.pop("XAU", None)
    xdr_ron = rates.pop("XDR", None)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "rates": rates,
        "bnr_date": bnr_date,
        "gold_ron": gold_ron,
        "xdr_ron": xdr_ron,
        "news": news,
        "updated": datetime.now().strftime("%d %b %Y, %H:%M")
    })

@app.get("/health")
async def health():
    return {"status": "healthy"}
