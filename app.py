from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
DATA_PATH = Path(os.getenv("DATA_PATH", ROOT / "data" / "documents.json"))
SITES = {
    "DarGlobal": {
        "domain": "darglobal.co.uk",
        "sitemaps": ["https://darglobal.co.uk/sitemap.xml"],
        "include": re.compile(r"/(projects|press|blog|about|faq)(/|$)"),
        "seeds": ["https://darglobal.co.uk/", "https://darglobal.co.uk/projects/properties-in-saudi-arabia", "https://darglobal.co.uk/projects/properties-in-uae", "https://darglobal.co.uk/faq"],
    },
    "Wasalt": {
        "domain": "wasalt.sa",
        "sitemaps": ["https://wasalt.sa/sitemap.xml", "https://wasalt.sa/sitemap_index.xml"],
        "include": re.compile(r"/(en/(properties|corporate|projects)|en$)"),
        "seeds": ["https://wasalt.sa/en", "https://wasalt.sa/en/properties-for-sale-in-saudi-arabia", "https://wasalt.sa/en/properties-for-sale-in-riyadh", "https://wasalt.sa/en/properties-for-rent-in-riyadh", "https://wasalt.sa/en/corporate"],
    },
}
HEADERS = {"User-Agent": "DarWasaltResearchBot/1.0 (public pages; contact: project owner)"}
_documents: list[dict[str, Any]] = []
_lock = threading.Lock()


def sitemap_locations(content: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return []
    return [element.text.strip() for element in root.iter() if element.tag.endswith("loc") and element.text]


def load_documents() -> list[dict[str, Any]]:
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def sitemap_urls(site: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for sitemap in site["sitemaps"]:
        try:
            response = requests.get(sitemap, headers=HEADERS, timeout=12)
            if response.ok:
                urls.extend(sitemap_locations(response.content))
        except requests.RequestException:
            continue
    # One level of sitemap index expansion; bound crawl size and stay on the publisher's domain.
    expanded: list[str] = []
    for url in urls[:15]:
        if urlparse(url).netloc.endswith(site["domain"]) and url.lower().endswith(".xml"):
            try:
                response = requests.get(url, headers=HEADERS, timeout=12)
                if response.ok:
                    expanded.extend(sitemap_locations(response.content))
            except requests.RequestException:
                pass
        else:
            expanded.append(url)
    return expanded


def scrape_site(name: str, site: dict[str, Any], max_pages: int = 45) -> list[dict[str, str]]:
    robots_url = f"https://{site['domain']}/robots.txt"
    robots = RobotFileParser()
    robots.set_url(robots_url)
    try:
        robots_response = requests.get(robots_url, headers=HEADERS, timeout=12)
        if not robots_response.ok:
            return []
        robots.parse(robots_response.text.splitlines())
    except requests.RequestException:
        # Fail closed if the site's crawl policy cannot be read.
        return []
    candidates = list(dict.fromkeys(site["seeds"] + [u for u in sitemap_urls(site) if site["include"].search(urlparse(u).path)]))
    docs: list[dict[str, str]] = []
    for url in candidates[:max_pages]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc.endswith(site["domain"]) or not robots.can_fetch("*", url):
            continue
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if not response.ok or "text/html" not in response.headers.get("content-type", ""):
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
                tag.decompose()
            title = (soup.title.get_text(" ", strip=True) if soup.title else parsed.path.strip("/").replace("/", " — "))[:180]
            main = soup.find("main") or soup.body or soup
            content = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
            content = content[:16000]
            if len(content) >= 180:
                docs.append({"source": name, "title": title, "url": url, "text": content})
        except requests.RequestException:
            continue
        time.sleep(0.4)
    return docs


def refresh_corpus() -> int:
    global _documents
    scraped: list[dict[str, str]] = []
    for name, site in SITES.items():
        scraped.extend(scrape_site(name, site))
    if scraped:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(json.dumps(scraped, ensure_ascii=False, indent=2), encoding="utf-8")
        with _lock:
            _documents = scraped
    return len(scraped)


def terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[\w-]{3,}", text) if word.lower() not in {"the", "and", "for", "with", "from", "what", "where", "how", "are", "can", "does", "about", "wasalt", "darglobal"}}


def retrieve(query: str, limit: int = 5) -> list[dict[str, str]]:
    query_terms = terms(query)
    ranked = []
    for doc in _documents:
        doc_terms = terms(doc["title"] + " " + doc["text"])
        score = len(query_terms & doc_terms) / max(1, len(query_terms))
        if score:
            ranked.append((score, doc))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in ranked[:limit]]


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _documents
    _documents = load_documents()
    # Refresh on every launch so a previously cached partial crawl cannot hide a source.
    threading.Thread(target=refresh_corpus, daemon=True).start()
    yield


app = FastAPI(title="Property Guide | DarGlobal × Wasalt", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    key_configured = api_key.startswith("sk-or-")
    return {"status": "ok", "documents": len(_documents), "openrouter_configured": key_configured, "sources": list(SITES)}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not api_key.startswith("sk-or-"):
        raise HTTPException(503, "Add your OpenRouter API key to the OPENROUTER_API_KEY setting in the project .env file, then restart the app.")
    docs = retrieve(request.message)
    if not docs:
        raise HTTPException(503, "The source library is loading. Please try again in a moment.")
    sources = [{"title": d["title"], "url": d["url"], "publisher": d["source"]} for d in docs]
    evidence = "\n\n".join(f"[{i+1}] {d['source']} — {d['title']} ({d['url']})\n{d['text'][:2500]}" for i, d in enumerate(docs))
    messages = [{"role": "system", "content": "You are Estate Atlas, a helpful real-estate information assistant for public DarGlobal and Wasalt webpages. Answer only from the supplied excerpts. Clearly distinguish DarGlobal developer projects from Wasalt marketplace listings. Never invent availability, price, returns, or legal advice; say when the excerpts do not establish a fact. Keep replies concise, and cite evidence inline using [1], [2] matching the supplied source list."}]
    for item in request.history[-6:]:
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:1200]})
    messages.append({"role": "user", "content": f"Question: {request.message}\n\nPublic source excerpts:\n{evidence}"})
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": os.getenv("PUBLIC_URL", "http://localhost:8000"), "X-Title": "Estate Atlas"}, json={"model": os.getenv("OPENROUTER_MODEL", "openrouter/free"), "messages": messages, "temperature": 0.2}, timeout=45)
        if response.status_code in {401, 403}:
            raise HTTPException(502, "OpenRouter rejected the API key. Check that the full key was copied into .env, then restart the app.")
        if response.status_code == 429:
            raise HTTPException(503, "OpenRouter rate-limited the free model. Wait a little and try again.")
        if response.status_code == 402:
            raise HTTPException(503, "OpenRouter requires credits for this request. Check that OPENROUTER_MODEL is set to a free model.")
        if response.status_code == 404:
            raise HTTPException(503, "The selected OpenRouter model is unavailable. Choose another free model and try again.")
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
        model = response.json().get("model", "openrouter/free")
        return {"answer": answer, "sources": sources, "model": model}
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(502, "The free model is temporarily unavailable. Try again shortly.") from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

