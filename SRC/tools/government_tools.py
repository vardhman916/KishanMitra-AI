# SRC/tools/government_tools.py

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()


def _j(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        # remove leading www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _is_allowed_domain(domain: str, allowed_suffixes: List[str]) -> bool:
    """
    Allowed if:
      - domain == suffix OR
      - domain ends with ".suffix"
    Example:
      domain="pmkisan.gov.in" suffix="gov.in" -> allowed
    """
    if not domain:
        return False
    for suffix in allowed_suffixes:
        suffix = suffix.lower().strip()
        if not suffix:
            continue
        if domain == suffix or domain.endswith("." + suffix):
            return True
    return False


def _build_serper_query(
    user_query: str,
    state: Optional[str],
    crop: Optional[str],
    category: str,
    allowed_suffixes: List[str],
) -> str:
    """
    Build a high-signal query with domain restrictions.
    We use "site:" with a few top domains + a broad gov.in suffix.

    category can be:
      - "scheme"  -> find scheme pages
      - "apply"   -> application portals/how to apply
      - "update"  -> PIB updates
      - "general" -> fallback
    """
    parts: List[str] = []

    uq = _norm(user_query)
    st = _norm(state) if state else ""
    cp = _norm(crop) if crop else ""

    if category == "scheme":
        parts.append("farmer scheme subsidy")
    elif category == "apply":
        parts.append("how to apply registration official portal")
    elif category == "update":
        parts.append("latest update announcement")
    else:
        parts.append("farmer scheme")

    if cp:
        parts.append(cp)
    if st:
        parts.append(st)

    if uq:
        parts.append(uq)

    # Stronger domain targeting
    # We keep it small to avoid overly restrictive searches.
    site_filters = [
        "site:myscheme.gov.in",
        "site:pib.gov.in",
        "site:india.gov.in",
        "site:gov.in",
    ]
    parts.append("(" + " OR ".join(site_filters) + ")")

    return " ".join([p for p in parts if p]).strip()


@dataclass
class _TTLCache:
    ttl_sec: int = 86400  # default 24h
    _store: Dict[str, Tuple[float, Dict[str, Any]]] = field(default_factory=dict)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if now - ts > self.ttl_sec:
            # expired
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = (time.time(), value)


_CACHE = _TTLCache(ttl_sec=int(os.getenv("GOV_SCHEME_CACHE_TTL_SEC", "86400")))


@dataclass
class GovernmentSchemeTool:
    """
    Government Scheme Tool using Serper (Google Search API) with official-domain filtering.

    Inputs:
      - query: free text like "subsidy for drip irrigation" or "pm kisan"
      - state: optional (India state)
      - crop: optional
      - category: optional ["scheme","apply","update","general"] (default "scheme")
      - max_results: optional (default 10)

    Env:
      - SERPER_API_KEY (required)
      - GOV_ALLOWED_DOMAINS (optional, comma-separated suffixes)
          default: "myscheme.gov.in,gov.in,nic.in,pib.gov.in,india.gov.in"
      - GOV_SCHEME_CACHE_TTL_SEC (optional) default 86400 (24 hours)
    """

    name: str = "government_scheme_tool"
    endpoint: str = "https://google.serper.dev/search"
    timeout_sec: int = 12

    def run(self, inputs: Optional[Dict[str, Any]] = None) -> str:
        inputs = inputs or {}
        user_query = inputs.get("query") or inputs.get("question") or inputs.get("text") or ""
        state = inputs.get("state")
        crop = inputs.get("crop")
        category = (inputs.get("category") or "scheme").strip().lower()
        max_results = int(inputs.get("max_results") or 10)

        if not user_query and not (state or crop):
            return _j({
                "tool": self.name,
                "status": "missing_data",
                "message": "Provide at least `query` (recommended), or `state/crop` context.",
                "inputs_received": inputs,
                "missing_data": ["query"],
                "data": {},
                "sources": []
            })

        api_key = os.getenv("SERPER_API_KEY", "").strip()
        if not api_key:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": "SERPER_API_KEY is required in .env/environment.",
                "inputs_received": inputs,
                "missing_data": ["set_SERPER_API_KEY"],
                "data": {},
                "sources": []
            })

        # Domain suffix whitelist
        allowed_suffixes_str = os.getenv(
            "GOV_ALLOWED_DOMAINS",
            "myscheme.gov.in,gov.in,nic.in,pib.gov.in,india.gov.in"
        )
        allowed_suffixes = [x.strip().lower() for x in allowed_suffixes_str.split(",") if x.strip()]

        query_built = _build_serper_query(
            user_query=str(user_query),
            state=state,
            crop=crop,
            category=category,
            allowed_suffixes=allowed_suffixes
        )

        # Cache key
        cache_key = f"{category}::{_norm(str(state or ''))}::{_norm(str(crop or ''))}::{query_built.lower()}"
        cached = _CACHE.get(cache_key)
        if cached:
            cached_out = dict(cached)
            cached_out["data"]["cache"] = {"hit": True, "ttl_sec": _CACHE.ttl_sec}
            return _j(cached_out)

        payload = {"q": query_built, "num": max_results}
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        try:
            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout_sec)
        except requests.RequestException as e:
            out = {
                "tool": self.name,
                "status": "error",
                "message": f"Serper request failed: {type(e).__name__}: {e}",
                "inputs_received": {
                    "query": user_query, "state": state, "crop": crop,
                    "category": category, "max_results": max_results
                },
                "missing_data": ["serper_request_failed"],
                "data": {"query_used": query_built},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        if resp.status_code != 200:
            out = {
                "tool": self.name,
                "status": "error",
                "message": f"Serper returned HTTP {resp.status_code}.",
                "inputs_received": {
                    "query": user_query, "state": state, "crop": crop,
                    "category": category, "max_results": max_results
                },
                "missing_data": ["serper_http_error"],
                "data": {"query_used": query_built, "http_status": resp.status_code},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        try:
            raw = resp.json()
        except Exception:
            out = {
                "tool": self.name,
                "status": "error",
                "message": "Serper response was not valid JSON.",
                "inputs_received": {
                    "query": user_query, "state": state, "crop": crop,
                    "category": category, "max_results": max_results
                },
                "missing_data": ["serper_bad_json"],
                "data": {"query_used": query_built},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        # Extract organic results
        organic = raw.get("organic", []) or []
        results: List[Dict[str, Any]] = []
        sources: List[str] = []

        def categorize(domain: str, title: str, snippet: str) -> str:
            text = f"{title} {snippet}".lower()
            if "pib.gov.in" in domain:
                return "update"
            if any(k in text for k in ["apply", "registration", "portal", "login", "beneficiary"]):
                return "portal"
            return "scheme"

        def confidence(domain: str) -> str:
            # high trust sources
            if domain in ("myscheme.gov.in", "pib.gov.in", "india.gov.in"):
                return "high"
            if domain.endswith(".gov.in") or domain == "gov.in":
                return "high"
            if domain.endswith(".nic.in") or domain == "nic.in":
                return "medium"
            return "low"

        for item in organic:
            link = item.get("link") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""

            dom = _domain_of(link)
            if not _is_allowed_domain(dom, allowed_suffixes):
                continue

            cat = categorize(dom, title, snippet)
            conf = confidence(dom)

            results.append({
                "title": title,
                "link": link,
                "snippet": snippet,
                "source_domain": dom,
                "category": cat,
                "confidence": conf
            })
            sources.append(link)

        # If not enough official results, return missing_data
        if len(results) < 2:
            out = {
                "tool": self.name,
                "status": "missing_data",
                "message": "No sufficient official government sources found via search. Try a more specific scheme name or keywords.",
                "inputs_received": {
                    "query": user_query, "state": state, "crop": crop,
                    "category": category, "max_results": max_results
                },
                "missing_data": ["no_official_sources_found"],
                "data": {
                    "query_used": query_built,
                    "filters": {"allowed_domains": allowed_suffixes},
                    "results": results,
                    "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec}
                },
                "sources": sources
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        out = {
            "tool": self.name,
            "status": "ok",
            "message": "Government scheme sources fetched successfully (official domains filtered).",
            "inputs_received": {
                "query": user_query, "state": state, "crop": crop,
                "category": category, "max_results": max_results
            },
            "missing_data": [],
            "data": {
                "query_used": query_built,
                "filters": {"allowed_domains": allowed_suffixes},
                "results": results[:max_results],
                "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec}
            },
            "sources": sources[:max_results]
        }
        _CACHE.set(cache_key, out)
        return _j(out)
