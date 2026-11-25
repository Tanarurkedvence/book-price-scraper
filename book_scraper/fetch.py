"""A polite HTTP client for scraping.

* asks robots.txt first and never fetches a disallowed URL;
* waits between requests to the same site (default 0.5 s);
* retries network errors, 429 and 5xx with exponential backoff, and honours
  a Retry-After header;
* identifies itself with a clear User-Agent;
* can keep a disk cache, so re-running while developing does not hit the site again.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

USER_AGENT = "book-price-scraper/1.0 (+https://github.com/Tanarurkedvence/book-price-scraper)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


class Blocked(FetchError):
    """robots.txt does not allow this URL."""


class Fetcher:
    def __init__(self, delay: float = 0.5, retries: int = 3, timeout: float = 20, cache: str | Path | None = None,
                 session: requests.Session | None = None, sleep=time.sleep, clock=time.monotonic, log=None):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.cache = Path(cache) if cache else None
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers["User-Agent"] = USER_AGENT
        self.sleep = sleep
        self.clock = clock
        self.log = log or (lambda message: None)
        self.robots: dict[str, RobotFileParser] = {}
        self.last_request: dict[str, float] = {}
        self.requests = 0

    def _wait_turn(self, host: str) -> None:
        last = self.last_request.get(host)
        if last is not None:
            remaining = self.delay - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self.last_request[host] = self.clock()

    def _robots(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self.robots:
            parser = RobotFileParser()
            try:
                response = self._request(f"{root}/robots.txt")
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:                                     # no robots.txt (404 …) → everything is allowed
                    parser.parse([])
            except FetchError:
                parser.parse([])
            self.robots[root] = parser
        return self.robots[root]

    def _request(self, url: str) -> requests.Response:
        host = urlsplit(url).netloc
        for attempt in range(self.retries + 1):
            self._wait_turn(host)
            self.requests += 1
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as err:
                if attempt == self.retries:
                    raise FetchError(f"{url}: {type(err).__name__}") from err
                wait = 2 ** attempt
            else:
                if response.status_code not in RETRY_STATUS or attempt == self.retries:
                    return response
                retry_after = response.headers.get("Retry-After", "")
                wait = int(retry_after) if retry_after.isdigit() else 2 ** attempt
            self.log(f"retrying in {wait}s: {url}")
            self.sleep(wait)
        raise AssertionError("unreachable")

    def get(self, url: str) -> bytes:
        cached = self.cache / (hashlib.sha1(url.encode()).hexdigest() + ".html") if self.cache else None
        if cached and cached.exists():
            return cached.read_bytes()
        if not self._robots(url).can_fetch(USER_AGENT, url):
            raise Blocked(f"robots.txt does not allow {url}")
        response = self._request(url)
        if response.status_code != 200:
            raise FetchError(f"{url}: HTTP {response.status_code}")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(response.content)
        return response.content
