"""
AuraOS · Browser MCP Server
Port: 8106
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from playwright.async_api import async_playwright

from config.settings import settings


class BrowserManager:
    """
    Keeps a single Playwright browser + context alive across requests,
    created lazily on first use and bound to FastAPI's own event loop
    via the lifespan handler — avoids cross-event-loop Playwright errors.
    """
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()

    async def ensure_started(self):
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=False)
                self._context = await self._browser.new_context()
                self._page = await self._context.new_page()

    async def get_page(self):
        await self.ensure_started()
        # Re-check page is still usable; recreate if it was closed externally
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    async def new_tab(self):
        await self.ensure_started()
        self._page = await self._context.new_page()
        return self._page

    async def shutdown(self):
        async with self._lock:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._browser = None
            self._playwright = None
            self._page = None


manager = BrowserManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing eager — browser launches lazily on first tool call
    yield
    # Shutdown: clean up Playwright properly
    await manager.shutdown()


app = FastAPI(title="AuraOS Browser Server", lifespan=lifespan)


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "server": "browser"}


@app.post("/tools/open_url")
async def open_url(req: ToolRequest):
    url = req.params.get("url")
    new_tab = req.params.get("new_tab", False)
    if not url:
        return {"success": False, "error": "url is required"}

    try:
        page = await (manager.new_tab() if new_tab else manager.get_page())
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        return {"success": True, "output": {"url": url, "title": title}}
    except Exception as e:
        return {"success": False, "error": f"Failed to open {url}: {e}"}


@app.post("/tools/search_web")
async def search_web(req: ToolRequest):
    query = req.params.get("query")
    engine = req.params.get("engine", "google")
    if not query:
        return {"success": False, "error": "query is required"}

    search_urls = {
        "google": f"https://www.google.com/search?q={query}",
        "leetcode": f"https://leetcode.com/problemset/?search={query}",
        "github": f"https://github.com/search?q={query}",
        "stackoverflow": f"https://stackoverflow.com/search?q={query}",
    }
    url = search_urls.get(engine, search_urls["google"])

    try:
        page = await manager.get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        return {"success": True, "output": {"query": query, "engine": engine, "url": url, "title": title}}
    except Exception as e:
        return {"success": False, "error": f"Search failed: {e}"}


@app.post("/tools/fill_form")
async def fill_form(req: ToolRequest):
    fields = req.params.get("fields", {})
    submit_selector = req.params.get("submit_selector")

    if not fields:
        return {"success": False, "error": "fields dict is required"}

    try:
        page = await manager.get_page()
        filled = []
        for selector, value in fields.items():
            await page.fill(selector, value, timeout=5000)
            filled.append(selector)

        if submit_selector:
            await page.click(submit_selector, timeout=5000)

        return {"success": True, "output": {"filled_fields": filled, "submitted": bool(submit_selector)}}
    except Exception as e:
        return {"success": False, "error": f"Form fill failed: {e}"}


@app.post("/tools/click_element")
async def click_element(req: ToolRequest):
    selector = req.params.get("selector")
    if not selector:
        return {"success": False, "error": "selector is required"}

    try:
        page = await manager.get_page()
        await page.click(selector, timeout=5000)
        return {"success": True, "output": {"clicked": selector}}
    except Exception as e:
        return {"success": False, "error": f"Click failed: {e}"}


@app.post("/tools/get_page_text")
async def get_page_text(req: ToolRequest):
    try:
        page = await manager.get_page()
        text = await page.inner_text("body")
        truncated = text[:3000]
        return {"success": True, "output": {"text": truncated, "truncated": len(text) > 3000}}
    except Exception as e:
        return {"success": False, "error": f"Failed to extract text: {e}"}


@app.post("/tools/close_browser")
async def close_browser(req: ToolRequest):
    try:
        await manager.shutdown()
        return {"success": True, "output": {"closed": True}}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print(f"[browser-server] starting on port {settings.port_browser}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_browser, log_level="warning")