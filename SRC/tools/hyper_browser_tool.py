# SRC/tools/hyper_browser_tool.py

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

try:
    from crewai_tools import HyperbrowserLoadTool  # type: ignore
except Exception:
    HyperbrowserLoadTool = None


def _j(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _is_allowed_domain(domain: str, allowed_suffixes: List[str]) -> bool:
    if not domain:
        return False
    for suffix in allowed_suffixes:
        suffix = suffix.lower().strip()
        if not suffix:
            continue
        if domain == suffix or domain.endswith("." + suffix):
            return True
    return False


def _infer_intent(query: str) -> str:
    """
    Lightweight intent classification (no LLM).
    """
    q = (query or "").lower()

    nearby_keywords = ["near me", "nearby", "closest", "location", "address", "distance", "map", "में कहाँ", "पास में"]
    if any(k in q for k in nearby_keywords):
        return "nearby"

    contact_keywords = ["contact", "phone", "mobile", "number", "helpline", "call", "office number"]
    if any(k in q for k in contact_keywords):
        return "contact"

    gov_keywords = [
        "scheme", "yojana", "subsidy", "grant",
        "pm kisan", "pm-kisan", "pmfby",
        "insurance scheme", "kisan credit", "kcc",
        "fertilizer subsidy", "solar pump subsidy",
        "eligibility", "application", "apply", "registration",
        "योजना", "सब्सिडी", "सरकारी", "आवेदन", "पात्रता"
    ]
    if any(k in q for k in gov_keywords):
        return "gov_scheme"

    return "general"


def _extract_phone_numbers(text: str, limit: int = 8) -> List[str]:
    if not text:
        return []

    # Supports: +91-9414785280, +91 9414785280, 9414785280, 01482-297173, 01482 297173
    patterns = [
        r"\+91[-\s]?[6-9]\d{9}\b",          # +91 mobile
        r"\b[6-9]\d{9}\b",                  # mobile
        r"\b0?\d{2,5}[-\s]?\d{5,8}\b",      # landline with/without 0
    ]

    nums: List[str] = []
    for p in patterns:
        nums.extend(re.findall(p, text))

    # clean + dedupe
    cleaned: List[str] = []
    seen = set()
    for n in nums:
        n2 = re.sub(r"\s+", "", n.strip())
        if n2.startswith("+91") and len(re.sub(r"\D", "", n2)) < 12:
            # safety: weird partial +91
            continue
        if n2 and n2 not in seen:
            cleaned.append(n.strip())
            seen.add(n2)
        if len(cleaned) >= limit:
            break

    return cleaned



def _build_serper_query(query: str, location_hint: Optional[str], intent: str) -> str:
    """
    Build search query.
    - We do NOT hard-restrict by default; gov_only adds filters later.
    """
    q = _norm(query)
    loc = _norm(location_hint) if location_hint else ""
    parts = [q]
    if loc:
        parts.append(loc)
    return " ".join([p for p in parts if p]).strip()


def _extract_evidence_lines(text: str, intent: str, max_lines: int = 12) -> List[str]:
    if not text:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    keep: List[str] = []

    if intent == "gov_scheme":
        keywords = [
            "eligibility", "benefit", "subsidy", "grant", "apply", "application",
            "registration", "document", "₹", "rs", "%", "last date", "deadline",
            "documents required", "how to apply"
        ]
    elif intent == "nearby":
        keywords = ["address", "timing", "hours", "contact", "phone", "distance", "km", "located", "near", "route"]
    elif intent == "contact":
        keywords = ["contact", "phone", "mobile", "helpline", "call", "email", "address", "office"]
    else:
        keywords = ["price", "date", "how", "what", "when", "official", "notice", "guideline", "₹", "rs", "%", "portal", "login"]

    for l in lines:
        low = l.lower()
        if any(k in low for k in keywords):
            if len(l) <= 240:
                keep.append(l)

    out: List[str] = []
    seen = set()
    for l in keep:
        if l not in seen:
            out.append(l)
            seen.add(l)
        if len(out) >= max_lines:
            break
    return out


def _extract_dates(text: str, limit: int = 12) -> List[str]:
    if not text:
        return []
    patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}\b",
        r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b",
    ]
    hits: List[str] = []
    for p in patterns:
        hits.extend(re.findall(p, text))
    out: List[str] = []
    seen = set()
    for h in hits:
        if h not in seen:
            out.append(h)
            seen.add(h)
        if len(out) >= limit:
            break
    return out


def _looks_like_overlay_garbage(text: str) -> bool:
    """
    Detect JS overlay / login gate / modal-heavy pages that pollute evidence.
    """
    if not text:
        return True
    t = text.lower()
    bad_signals = [
        "something went wrong",
        "you need to sign in",
        "are you sure you want to sign out",
        "you're being redirected",
        "cancel sign in",
        "cancel ok",
        "ok cancel",
        "enter scheme name to search",
    ]
    return any(s in t for s in bad_signals)


def _extract_scheme_candidates_from_serper(raw_serper: dict, limit: int = 10) -> List[Dict[str, str]]:
    """
    Build scheme list directly from Serper titles/snippets.
    """
    out: List[Dict[str, str]] = []
    seen = set()

    organic = raw_serper.get("organic", []) or []
    for item in organic:
        title = (item.get("title") or "").strip()
        link = (item.get("link") or "").strip()
        snippet = (item.get("snippet") or "").strip()

        if not link or not title:
            continue

        key = link.lower()
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "name": title,
            "url": link,
            "source_domain": _domain_of(link),
            "evidence": snippet[:240]
        })

        if len(out) >= limit:
            break

    return out


@dataclass
class _TTLCache:
    ttl_sec: int = 21600
    _store: Dict[str, Tuple[float, Dict[str, Any]]] = field(default_factory=dict)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if now - ts > self.ttl_sec:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = (time.time(), value)


_CACHE = _TTLCache(ttl_sec=int(os.getenv("BROWSE_CACHE_TTL_SEC", "21600")))


@dataclass
class HyperBrowseGeneralTool:
    """
    General-purpose browse tool

    mode:
      - auto: detect intent (general/gov_scheme/nearby/contact), no hard domain restriction
      - gov_only: restrict search results to official-ish domains (gov scheme focused)
      - general: force non-gov behavior even if query contains "scheme" words

    Output:
      - For scheme discovery questions: returns data.schemes list (clean)
      - For contact intent: returns phone_numbers if found
      - Otherwise: returns evidence_lines + pages
    """

    name: str = "hyper_browse_general_tool"
    serper_endpoint: str = "https://google.serper.dev/search"
    timeout_sec: int = 15
    max_chars_per_page: int = 14000

    def run(self, inputs: Optional[Dict[str, Any]] = None) -> str:
        inputs = inputs or {}

        query = inputs.get("query") or inputs.get("question") or inputs.get("text") or ""
        location_hint = inputs.get("location_hint") or inputs.get("location") or inputs.get("state") or None
        mode = (inputs.get("mode") or "auto").strip().lower()

        max_sources_default = int(os.getenv("BROWSE_MAX_SOURCES", "3"))
        max_sources = int(inputs.get("max_sources") or max_sources_default)

        if not query:
            return _j({
                "tool": self.name,
                "status": "missing_data",
                "message": "query is required.",
                "inputs_received": inputs,
                "missing_data": ["query"],
                "data": {},
                "sources": []
            })

        serper_key = os.getenv("SERPER_API_KEY", "").strip()
        if not serper_key:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": "SERPER_API_KEY is required in .env/environment.",
                "inputs_received": inputs,
                "missing_data": ["set_SERPER_API_KEY"],
                "data": {},
                "sources": []
            })

        if HyperbrowserLoadTool is None:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": "HyperbrowserLoadTool not available. Install crewai-tools and hyperbrowser.",
                "inputs_received": inputs,
                "missing_data": ["install_crewai-tools_and_hyperbrowser"],
                "data": {},
                "sources": []
            })

        # --------- FIXED MODE -> INTENT LOGIC ----------
        detected_intent = _infer_intent(query)

        if mode == "general":
            intent = detected_intent if detected_intent != "gov_scheme" else "general"
        elif mode == "gov_only":
            intent = "gov_scheme"
        else:
            intent = detected_intent
        # ---------------------------------------------

        # Build search query (no forced site filters here)
        query_built = _build_serper_query(query=query, location_hint=location_hint, intent=intent)

        cache_key = f"{mode}::{intent}::{_norm(str(location_hint or ''))}::{query_built.lower()}::{max_sources}"
        cached = _CACHE.get(cache_key)
        if cached:
            cached_out = dict(cached)
            cached_out["data"]["cache"] = {"hit": True, "ttl_sec": _CACHE.ttl_sec}
            return _j(cached_out)

        headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}

        # If gov_only mode, bias to official-ish sources
        if mode == "gov_only":
            site_filters = [
                "site:india.gov.in",
                "site:pib.gov.in",
                "site:myscheme.gov.in",
                "site:pmkisan.gov.in",
                "site:fert.gov.in",
                "site:kisan.gov.in",
                "site:agri.gov.in",
                "site:kisan.gov.in",
                "site:icar.org.in",
                "site:nabard.org",
                "site:enam.gov.in",
                "site:agmarknet.gov.in",
                "site:nic.in",
                "site:gov.in",
            ]
            query_for_serper = f"{query_built} ({' OR '.join(site_filters)})"
        else:
            query_for_serper = query_built

        payload = {"q": query_for_serper, "num": 10}

        try:
            resp = requests.post(self.serper_endpoint, headers=headers, json=payload, timeout=self.timeout_sec)
        except requests.RequestException as e:
            out = {
                "tool": self.name,
                "status": "error",
                "message": f"Serper request failed: {type(e).__name__}: {e}",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["serper_request_failed"],
                "data": {"query_used": query_for_serper},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        if resp.status_code != 200:
            out = {
                "tool": self.name,
                "status": "error",
                "message": f"Serper returned HTTP {resp.status_code}.",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["serper_http_error"],
                "data": {"query_used": query_for_serper, "http_status": resp.status_code},
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
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["serper_bad_json"],
                "data": {"query_used": query_for_serper},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        organic = raw.get("organic", []) or []
        all_links: List[str] = []
        for item in organic:
            link = item.get("link") or ""
            if link:
                all_links.append(link)

        if not all_links:
            out = {
                "tool": self.name,
                "status": "missing_data",
                "message": "No sources found from search.",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["no_sources_found"],
                "data": {"query_used": query_for_serper},
                "sources": []
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        # Scheme discovery detection (list schemes cleanly)
        q_lower = (query or "").lower()
        is_scheme_discovery = any(k in q_lower for k in [
            "what scheme", "schemes available", "available scheme", "which scheme",
            "yojana", "subsidy", "government scheme"
        ])

        scheme_candidates = _extract_scheme_candidates_from_serper(raw, limit=10) if is_scheme_discovery else []

        # Init Hyperbrowser
        hb_key = os.getenv("HYPERBROWSER_API_KEY", "").strip()
        if not hb_key:
            out = {
                "tool": self.name,
                "status": "error",
                "message": "HYPERBROWSER_API_KEY is required in .env/environment.",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["set_HYPERBROWSER_API_KEY"],
                "data": {"query_used": query_for_serper},
                "sources": all_links[:max_sources]
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        try:
            hb = HyperbrowserLoadTool(api_key=hb_key)
        except Exception as e:
            out = {
                "tool": self.name,
                "status": "error",
                "message": f"Failed to init HyperbrowserLoadTool: {e}",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": ["check_HYPERBROWSER_API_KEY_and_dependencies"],
                "data": {"query_used": query_for_serper},
                "sources": all_links[:max_sources]
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        # Progressive browsing: skip overlay garbage and collect GOOD pages
        chosen: List[str] = []
        pages: List[Dict[str, Any]] = []
        combined_text_parts: List[str] = []

        for link in all_links[:20]:
            if len(chosen) >= max_sources:
                break

            try:
                content = hb.run(url=link, operation="scrape")
                content = (content or "")[: self.max_chars_per_page]

                if _looks_like_overlay_garbage(content):
                    pages.append({
                        "url": link,
                        "status": "skipped",
                        "domain": _domain_of(link),
                        "reason": "overlay_or_login_garbage_detected",
                        "content_excerpt": content[:400],
                    })
                    continue

                chosen.append(link)
                pages.append({
                    "url": link,
                    "status": "ok",
                    "domain": _domain_of(link),
                    "content_excerpt": content[:1200],
                })
                combined_text_parts.append(content)

            except Exception as e:
                pages.append({
                    "url": link,
                    "status": "error",
                    "domain": _domain_of(link),
                    "error": f"{type(e).__name__}: {e}",
                    "content_excerpt": "",
                })

        combined_text = "\n\n".join([t for t in combined_text_parts if t]).strip()

        # If scheme discovery: return clean schemes list + pages debug
        if is_scheme_discovery and scheme_candidates:
            out = {
                "tool": self.name,
                "status": "ok",
                "message": "Found scheme options from search results (evidence-based).",
                "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                "missing_data": [],
                "data": {
                    "intent": intent,
                    "query_used": query_for_serper,
                    "schemes": scheme_candidates[:10],
                    "pages": pages,
                    "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec},
                },
                "sources": [s["url"] for s in scheme_candidates[:10]],
            }
            _CACHE.set(cache_key, out)
            return _j(out)

        # ---------- CONTACT INTENT HANDLING (IMPROVED) ----------
        phones = _extract_phone_numbers(combined_text)

        if intent == "contact":
            if phones:
                out = {
                    "tool": self.name,
                    "status": "ok",
                    "message": "Contact details found from public sources.",
                    "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                    "missing_data": [],
                    "data": {
                        "intent": "contact",
                        "phone_numbers": phones,
                        "pages": pages,
                        "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec}
                    },
                    "sources": chosen
                }
                _CACHE.set(cache_key, out)
                return _j(out)
            else:
                out = {
                    "tool": self.name,
                    "status": "missing_data",
                    "message": "Contact intent detected but phone number not found in scraped pages.",
                    "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
                    "missing_data": ["phone_number_not_found_try_more_sources_or_different_query"],
                    "data": {
                        "intent": "contact",
                        "pages": pages,
                        "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec}
                    },
                    "sources": chosen
                }
                _CACHE.set(cache_key, out)
                return _j(out)
        # ---------- END CONTACT HANDLING ----------

        # Otherwise evidence extraction
        evidence = _extract_evidence_lines(combined_text, intent=intent, max_lines=12)
        dates = _extract_dates(combined_text, limit=12)

        missing: List[str] = []
        if not combined_text:
            missing.append("no_text_extracted_from_pages")
        if not evidence:
            missing.append("no_clear_evidence_lines_found")
        if not chosen:
            missing.append("all_pages_skipped_or_failed")

        status = "ok" if not missing else "missing_data"

        out = {
            "tool": self.name,
            "status": status,
            "message": "Browsed sources and extracted evidence (no fabrication).",
            "inputs_received": {"query": query, "location_hint": location_hint, "mode": mode},
            "missing_data": missing,
            "data": {
                "intent": intent,
                "query_used": query_for_serper,
                "evidence_lines": evidence,
                "date_mentions": dates,
                "pages": pages,
                "cache": {"hit": False, "ttl_sec": _CACHE.ttl_sec},
            },
            "sources": chosen
        }

        _CACHE.set(cache_key, out)
        return _j(out)
