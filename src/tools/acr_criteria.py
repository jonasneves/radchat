"""
ACR Appropriateness Criteria Tool - Clinical decision support for imaging.
Fetches cached data from GitHub data branch, falls back to live topic search.
Cache is updated weekly via GitHub Action.
"""

import json
import os
import re
from functools import lru_cache
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://acsearch.acr.org"
CACHE_URL = "https://raw.githubusercontent.com/jonasneves/radchat/data/src/data/acr_criteria.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}

BODY_REGION_KEYWORDS = {
    "head": ["head", "brain", "cranial", "intracranial", "skull", "headache", "stroke"],
    "neck": ["neck", "cervical", "thyroid", "carotid"],
    "spine": ["spine", "spinal", "vertebr", "lumbar", "thoracic", "back pain"],
    "chest": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart"],
    "abdomen": ["abdomen", "liver", "pancrea", "kidney", "renal", "bowel", "hepat"],
    "pelvis": ["pelvis", "bladder", "prostate", "uterus", "ovary", "pregnancy"],
    "msk": ["musculoskeletal", "bone", "joint", "shoulder", "knee", "fracture"],
    "vascular": ["vascular", "aorta", "artery", "vein", "dvt", "embolism", "aneurysm"],
    "breast": ["breast", "mammary"],
}


def extract_body_regions(title: str) -> list[str]:
    """Extract body regions from topic title."""
    title_lower = title.lower()
    return [r for r, kws in BODY_REGION_KEYWORDS.items() if any(kw in title_lower for kw in kws)]


@lru_cache(maxsize=1)
def load_cache() -> Optional[dict]:
    """Fetch cached ACR data from GitHub data branch."""
    try:
        response = requests.get(CACHE_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None


@lru_cache(maxsize=1)
def fetch_topics_live() -> list[dict]:
    """Fetch topic list from ACR website (fallback when no cache)."""
    try:
        response = requests.get(f"{BASE_URL}/list", headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    topics = {}

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "TopicId=" in href and "TopicName=" in href:
            id_match = re.search(r"TopicId=(\d+)", href)
            name_match = re.search(r"TopicName=([^&]+)", href)
            if id_match and name_match:
                topic_id = id_match.group(1)
                topic_name = unquote(name_match.group(1)).replace("+", " ")
                if topic_id not in topics:
                    topics[topic_id] = topic_name

    return [
        {
            "id": tid,
            "title": tname,
            "body_regions": extract_body_regions(tname),
            "url": f"{BASE_URL}/docs/{tid}/Narrative/",
        }
        for tid, tname in sorted(topics.items(), key=lambda x: x[1])
    ]


def get_topics() -> tuple[list[dict], bool]:
    """Get topics from cache or live. Returns (topics, is_cached)."""
    cache = load_cache()
    if cache and cache.get("topics"):
        topics = list(cache["topics"].values())
        return topics, True
    return fetch_topics_live(), False


def search_topics(query: str, body_region: Optional[str] = None) -> dict:
    """Search topics by query and optional body region."""
    topics, is_cached = get_topics()

    if not topics:
        return {
            "error": "Unable to fetch ACR topics.",
            "fallback_url": f"{BASE_URL}/list",
        }

    query_lower = query.lower()
    query_words = query_lower.split()

    results = []
    for topic in topics:
        title_lower = topic.get("title", "").lower()

        # Score matching
        if query_lower in title_lower:
            score = 100
        elif all(word in title_lower for word in query_words):
            score = 50
        elif any(word in title_lower for word in query_words if len(word) > 3):
            score = 10
        else:
            continue

        # Body region filter
        if body_region and body_region not in topic.get("body_regions", []):
            continue

        results.append({**topic, "_score": score})

    results.sort(key=lambda t: (-t["_score"], len(t.get("title", ""))))
    for r in results:
        del r["_score"]

    return {
        "results": results[:10],
        "total_matches": len(results),
        "cached": is_cached,
    }


def get_imaging_recommendations(
    clinical_scenario: str,
    body_region: Optional[str] = None,
) -> dict:
    """Get imaging recommendations for a clinical scenario."""
    search_result = search_topics(clinical_scenario, body_region)

    if "error" in search_result:
        return search_result

    if not search_result["results"]:
        return {
            "found": False,
            "query": clinical_scenario,
            "message": f"No ACR criteria found for '{clinical_scenario}'.",
            "suggestions": [
                "Try specific clinical terms (e.g., 'suspected pulmonary embolism')",
                "Use symptom descriptions (e.g., 'acute chest pain', 'headache')",
            ],
            "browse_url": f"{BASE_URL}/list",
        }

    topic = search_result["results"][0]
    is_cached = search_result["cached"]

    response = {
        "found": True,
        "topic": topic.get("title"),
        "url": topic.get("url"),
        "body_regions": topic.get("body_regions", []),
    }

    # Include detailed recommendations if we have cached data
    summary = topic.get("summary", {})
    if summary.get("first_line"):
        response["first_line_imaging"] = summary["first_line"]
    if summary.get("alternatives"):
        response["alternatives"] = summary["alternatives"]
    if summary.get("avoid"):
        response["usually_not_appropriate"] = summary["avoid"]
    if summary.get("special_considerations"):
        response["special_considerations"] = summary["special_considerations"]

    # Include variant descriptions if available
    variants = topic.get("variants", [])
    if variants:
        response["clinical_variants"] = [
            v.get("description") or f"Variant {v.get('number')}"
            for v in variants[:3]
            if v.get("description") or v.get("procedures")
        ]
        response["total_procedures_evaluated"] = summary.get("total_procedures", 0)

    # If no detailed data, add instruction to visit URL
    if not summary.get("first_line"):
        response["instructions"] = "View the ACR website for detailed appropriateness ratings."

    # Related topics
    if len(search_result["results"]) > 1:
        response["related_topics"] = [
            {"title": t.get("title"), "url": t.get("url")}
            for t in search_result["results"][1:5]
        ]

    return response


def list_topics_by_region(body_region: str) -> dict:
    """List all ACR topics for a body region."""
    topics, is_cached = get_topics()

    if not topics:
        return {"error": "Unable to fetch topics"}

    filtered = [t for t in topics if body_region in t.get("body_regions", [])]

    return {
        "body_region": body_region,
        "topics": [{"title": t.get("title"), "url": t.get("url")} for t in filtered],
        "total": len(filtered),
        "cached": is_cached,
    }


# Tool definitions
ACR_CRITERIA_TOOLS = [
    {
        "name": "get_imaging_recommendations",
        "description": """Find ACR Appropriateness Criteria topics for a clinical scenario.

Returns the most relevant ACR guideline topic with a link to view detailed recommendations.
ACR scores range from 1-9: Usually Appropriate (7-9), May Be Appropriate (4-6), Usually Not Appropriate (1-3).

Use when clinicians ask about appropriate imaging for symptoms or conditions.
Examples: "suspected pulmonary embolism", "acute chest pain", "headache", "low back pain".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinical_scenario": {
                    "type": "string",
                    "description": "Clinical scenario (e.g., 'suspected pulmonary embolism', 'acute low back pain')",
                },
                "body_region": {
                    "type": "string",
                    "description": "Optional body region filter",
                    "enum": ["head", "neck", "spine", "chest", "abdomen", "pelvis", "msk", "vascular", "breast"],
                },
            },
            "required": ["clinical_scenario"],
        },
    },
    {
        "name": "list_acr_topics",
        "description": "List all ACR Appropriateness Criteria topics for a body region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "body_region": {
                    "type": "string",
                    "description": "Body region",
                    "enum": ["head", "neck", "spine", "chest", "abdomen", "pelvis", "msk", "vascular", "breast"],
                },
            },
            "required": ["body_region"],
        },
    },
]


def execute_acr_tool(name: str, args: dict) -> dict:
    """Execute an ACR criteria tool."""
    if name == "get_imaging_recommendations":
        return get_imaging_recommendations(
            args.get("clinical_scenario", ""),
            args.get("body_region"),
        )
    elif name == "search_acr_criteria":
        return get_imaging_recommendations(args.get("query", ""), args.get("body_region"))
    elif name == "list_acr_topics":
        body_region = args.get("body_region")
        if body_region:
            return list_topics_by_region(body_region)
        topics, _ = get_topics()
        return {"topics": [{"title": t.get("title"), "url": t.get("url")} for t in topics[:30]], "total": len(topics)}
    elif name == "get_acr_topic_details":
        return get_imaging_recommendations(args.get("topic_id", ""))
    return {"error": f"Unknown tool: {name}"}
