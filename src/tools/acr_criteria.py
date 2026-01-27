"""
ACR Appropriateness Criteria Tool - Clinical decision support for imaging
"""

import re
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://acsearch.acr.org"

MODALITY_KEYWORDS = {
    "ct": ["ct ", "ct,", "computed tomography", "cta"],
    "mri": ["mri", "mr ", "magnetic resonance", "mra", "mrcp"],
    "us": ["ultrasound", "us ", "sonograph", "doppler"],
    "xray": ["x-ray", "xray", "radiograph", "plain film"],
    "nuclear": ["pet", "spect", "scintigraphy", "nuclear", "bone scan"],
    "fluoroscopy": ["fluoroscop", "barium", "swallow study"],
    "mammography": ["mammograph", "breast imaging"],
}

BODY_REGION_KEYWORDS = {
    "head": ["head", "brain", "cranial", "intracranial", "skull", "headache"],
    "neck": ["neck", "cervical spine", "thyroid", "carotid"],
    "spine": ["spine", "spinal", "lumbar", "thoracic", "back pain"],
    "chest": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart"],
    "abdomen": ["abdomen", "liver", "pancrea", "kidney", "renal", "bowel"],
    "pelvis": ["pelvis", "pelvic", "bladder", "prostate", "uterus", "ovary"],
    "msk": ["musculoskeletal", "bone", "joint", "shoulder", "knee", "fracture"],
    "vascular": ["vascular", "aorta", "artery", "vein", "dvt", "embolism"],
    "breast": ["breast", "mammary"],
}

APPROPRIATENESS_LEVELS = {
    "usually_appropriate": {"range": (7, 9), "label": "Usually Appropriate"},
    "may_be_appropriate": {"range": (4, 6), "label": "May Be Appropriate"},
    "usually_not_appropriate": {"range": (1, 3), "label": "Usually Not Appropriate"},
}

_topic_cache: Optional[list] = None


def extract_modalities(text: str) -> list[str]:
    text_lower = text.lower()
    return [k for k, keywords in MODALITY_KEYWORDS.items() if any(kw in text_lower for kw in keywords)]


def extract_body_regions(text: str) -> list[str]:
    text_lower = text.lower()
    return [k for k, keywords in BODY_REGION_KEYWORDS.items() if any(kw in text_lower for kw in keywords)]


def parse_score(text: str) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"\b([1-9])\b", text)
    if match:
        return int(match.group(1))
    text_lower = text.lower()
    if "usually appropriate" in text_lower:
        return 8
    if "may be appropriate" in text_lower:
        return 5
    if "usually not appropriate" in text_lower:
        return 2
    return None


def get_level(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    for key, data in APPROPRIATENESS_LEVELS.items():
        if data["range"][0] <= score <= data["range"][1]:
            return key
    return None


def get_level_label(score: Optional[int]) -> str:
    level = get_level(score)
    return APPROPRIATENESS_LEVELS.get(level, {}).get("label", "Unknown") if level else "Unknown"


def fetch_topics() -> list[dict]:
    """Fetch all ACR topics from the main list."""
    global _topic_cache
    if _topic_cache is not None:
        return _topic_cache

    url = f"{BASE_URL}/list"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

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

    result = [
        {
            "id": tid,
            "title": tname,
            "modalities": extract_modalities(tname),
            "body_regions": extract_body_regions(tname),
        }
        for tid, tname in sorted(topics.items(), key=lambda x: x[1])
    ]

    _topic_cache = result
    return result


def fetch_topic_details(topic_id: str) -> dict:
    """Fetch detailed appropriateness criteria for a topic."""
    list_url = f"{BASE_URL}/list"
    response = requests.get(list_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find topic URL
    topic_url = None
    topic_title = None
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if f"TopicId={topic_id}" in href:
            name_match = re.search(r"TopicName=([^&]+)", href)
            if name_match:
                topic_title = unquote(name_match.group(1)).replace("+", " ")
            parent = link.find_parent(["tr", "div", "li"])
            if parent:
                for a in parent.find_all("a", href=True):
                    if "/docs/" in a.get("href", ""):
                        topic_url = a["href"]
                        if not topic_url.startswith("http"):
                            topic_url = f"{BASE_URL}{topic_url}"
                        break
            break

    if not topic_url:
        topic_url = f"{BASE_URL}/docs/{topic_id}/Narrative/"

    response = requests.get(topic_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Parse procedure tables
    procedures = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header = rows[0].get_text(strip=True).lower()
        if "procedure" not in header and "appropriateness" not in header:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            name = cells[0].get_text(strip=True)
            if not name or name.lower() in ("procedure", "radiologic procedure"):
                continue

            appropriateness_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            score = parse_score(appropriateness_text)

            procedures.append({
                "name": name,
                "score": score,
                "level": get_level_label(score),
                "modalities": extract_modalities(name),
            })

    return {
        "topic_id": topic_id,
        "title": topic_title,
        "url": topic_url,
        "procedures": procedures,
    }


def search_criteria(
    query: str,
    modality: Optional[str] = None,
    body_region: Optional[str] = None,
) -> dict:
    """Search ACR Appropriateness Criteria topics."""
    topics = fetch_topics()
    query_lower = query.lower() if query else ""

    results = []
    for topic in topics:
        if query_lower and query_lower not in topic["title"].lower():
            continue
        if modality and modality not in topic["modalities"]:
            continue
        if body_region and body_region not in topic["body_regions"]:
            continue
        results.append(topic)

    return {
        "results": results[:15],
        "total_matches": len(results),
        "query": query,
    }


# Tool definitions for Claude
ACR_CRITERIA_TOOLS = [
    {
        "name": "search_acr_criteria",
        "description": "Search ACR Appropriateness Criteria for imaging guidance. Use this when a clinician asks about appropriate imaging for a clinical scenario. Returns topics with appropriateness guidance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Clinical scenario or search term (e.g., 'acute chest pain', 'headache', 'abdominal trauma', 'pulmonary embolism')",
                },
                "modality": {
                    "type": "string",
                    "description": "Filter by imaging modality",
                    "enum": ["ct", "mri", "us", "xray", "nuclear", "fluoroscopy", "mammography"],
                },
                "body_region": {
                    "type": "string",
                    "description": "Filter by body region",
                    "enum": ["head", "neck", "spine", "chest", "abdomen", "pelvis", "msk", "vascular", "breast"],
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_acr_topic_details",
        "description": "Get detailed appropriateness ratings for a specific ACR topic. Returns all procedures with their appropriateness scores (1-9).",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "ACR topic ID from search results",
                },
            },
            "required": ["topic_id"],
        },
    },
    {
        "name": "list_acr_topics",
        "description": "List all available ACR Appropriateness Criteria topics. Use when browsing or when the clinical scenario is unclear.",
        "input_schema": {
            "type": "object",
            "properties": {
                "body_region": {
                    "type": "string",
                    "description": "Filter by body region",
                    "enum": ["head", "neck", "spine", "chest", "abdomen", "pelvis", "msk", "vascular", "breast"],
                },
            },
        },
    },
]


def execute_acr_tool(name: str, args: dict) -> dict:
    """Execute an ACR criteria tool."""
    if name == "search_acr_criteria":
        return search_criteria(
            args.get("query", ""),
            args.get("modality"),
            args.get("body_region"),
        )
    elif name == "get_acr_topic_details":
        return fetch_topic_details(args.get("topic_id", ""))
    elif name == "list_acr_topics":
        topics = fetch_topics()
        body_region = args.get("body_region")
        if body_region:
            topics = [t for t in topics if body_region in t["body_regions"]]
        return {"topics": topics[:30], "total": len(topics)}
    else:
        return {"error": f"Unknown tool: {name}"}
