import re
from dataclasses import dataclass
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tavily import TavilyClient

from config.settings import settings


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float
    published_date: Optional[str] = None


def _clean_text(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class WebSearchTool:
    def __init__(self):
        self._client = TavilyClient(api_key=settings.tavily_api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def search(self, query: str, max_results: int = None) -> list[SearchResult]:
        """
        Run a Tavily search and return cleaned, structured results.

        Args:
            query: Search query string
            max_results: Number of results (defaults to settings.max_search_results)

        Returns:
            List of SearchResult dataclasses, sorted by relevance score
        """
        max_results = max_results or settings.max_search_results

        response = self._client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
        )

        results = []
        for item in response.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", "").strip(),
                    url=item.get("url", ""),
                    content=_clean_text(item.get("content", "")),
                    score=item.get("score", 0.0),
                    published_date=item.get("published_date"),
                )
            )

        return sorted(results, key=lambda r: r.score, reverse=True)

    def search_financial_news(self, query: str, max_results: int = None) -> list[SearchResult]:
        """Append financial context to the query for better results."""
        financial_query = f"{query} financial analysis India stock market"
        return self.search(financial_query, max_results)

    def format_for_llm(self, results: list[SearchResult]) -> str:
        """Format search results into a clean string for LLM context."""
        if not results:
            return "No search results found."

        parts = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"[{i}] {r.title}\n"
                f"URL: {r.url}\n"
                f"Content: {r.content[:500]}\n"
            )
        return "\n".join(parts)


# Module-level singleton
web_search = WebSearchTool()
