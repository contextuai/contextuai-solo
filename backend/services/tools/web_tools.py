"""
Web operation tools for Strands Agent.
Provides web search, scraping, and fetch capabilities.

Primary search: Tavily (AI-optimized)
Fallbacks: Google Custom Search, Bing Search, DuckDuckGo
"""

import os
import logging
import json
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, quote_plus
from strands.tools import tool
import asyncio
import aiohttp

# Tavily client for AI-optimized web search
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    TavilyClient = None

logger = logging.getLogger(__name__)


class WebTools:
    """Web operation tools for personas with web search and scraping capabilities."""

    def __init__(self):
        """Initialize web tools with API configurations."""
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Tavily API key (primary search - AI-optimized)
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.tavily_client = None
        if self.tavily_api_key and TAVILY_AVAILABLE:
            try:
                self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
                logger.info("Tavily Search API configured (primary)")
            except Exception as e:
                logger.warning(f"Failed to initialize Tavily client: {e}")

        # Fallback API keys
        self.google_api_key = os.getenv("GOOGLE_API_KEY", "")
        self.google_search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
        self.bing_api_key = os.getenv("BING_API_KEY", "")

        # Request timeouts and limits
        self.timeout = 30  # seconds
        self.max_results = 10  # Maximum search results
        self.max_content_size = 5 * 1024 * 1024  # 5 MB max content

        # User agent for web requests
        self.user_agent = "ContextuAI-Agent/1.0 (+https://contextuai.com)"

        # Headers for requests
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

        logger.info(f"WebTools initialized for environment: {self.environment}")
        if self.tavily_client:
            logger.info("Primary search: Tavily (AI-optimized)")
        if self.google_api_key:
            logger.info("Fallback search: Google Custom Search API configured")
        if self.bing_api_key:
            logger.info("Fallback search: Bing Search API configured")

    def get_tools(self):
        """Return all web operation tools."""
        return [
            self.web_search,
            self.fetch_url,
            self.extract_links,
            self.check_url_status
        ]

    @tool
    async def web_search(self, query: str, search_engine: str = "auto", num_results: int = 5) -> Dict[str, Any]:
        """
        Search the web using configured search engines.

        Args:
            query: Search query string
            search_engine: Search engine to use (auto, tavily, google, bing, duckduckgo)
                          'auto' tries Tavily first, then falls back to others
            num_results: Number of results to return (max 10)

        Returns:
            Dictionary with search results including title, url, snippet, and content
        """
        try:
            # Limit number of results
            num_results = min(num_results, self.max_results)

            results = []
            search_engines_used = []

            # Primary: Tavily Search (AI-optimized, returns clean content)
            if search_engine in ["auto", "tavily"] and self.tavily_client:
                tavily_results = await self._tavily_search(query, num_results)
                if tavily_results:
                    results.extend(tavily_results)
                    search_engines_used.append("tavily")

            # Fallback: Google Search
            if not results and search_engine in ["auto", "google"] and self.google_api_key:
                google_results = await self._google_search(query, num_results)
                if google_results:
                    results.extend(google_results)
                    search_engines_used.append("google")

            # Fallback: Bing Search
            if not results and search_engine in ["auto", "bing"] and self.bing_api_key:
                bing_results = await self._bing_search(query, num_results)
                if bing_results:
                    results.extend(bing_results)
                    search_engines_used.append("bing")

            # Last resort: DuckDuckGo (no API key required, but rate limited)
            if not results and search_engine in ["auto", "duckduckgo"]:
                logger.warning("Using DuckDuckGo fallback (rate limited)")
                duckduckgo_results = await self._duckduckgo_search(query, num_results)
                if duckduckgo_results:
                    results.extend(duckduckgo_results)
                    search_engines_used.append("duckduckgo")

            if not results:
                return {
                    "success": False,
                    "error": "No search results found. Please configure TAVILY_API_KEY for reliable search.",
                    "query": query,
                    "hint": "Get a free Tavily API key at https://tavily.com (1000 searches/month free)"
                }

            logger.info(f"Web search completed: {len(results)} results from {search_engines_used}")

            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
                "search_engines": search_engines_used
            }

        except Exception as e:
            logger.error(f"Error performing web search: {e}")
            return {
                "success": False,
                "error": f"Search failed: {str(e)}",
                "query": query
            }

    async def _tavily_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """
        Perform Tavily search (AI-optimized, returns clean content).

        Tavily is designed for LLMs - it aggregates multiple sources and
        returns clean, structured content ready for AI processing.
        """
        try:
            if not self.tavily_client:
                return []

            # Tavily search - run in thread pool since it's synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.tavily_client.search(
                    query=query,
                    max_results=num_results,
                    include_answer=True,  # Get AI-generated answer
                    include_raw_content=False,  # Clean content only
                    search_depth="basic"  # "basic" or "advanced"
                )
            )

            results = []

            # Include the AI-generated answer if available
            if response.get("answer"):
                results.append({
                    "title": "AI Summary",
                    "url": "",
                    "snippet": response["answer"],
                    "content": response["answer"],
                    "source": "tavily",
                    "is_answer": True
                })

            # Include individual search results
            for item in response.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")[:500],  # First 500 chars as snippet
                    "content": item.get("content", ""),  # Full content for LLM context
                    "source": "tavily",
                    "score": item.get("score", 0)  # Relevance score
                })

            logger.info(f"Tavily search returned {len(results)} results for: {query[:50]}...")
            return results

        except Exception as e:
            logger.error(f"Tavily Search failed: {e}")
            return []

    async def _google_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Perform Google Custom Search."""
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.google_api_key,
                "cx": self.google_search_engine_id,
                "q": query,
                "num": num_results
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("items", []):
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("link", ""),
                                "snippet": item.get("snippet", ""),
                                "source": "google"
                            })
                        return results
                    else:
                        logger.error(f"Google Search API error: {response.status}")
                        return []

        except Exception as e:
            logger.error(f"Google Search failed: {e}")
            return []

    async def _bing_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Perform Bing Search."""
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {
                "Ocp-Apim-Subscription-Key": self.bing_api_key
            }
            params = {
                "q": query,
                "count": num_results
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("webPages", {}).get("value", []):
                            results.append({
                                "title": item.get("name", ""),
                                "url": item.get("url", ""),
                                "snippet": item.get("snippet", ""),
                                "source": "bing"
                            })
                        return results
                    else:
                        logger.error(f"Bing Search API error: {response.status}")
                        return []

        except Exception as e:
            logger.error(f"Bing Search failed: {e}")
            return []

    async def _duckduckgo_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Perform DuckDuckGo search (no API key required)."""
        try:
            # DuckDuckGo instant answer API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self.headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []

                        # Extract abstract if available
                        if data.get("AbstractText"):
                            results.append({
                                "title": data.get("Heading", "Summary"),
                                "url": data.get("AbstractURL", ""),
                                "snippet": data.get("AbstractText", ""),
                                "source": "duckduckgo"
                            })

                        # Extract related topics
                        for topic in data.get("RelatedTopics", [])[:num_results-1]:
                            if isinstance(topic, dict) and "Text" in topic:
                                results.append({
                                    "title": topic.get("Text", "").split(" - ")[0] if " - " in topic.get("Text", "") else "Related",
                                    "url": topic.get("FirstURL", ""),
                                    "snippet": topic.get("Text", ""),
                                    "source": "duckduckgo"
                                })

                        return results[:num_results]
                    else:
                        logger.error(f"DuckDuckGo API error: {response.status}")
                        return []

        except Exception as e:
            logger.error(f"DuckDuckGo Search failed: {e}")
            return []

    @tool
    async def fetch_url(self, url: str, extract_text: bool = True, follow_redirects: bool = True) -> Dict[str, Any]:
        """
        Fetch content from a URL.

        Args:
            url: URL to fetch
            extract_text: Whether to extract text content (default: True)
            follow_redirects: Whether to follow redirects (default: True)

        Returns:
            Dictionary with fetched content
        """
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {
                    "success": False,
                    "error": "Invalid URL format",
                    "url": url
                }

            # Security check - don't fetch local/internal URLs in production
            if self.environment == "prod":
                if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
                    return {
                        "success": False,
                        "error": "Access to local URLs is not allowed",
                        "url": url
                    }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                    allow_redirects=follow_redirects,
                    max_redirects=5
                ) as response:
                    # Check content size
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self.max_content_size:
                        return {
                            "success": False,
                            "error": f"Content too large: {content_length} bytes (max: {self.max_content_size})",
                            "url": url
                        }

                    # Get content
                    content = await response.text()

                    # Limit content size after download
                    if len(content) > self.max_content_size:
                        content = content[:self.max_content_size]
                        truncated = True
                    else:
                        truncated = False

                    result = {
                        "success": True,
                        "url": str(response.url),  # Final URL after redirects
                        "status_code": response.status,
                        "content_type": response.headers.get("Content-Type", ""),
                        "content_length": len(content),
                        "truncated": truncated
                    }

                    if extract_text:
                        # For HTML, try to extract text content
                        if "text/html" in result["content_type"]:
                            text_content = await self._extract_text_from_html(content)
                            result["text_content"] = text_content
                        else:
                            result["content"] = content

                    logger.info(f"Successfully fetched URL: {url} ({len(content)} bytes)")
                    return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching URL: {url}")
            return {
                "success": False,
                "error": f"Request timeout after {self.timeout} seconds",
                "url": url
            }
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return {
                "success": False,
                "error": f"Failed to fetch URL: {str(e)}",
                "url": url
            }

    async def _extract_text_from_html(self, html: str) -> str:
        """Extract text content from HTML."""
        try:
            # Simple text extraction without BeautifulSoup
            # Remove script and style tags
            import re

            # Remove script and style elements
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

            # Remove HTML tags
            html = re.sub(r'<[^>]+>', ' ', html)

            # Clean up whitespace
            text = ' '.join(html.split())

            return text[:10000]  # Limit text to 10000 characters

        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            return ""

    @tool
    async def extract_links(self, url: str, include_external: bool = True) -> Dict[str, Any]:
        """
        Extract all links from a webpage.

        Args:
            url: URL to extract links from
            include_external: Whether to include external links (default: True)

        Returns:
            Dictionary with extracted links
        """
        try:
            # Fetch the page
            fetch_result = await self.fetch_url(url, extract_text=False)
            if not fetch_result["success"]:
                return fetch_result

            content = fetch_result.get("content", "")
            base_domain = urlparse(url).netloc

            # Simple link extraction using regex
            import re
            link_pattern = re.compile(r'href=[\'"]?([^\'" >]+)', re.IGNORECASE)
            links = link_pattern.findall(content)

            # Process and categorize links
            internal_links = []
            external_links = []

            for link in links:
                # Skip empty links and anchors
                if not link or link.startswith("#"):
                    continue

                # Make absolute URL
                if link.startswith("http://") or link.startswith("https://"):
                    absolute_url = link
                elif link.startswith("//"):
                    absolute_url = "https:" + link
                elif link.startswith("/"):
                    absolute_url = f"{urlparse(url).scheme}://{base_domain}{link}"
                else:
                    continue  # Skip relative paths for now

                # Categorize link
                link_domain = urlparse(absolute_url).netloc
                if link_domain == base_domain:
                    if absolute_url not in internal_links:
                        internal_links.append(absolute_url)
                elif include_external:
                    if absolute_url not in external_links:
                        external_links.append(absolute_url)

            logger.info(f"Extracted {len(internal_links)} internal and {len(external_links)} external links from {url}")

            return {
                "success": True,
                "url": url,
                "internal_links": internal_links[:50],  # Limit to 50 links
                "external_links": external_links[:50] if include_external else [],
                "total_internal": len(internal_links),
                "total_external": len(external_links)
            }

        except Exception as e:
            logger.error(f"Error extracting links from {url}: {e}")
            return {
                "success": False,
                "error": f"Failed to extract links: {str(e)}",
                "url": url
            }

    @tool
    async def check_url_status(self, urls: List[str]) -> Dict[str, Any]:
        """
        Check the status of multiple URLs.

        Args:
            urls: List of URLs to check

        Returns:
            Dictionary with status information for each URL
        """
        try:
            results = []

            async with aiohttp.ClientSession() as session:
                for url in urls[:20]:  # Limit to 20 URLs
                    try:
                        async with session.head(
                            url,
                            headers=self.headers,
                            timeout=10,
                            allow_redirects=True
                        ) as response:
                            results.append({
                                "url": url,
                                "status_code": response.status,
                                "status_text": response.reason,
                                "accessible": 200 <= response.status < 400,
                                "final_url": str(response.url),
                                "content_type": response.headers.get("Content-Type", "")
                            })
                    except asyncio.TimeoutError:
                        results.append({
                            "url": url,
                            "status_code": None,
                            "status_text": "Timeout",
                            "accessible": False,
                            "error": "Request timeout"
                        })
                    except Exception as e:
                        results.append({
                            "url": url,
                            "status_code": None,
                            "status_text": "Error",
                            "accessible": False,
                            "error": str(e)
                        })

            logger.info(f"Checked status for {len(results)} URLs")

            return {
                "success": True,
                "results": results,
                "total_checked": len(results),
                "accessible_count": sum(1 for r in results if r.get("accessible", False))
            }

        except Exception as e:
            logger.error(f"Error checking URL status: {e}")
            return {
                "success": False,
                "error": f"Failed to check URLs: {str(e)}"
            }