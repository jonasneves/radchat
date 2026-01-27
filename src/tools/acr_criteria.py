"""
ACR Appropriateness Criteria Tool - Clinical decision support for imaging
Full implementation with radiation levels, contrast info, and variant parsing.
"""

import re
from functools import lru_cache
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://acsearch.acr.org"

# Configuration-driven thresholds and mappings
CONFIG = {
    "appropriateness_levels": {
        "usually_appropriate": {
            "range": (7, 9),
            "label": "Usually Appropriate",
            "description": "The imaging procedure is indicated at a favorable risk-benefit ratio.",
        },
        "may_be_appropriate": {
            "range": (4, 6),
            "label": "May Be Appropriate",
            "description": "The imaging procedure may be indicated as an alternative or when initial imaging is nondiagnostic.",
        },
        "usually_not_appropriate": {
            "range": (1, 3),
            "label": "Usually Not Appropriate",
            "description": "The imaging procedure is unlikely to be indicated, or the risk-benefit ratio is unfavorable.",
        },
    },
    "modalities": {
        "ct": {"label": "CT", "keywords": ["ct ", "ct,", "computed tomography", "cta", "ct angiography"]},
        "mri": {"label": "MRI", "keywords": ["mri", "mr ", "magnetic resonance", "mra", "mrcp"]},
        "us": {"label": "Ultrasound", "keywords": ["ultrasound", "us ", "sonograph", "doppler", "echocardiograph"]},
        "xray": {"label": "X-ray", "keywords": ["x-ray", "xray", "radiograph", "plain film", "chest film"]},
        "nuclear": {"label": "Nuclear Medicine", "keywords": ["pet", "spect", "scintigraphy", "nuclear", "bone scan", "tc-99m", "fdg", "f-18", "ga-68"]},
        "fluoroscopy": {"label": "Fluoroscopy", "keywords": ["fluoroscop", "barium", "swallow study", "esophagram", "defecography"]},
        "angiography": {"label": "Angiography", "keywords": ["angiograph", "arteriograph", "venograph", "catheter", "interventional"]},
        "mammography": {"label": "Mammography", "keywords": ["mammograph", "breast imaging", "tomosynthesis"]},
    },
    "body_regions": {
        "head": {"label": "Head/Brain", "keywords": ["head", "brain", "cranial", "intracranial", "cerebr", "skull", "orbit", "sella", "temporal bone", "sinusitis", "headache"]},
        "neck": {"label": "Neck", "keywords": ["neck", "cervical spine", "thyroid", "larynx", "pharynx", "carotid"]},
        "spine": {"label": "Spine", "keywords": ["spine", "spinal", "vertebr", "lumbar", "thoracic", "sacr", "coccyx", "back pain", "radiculopathy", "myelopathy"]},
        "chest": {"label": "Chest", "keywords": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart", "mediastin", "pleura", "dyspnea", "cough"]},
        "abdomen": {"label": "Abdomen", "keywords": ["abdomen", "abdominal", "liver", "spleen", "pancrea", "kidney", "renal", "bowel", "intestin", "hepat", "biliary", "gallbladder"]},
        "pelvis": {"label": "Pelvis", "keywords": ["pelvis", "pelvic", "bladder", "prostate", "uterus", "ovary", "rectum", "gynecologic", "obstetric", "pregnancy"]},
        "msk": {"label": "Musculoskeletal", "keywords": ["musculoskeletal", "bone", "joint", "shoulder", "elbow", "wrist", "hip", "knee", "ankle", "fracture", "arthritis", "extremity", "trauma"]},
        "vascular": {"label": "Vascular", "keywords": ["vascular", "aorta", "artery", "vein", "dvt", "embolism", "aneurysm", "claudication", "ischemia"]},
        "breast": {"label": "Breast", "keywords": ["breast", "mammary", "axilla"]},
    },
    "radiation_levels": {
        "none": {"label": "None", "description": "No ionizing radiation (MRI, US)"},
        "low": {"label": "Low", "description": "<1 mSv (chest X-ray level)"},
        "medium": {"label": "Medium", "description": "1-10 mSv"},
        "high": {"label": "High", "description": ">10 mSv"},
    },
    "contrast_types": {
        "none": {"label": "Without contrast"},
        "iv": {"label": "With IV contrast"},
        "oral": {"label": "With oral contrast"},
        "both": {"label": "With IV and oral contrast"},
        "intrathecal": {"label": "With intrathecal contrast"},
        "intraarticular": {"label": "With intraarticular contrast"},
    },
}


def extract_modalities(text: str) -> list[str]:
    """Extract modalities from procedure or topic text."""
    text_lower = text.lower()
    found = []
    for key, data in CONFIG["modalities"].items():
        for keyword in data["keywords"]:
            if keyword in text_lower:
                found.append(key)
                break
    return list(set(found))


def extract_body_regions(text: str) -> list[str]:
    """Extract body regions from procedure or topic text."""
    text_lower = text.lower()
    found = []
    for key, data in CONFIG["body_regions"].items():
        for keyword in data["keywords"]:
            if keyword in text_lower:
                found.append(key)
                break
    return list(set(found))


def extract_contrast_info(text: str) -> dict:
    """Extract contrast administration details from procedure name."""
    if not text:
        return {"has_contrast": False, "contrast_type": "none", "contrast_detail": ""}

    text_lower = text.lower()

    if any(x in text_lower for x in ["without contrast", "without iv contrast", "noncontrast", "non-contrast", "unenhanced"]):
        return {"has_contrast": False, "contrast_type": "none", "contrast_detail": "Without contrast"}

    if "intrathecal" in text_lower or "myelograph" in text_lower:
        return {"has_contrast": True, "contrast_type": "intrathecal", "contrast_detail": "Intrathecal contrast"}

    if "arthrograph" in text_lower or "intra-articular" in text_lower or "intraarticular" in text_lower:
        return {"has_contrast": True, "contrast_type": "intraarticular", "contrast_detail": "Intraarticular contrast"}

    has_iv = any(x in text_lower for x in ["with iv contrast", "with contrast", "contrast enhanced", "contrast-enhanced", "iv contrast", "enhanced"])
    has_oral = any(x in text_lower for x in ["oral contrast", "oral and iv", "iv and oral"])

    if has_iv and has_oral:
        return {"has_contrast": True, "contrast_type": "both", "contrast_detail": "IV and oral contrast"}
    elif has_oral:
        return {"has_contrast": True, "contrast_type": "oral", "contrast_detail": "Oral contrast"}
    elif has_iv:
        return {"has_contrast": True, "contrast_type": "iv", "contrast_detail": "IV contrast"}

    return {"has_contrast": False, "contrast_type": "none", "contrast_detail": ""}


def extract_patient_population(text: str) -> dict:
    """Extract patient population details from variant description."""
    if not text:
        return {}

    population = {}
    text_lower = text.lower()

    # Age groups
    if any(x in text_lower for x in ["pediatric", "child", "infant", "neonate", "newborn"]):
        population["age_group"] = "pediatric"
    elif any(x in text_lower for x in ["adult", "elderly", "geriatric"]):
        population["age_group"] = "adult"

    # Sex
    if any(x in text_lower for x in ["female", "woman", "women", "girl"]):
        population["sex"] = "female"
    elif any(x in text_lower for x in ["male", "man", "men", "boy"]):
        population["sex"] = "male"

    # Special populations
    if any(x in text_lower for x in ["pregnant", "pregnancy", "obstetric", "gravid"]):
        population["special"] = "pregnant"
    elif "postmenopausal" in text_lower:
        population["special"] = "postmenopausal"
    elif "premenopausal" in text_lower or "reproductive age" in text_lower:
        population["special"] = "reproductive_age"

    # Acuity - check for chronic/subacute FIRST (more specific)
    if any(x in text_lower for x in ["chronic", "subacute"]):
        population["acuity"] = "chronic"
    elif any(x in text_lower for x in ["acute", "emergency", "emergent", "urgent"]):
        population["acuity"] = "acute"

    return population


def parse_radiation_level(text: str) -> str:
    """Parse radiation level from text using RRL (Relative Radiation Level)."""
    if not text:
        return "none"
    text_lower = text.lower().strip()

    # Count radiation symbols
    radioactive_count = text.count("☢")
    filled_count = text.count("●")

    # Check for explicit "O" meaning no radiation
    if text.strip() in ("O", "0") or "none" in text_lower:
        return "none"

    # Use symbol count
    symbol_count = radioactive_count or filled_count
    if symbol_count == 0:
        if any(x in text_lower for x in ["mri", "ultrasound", "us ", "mr ", "none", "n/a"]):
            return "none"
        return "none"
    elif symbol_count <= 2:
        return "low"
    elif symbol_count == 3:
        return "medium"
    else:
        return "high"


def parse_score(text: str) -> Optional[int]:
    """Extract numeric score from appropriateness text."""
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
    if "usually not appropriate" in text_lower or "not appropriate" in text_lower:
        return 2

    return None


def get_level(score: Optional[int]) -> Optional[str]:
    """Get appropriateness level from score."""
    if score is None:
        return None
    for key, data in CONFIG["appropriateness_levels"].items():
        if data["range"][0] <= score <= data["range"][1]:
            return key
    return None


def get_level_label(score: Optional[int]) -> str:
    """Get human-readable level label from score."""
    level = get_level(score)
    return CONFIG["appropriateness_levels"].get(level, {}).get("label", "Unknown") if level else "Unknown"


def parse_variant_description(text: str) -> dict:
    """Parse variant description into structured components."""
    if not text:
        return {"raw": "", "population": {}, "clinical_scenario": "", "imaging_phase": ""}

    # Clean up the text
    text = re.sub(r"^Variant\s*\d+[:\.]?\s*", "", text, flags=re.IGNORECASE).strip()

    result = {
        "raw": text,
        "population": extract_patient_population(text),
        "clinical_scenario": text,
        "imaging_phase": "",
    }

    # Extract imaging phase
    phase_patterns = [
        r"(initial imaging\.?)",
        r"(follow[- ]?up imaging\.?)",
        r"(surveillance\.?)",
        r"(staging\.?)",
        r"(restaging\.?)",
        r"(screening\.?)",
        r"(post[- ]?treatment\.?)",
        r"(pre[- ]?operative\.?)",
    ]

    for pattern in phase_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["imaging_phase"] = match.group(1).strip().rstrip(".")
            break

    return result


def generate_synopsis(topic_title: str, variants: list) -> Optional[list]:
    """Generate a clinical synopsis for the topic based on variant data."""
    if not variants:
        return None

    synopsis_parts = []

    variant_count = len(variants)
    if variant_count > 1:
        synopsis_parts.append(f"{variant_count} clinical scenarios addressed")

    all_procedures = []
    for v in variants:
        all_procedures.extend(v.get("procedures", []))

    if not all_procedures:
        return synopsis_parts if synopsis_parts else None

    appropriate = [p for p in all_procedures if p.get("level") == "usually_appropriate"]
    not_appropriate = [p for p in all_procedures if p.get("level") == "usually_not_appropriate"]

    # Find radiation-free appropriate options
    radiation_free = [p for p in appropriate if p.get("radiation_level") == "none"]
    if radiation_free:
        modalities = set()
        for p in radiation_free:
            modalities.update(p.get("modalities", []))
        modality_labels = [CONFIG["modalities"].get(m, {}).get("label", m) for m in modalities]
        if modality_labels:
            synopsis_parts.append(f"Radiation-free options: {', '.join(sorted(set(modality_labels))[:3])}")

    if appropriate:
        modalities = set()
        for p in appropriate:
            modalities.update(p.get("modalities", []))
        modality_labels = [CONFIG["modalities"].get(m, {}).get("label", m) for m in modalities]
        if modality_labels:
            synopsis_parts.append(f"First-line imaging may include: {', '.join(sorted(set(modality_labels))[:4])}")

    if not_appropriate:
        synopsis_parts.append(f"{len(not_appropriate)} procedure(s) generally not indicated")

    return synopsis_parts if synopsis_parts else None


_topic_cache: Optional[list] = None


@lru_cache(maxsize=100)
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


def extract_all_variant_descriptions(soup) -> list:
    """Extract all variant descriptions from the page."""
    variants = {}

    for element in soup.find_all(["b", "strong"]):
        text = element.get_text(strip=True)
        match = re.match(r"Variant\s*(\d+)[:\s]+(.+)", text, re.IGNORECASE)
        if match:
            variant_num = int(match.group(1))
            description = match.group(2).strip()
            if len(description) > 20 and not description.lower().startswith("discussion"):
                if variant_num not in variants or len(description) > len(variants[variant_num]):
                    variants[variant_num] = description

    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        match = re.match(r"^Variant\s*(\d+)[:\s]+([^<]+)", text, re.IGNORECASE)
        if match:
            variant_num = int(match.group(1))
            description = match.group(2).strip()
            description = re.split(r"(?<=[.!?])\s+(?=[A-Z])", description)[0]
            if len(description) > 20 and not description.lower().startswith("discussion"):
                if variant_num not in variants:
                    variants[variant_num] = description

    if not variants:
        return []

    max_variant = max(variants.keys())
    return [variants.get(i, "") for i in range(1, max_variant + 1)]


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

    # Extract variant descriptions
    variant_descriptions = extract_all_variant_descriptions(soup)

    # Parse procedure tables
    variants = []
    table_index = 0

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header = rows[0].get_text(strip=True).lower()
        if "procedure" not in header and "appropriateness" not in header:
            continue

        procedures = []
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            name = cells[0].get_text(strip=True)
            if not name or name.lower() in ("procedure", "radiologic procedure"):
                continue

            appropriateness_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            radiation_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            score = parse_score(appropriateness_text)
            contrast_info = extract_contrast_info(name)

            procedures.append({
                "name": name,
                "score": score,
                "level": get_level(score),
                "level_label": get_level_label(score),
                "radiation_level": parse_radiation_level(radiation_text),
                "modalities": extract_modalities(name),
                "contrast": contrast_info,
            })

        if procedures:
            variant_desc = variant_descriptions[table_index] if table_index < len(variant_descriptions) else ""
            parsed_variant = parse_variant_description(variant_desc)

            variants.append({
                "variant_number": table_index + 1,
                "description": variant_desc,
                "clinical_scenario": parsed_variant["clinical_scenario"],
                "population": parsed_variant["population"],
                "imaging_phase": parsed_variant["imaging_phase"],
                "procedures": procedures,
            })
            table_index += 1

    synopsis = generate_synopsis(topic_title, variants)

    return {
        "topic_id": topic_id,
        "title": topic_title,
        "url": topic_url,
        "synopsis": synopsis,
        "variants": variants,
        "total_variants": len(variants),
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
        "results": results[:20],
        "total_matches": len(results),
        "query": query,
    }


def list_topics(body_region: Optional[str] = None, limit: int = 30) -> dict:
    """List all ACR topics, optionally filtered by body region."""
    topics = fetch_topics()
    if body_region:
        topics = [t for t in topics if body_region in t["body_regions"]]
    return {
        "topics": topics[:limit],
        "total": len(topics),
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
                    "enum": ["ct", "mri", "us", "xray", "nuclear", "fluoroscopy", "angiography", "mammography"],
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
        "description": "Get detailed appropriateness ratings for a specific ACR topic. Returns all variants and procedures with scores (1-9), radiation levels, and contrast information.",
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
        return list_topics(args.get("body_region"))
    else:
        return {"error": f"Unknown tool: {name}"}
