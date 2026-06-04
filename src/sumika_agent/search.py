from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .budget import BudgetManager
from .settings import Settings
from .storage import Store


@dataclass
class SearchResult:
    title: str
    href: str
    body: str


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._capture_title = False
        self._capture_body = False
        self._title_chunks: list[str] = []
        self._body_chunks: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name: value or "" for name, value in attrs}
        classes = attrs_map.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._capture_title = True
            self._title_chunks = []
            self._href = self._normalize_href(attrs_map.get("href", ""))
        elif "result__snippet" in classes:
            self._capture_body = True
            self._body_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            title = self._clean("".join(self._title_chunks))
            if title and self._href:
                self.results.append(SearchResult(title=title[:200], href=self._href[:500], body=""))
            self._capture_title = False
            self._title_chunks = []
            self._href = ""
        elif self._capture_body and tag in {"a", "div", "span"}:
            body = self._clean("".join(self._body_chunks))
            if body and self.results and not self.results[-1].body:
                last = self.results[-1]
                self.results[-1] = SearchResult(last.title, last.href, body[:500])
            self._capture_body = False
            self._body_chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_chunks.append(data)
        if self._capture_body:
            self._body_chunks.append(data)

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(unescape(value).split())

    @staticmethod
    def _normalize_href(href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
        return href


class SearchTool:
    def __init__(self, settings: Settings, store: Store, budget: BudgetManager):
        self.settings = settings
        self.store = store
        self.budget = budget

    def should_search(self, text: str) -> bool:
        if not self.settings.search_enabled or not self.budget.allow_search():
            return False
        triggers = ("帮我查", "搜一下", "搜索", "网上", "最新", "新闻", "现在", "今天")
        return any(trigger in text for trigger in triggers)

    def search(self, query: str, max_results: int = 4) -> list[SearchResult]:
        if not self.settings.search_enabled or not self.budget.allow_search():
            return []
        try:
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                response = client.get(
                    "https://duckduckgo.com/html/",
                    params={"q": query, "kl": "cn-zh"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return []
        parser = _DuckDuckGoHTMLParser()
        parser.feed(response.text)
        results = parser.results[:max_results]
        self.budget.note_estimated_egress("search", len(response.content) + 20_000)
        return results

    @staticmethod
    def format_for_prompt(results: list[SearchResult]) -> str:
        if not results:
            return "搜索工具没有返回可用结果。"
        lines = []
        for idx, result in enumerate(results, start=1):
            lines.append(f"{idx}. {result.title}\n{result.body}\n{result.href}")
        return "\n".join(lines)
