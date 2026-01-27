"""
ACR Appropriateness Criteria Tool - Clinical decision support for imaging.
Fetches topic list from ACR website. Detail pages require browser access.
"""

import re
from functools import lru_cache
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://acsearch.acr.org"

# Browser-like headers for requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}

# Body region keywords for classification
BODY_REGION_KEYWORDS = {
    "head": ["head", "brain", "cranial", "intracranial", "skull", "orbit", "headache", "stroke", "seizure"],
    "neck": ["neck", "cervical", "thyroid", "carotid", "larynx"],
    "spine": ["spine", "spinal", "vertebr", "lumbar", "thoracic", "back pain", "radiculopathy"],
    "chest": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart", "dyspnea", "cough"],
    "abdomen": ["abdomen", "liver", "pancrea", "kidney", "renal", "bowel", "hepat", "biliary"],
    "pelvis": ["pelvis", "bladder", "prostate", "uterus", "ovary", "pregnancy", "obstetric"],
    "msk": ["musculoskeletal", "bone", "joint", "shoulder", "knee", "fracture", "extremity", "trauma"],
    "vascular": ["vascular", "aorta", "artery", "vein", "dvt", "embolism", "aneurysm", "claudication"],
    "breast": ["breast", "mammary", "axilla"],
}


def extract_body_regions(title: str) -> list[str]:
    """Extract body regions from topic title."""
    title_lower = title.lower()
    regions = []
    for region, keywords in BODY_REGION_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            regions.append(region)
    return regions


@lru_cache(maxsize=1)
def fetch_topics() -> list[dict]:
    """Fetch all ACR topics from the main list page."""
    try:
        response = requests.get(f"{BASE_URL}/list", headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
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

    # Also extract direct doc links for URLs
    doc_urls = {}
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/docs/" in href and "Narrative" in href:
            # Extract topic ID from URL like /docs/12345/Narrative/
            match = re.search(r"/docs/(\d+)/", href)
            if match:
                doc_urls[match.group(1)] = BASE_URL + href if href.startswith("/") else href

    result = []
    for tid, tname in sorted(topics.items(), key=lambda x: x[1]):
        result.append({
            "id": tid,
            "title": tname,
            "body_regions": extract_body_regions(tname),
            "url": doc_urls.get(tid, f"{BASE_URL}/docs/{tid}/Narrative/"),
        })

    return result


def search_criteria(
    query: str,
    body_region: Optional[str] = None,
) -> dict:
    """
    Search ACR Appropriateness Criteria topics.

    Returns matching topics with URLs to full criteria on ACR website.
    """
    topics = fetch_topics()

    if not topics:
        return {
            "error": "Unable to fetch ACR topics. The ACR website may be temporarily unavailable.",
            "fallback_url": f"{BASE_URL}/list",
        }

    query_lower = query.lower() if query else ""
    query_words = query_lower.split()

    results = []
    for topic in topics:
        title_lower = topic["title"].lower()

        # Match: full query in title OR all query words in title
        if query_lower in title_lower:
            score = 100  # Exact match
        elif all(word in title_lower for word in query_words):
            score = 50  # All words match
        elif any(word in title_lower for word in query_words if len(word) > 3):
            score = 10  # Partial match
        else:
            continue

        # Filter by body region if specified
        if body_region and body_region not in topic.get("body_regions", []):
            continue

        results.append({**topic, "_score": score})

    # Sort by relevance score, then by title length (shorter = more specific)
    results.sort(key=lambda t: (-t["_score"], len(t["title"])))

    # Remove internal score from output
    for r in results:
        del r["_score"]

    return {
        "query": query,
        "body_region": body_region,
        "results": results[:10],
        "total_matches": len(results),
        "note": "Click the URL to view full appropriateness ratings on ACR website.",
    }


def get_imaging_recommendations(
    clinical_scenario: str,
    body_region: Optional[str] = None,
) -> dict:
    """
    Search ACR criteria for a clinical scenario.
    Returns matching topics with links to full criteria.
    """
    result = search_criteria(clinical_scenario, body_region)

    if "error" in result:
        return result

    if not result["results"]:
        return {
            "found": False,
            "query": clinical_scenario,
            "message": f"No ACR criteria found for '{clinical_scenario}'.",
            "suggestions": [
                "Try more specific clinical terms (e.g., 'suspected pulmonary embolism')",
                "Use common symptom descriptions (e.g., 'acute chest pain', 'headache')",
                "Browse by body region using the body_region filter",
            ],
            "browse_url": f"{BASE_URL}/list",
        }

    # Format response
    topics = result["results"]
    primary = topics[0]

    response = {
        "found": True,
        "topic": primary["title"],
        "url": primary["url"],
        "body_regions": primary.get("body_regions", []),
        "instructions": "View the ACR website for detailed appropriateness ratings (1-9 scale), radiation levels, and clinical variants.",
    }

    if len(topics) > 1:
        response["related_topics"] = [
            {"title": t["title"], "url": t["url"]}
            for t in topics[1:5]
        ]

    return response


def list_topics_by_region(body_region: str) -> dict:
    """List all ACR topics for a body region."""
    topics = fetch_topics()

    if not topics:
        return {"error": "Unable to fetch topics"}

    filtered = [t for t in topics if body_region in t.get("body_regions", [])]

    return {
        "body_region": body_region,
        "topics": [{"title": t["title"], "url": t["url"]} for t in filtered],
        "total": len(filtered),
    }


# Tool definitions
ACR_CRITERIA_TOOLS = [
    {
        "name": "get_imaging_recommendations",
        "description": """Search ACR Appropriateness Criteria for imaging guidance.

Returns matching ACR topics with links to view full criteria including:
- Appropriateness ratings (1-9 scale)
- Radiation levels
- Clinical variants and special populations

Use when clinicians ask about appropriate imaging for symptoms or conditions.
Examples: "suspected pulmonary embolism", "acute chest pain", "headache", "low back pain".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinical_scenario": {
                    "type": "string",
                    "description": "Clinical scenario or condition (e.g., 'suspected pulmonary embolism', 'acute low back pain')",
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
        "description": "List all ACR Appropriateness Criteria topics for a body region. Use when browsing or when the clinical scenario is unclear.",
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
        # Backwards compatibility
        return get_imaging_recommendations(
            args.get("query", ""),
            args.get("body_region"),
        )
    elif name == "list_acr_topics":
        body_region = args.get("body_region")
        if body_region:
            return list_topics_by_region(body_region)
        topics = fetch_topics()
        return {
            "topics": [{"title": t["title"], "url": t["url"]} for t in topics[:30]],
            "total": len(topics),
        }
    elif name == "get_acr_topic_details":
        # Backwards compatibility - redirect to search
        return get_imaging_recommendations(args.get("topic_id", ""))
    return {"error": f"Unknown tool: {name}"}
