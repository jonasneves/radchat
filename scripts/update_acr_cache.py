#!/usr/bin/env python3
"""
ACR Appropriateness Criteria topic scraper.

Scrapes topic names and search URLs from the ACR list page.
Detail pages (Narrative/Rating tables) are blocked by ACR for automated access.
Users can click through to view detailed ratings on the ACR website.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, quote_plus

OUTPUT_FILE = Path.cwd() / "src" / "data" / "acr_criteria.json"
BASE_URL = "https://acsearch.acr.org"


def extract_body_regions(title: str) -> list[str]:
    """Extract body regions from topic title."""
    title_lower = title.lower()
    regions = []
    keywords = {
        "head": ["head", "brain", "cranial", "intracranial", "skull", "headache", "stroke", "seizure", "dementia", "vision", "eye", "orbit"],
        "neck": ["neck", "cervical", "thyroid", "carotid", "laryn", "hoarse"],
        "spine": ["spine", "spinal", "vertebr", "lumbar", "thoracic", "back pain", "myelopathy", "radiculopathy"],
        "chest": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart", "aortic", "rib", "dyspnea", "cough"],
        "abdomen": ["abdomen", "liver", "pancrea", "kidney", "renal", "bowel", "hepat", "spleen", "biliary", "gallbladder"],
        "pelvis": ["pelvis", "bladder", "prostate", "uterus", "ovary", "pregnancy", "testicular", "scrotal", "groin"],
        "msk": ["musculoskeletal", "bone", "joint", "shoulder", "knee", "fracture", "hip", "ankle", "wrist", "elbow", "foot", "hand", "trauma"],
        "vascular": ["vascular", "aorta", "artery", "vein", "dvt", "embolism", "aneurysm", "thrombosis", "claudication"],
        "breast": ["breast", "mammary", "nipple"],
        "pediatric": ["child", "infant", "pediatric", "neonat"],
    }
    for region, kws in keywords.items():
        if any(kw in title_lower for kw in kws):
            regions.append(region)
    return regions


def load_existing_cache() -> dict:
    """Load existing cache if available."""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"updated_at": None, "source": BASE_URL, "topics": {}}


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: playwright not installed")
        sys.exit(1)

    print("Fetching ACR topic list...")

    # Load existing cache to preserve any manually added data
    cache = load_existing_cache()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        page.goto(f"{BASE_URL}/list", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("a[href*='TopicId=']", timeout=30000)

        # Extract topics from links with TopicId and TopicName
        links = page.query_selector_all("a[href*='TopicId='][href*='TopicName=']")
        new_count = 0
        updated_count = 0

        for link in links:
            href = link.get_attribute("href") or ""
            id_match = re.search(r"TopicId=(\d+)", href)
            name_match = re.search(r"TopicName=([^&]+)", href)

            if id_match and name_match:
                topic_id = id_match.group(1)
                topic_name = unquote(name_match.group(1)).replace("+", " ")

                if topic_name:
                    if topic_id not in cache["topics"]:
                        new_count += 1
                    else:
                        # Check if name changed
                        if cache["topics"][topic_id].get("title") != topic_name:
                            updated_count += 1

                    cache["topics"][topic_id] = {
                        "id": topic_id,
                        "title": topic_name,
                        "url": f"{BASE_URL}/list?q={quote_plus(topic_name)}",
                        "body_regions": extract_body_regions(topic_name),
                    }

        browser.close()

    # Update metadata
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()
    cache["note"] = "Topic search only. Visit ACR website for detailed appropriateness ratings."

    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"Total topics: {len(cache['topics'])}")
    print(f"New: {new_count}, Updated: {updated_count}")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
