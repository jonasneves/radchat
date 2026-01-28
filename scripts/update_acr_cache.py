#!/usr/bin/env python3
"""
Scrape ACR Appropriateness Criteria topic list.
Extracts topic names and URLs for search functionality.
Detail pages are not scraped as ACR blocks automated access.
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
        "head": ["head", "brain", "cranial", "intracranial", "skull", "headache", "stroke", "seizure", "dementia"],
        "neck": ["neck", "cervical", "thyroid", "carotid", "laryn"],
        "spine": ["spine", "spinal", "vertebr", "lumbar", "thoracic", "back pain", "myelopathy"],
        "chest": ["chest", "thorax", "lung", "pulmonary", "cardiac", "heart", "aortic", "rib"],
        "abdomen": ["abdomen", "liver", "pancrea", "kidney", "renal", "bowel", "hepat", "spleen", "biliary"],
        "pelvis": ["pelvis", "bladder", "prostate", "uterus", "ovary", "pregnancy", "testicular", "scrotal"],
        "msk": ["musculoskeletal", "bone", "joint", "shoulder", "knee", "fracture", "hip", "ankle", "wrist", "elbow"],
        "vascular": ["vascular", "aorta", "artery", "vein", "dvt", "embolism", "aneurysm", "thrombosis"],
        "breast": ["breast", "mammary"],
    }
    for region, kws in keywords.items():
        if any(kw in title_lower for kw in kws):
            regions.append(region)
    return regions


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("Starting ACR cache update with Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Fetch topic list
        print("Fetching topic list...")
        page.goto(f"{BASE_URL}/list", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("a[href*='TopicId=']", timeout=30000)

        # Extract topics from links with TopicId and TopicName parameters
        topics = {}
        links = page.query_selector_all("a[href*='TopicId='][href*='TopicName=']")

        for link in links:
            href = link.get_attribute("href") or ""
            id_match = re.search(r"TopicId=(\d+)", href)
            name_match = re.search(r"TopicName=([^&]+)", href)

            if id_match and name_match:
                topic_id = id_match.group(1)
                topic_name = unquote(name_match.group(1)).replace("+", " ")

                if topic_id not in topics and topic_name:
                    # Construct URL to ACR search with this topic
                    search_url = f"{BASE_URL}/list?q={quote_plus(topic_name)}"

                    topics[topic_id] = {
                        "id": topic_id,
                        "title": topic_name,
                        "url": search_url,
                        "body_regions": extract_body_regions(topic_name),
                    }

        browser.close()

    print(f"Found {len(topics)} topics")

    # Build cache
    cached_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE_URL,
        "note": "Topic names and search URLs only. Visit ACR website for detailed ratings.",
        "topics": topics,
    }

    # Save to file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(cached_data, f, indent=2)

    print(f"Saved {len(topics)} topics to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
