#!/usr/bin/env python3
"""
Scrape ACR Appropriateness Criteria using Playwright (headless browser).
Required because ACR site uses JavaScript to render content.

Run: pip install playwright && playwright install chromium
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

OUTPUT_FILE = Path(__file__).parent.parent / "src" / "data" / "acr_criteria.json"
BASE_URL = "https://acsearch.acr.org"


def extract_body_regions(title: str) -> list[str]:
    """Extract body regions from topic title."""
    title_lower = title.lower()
    regions = []
    keywords = {
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
    for region, kws in keywords.items():
        if any(kw in title_lower for kw in kws):
            regions.append(region)
    return regions


def parse_score(text: str) -> Optional[int]:
    """Extract numeric score from appropriateness text."""
    if not text:
        return None
    match = re.search(r"\b([1-9])\b", text.strip())
    if match:
        return int(match.group(1))
    return None


def get_rating_label(score: Optional[int]) -> str:
    """Get human-readable rating label."""
    if score is None:
        return "Unknown"
    if score >= 7:
        return "Usually Appropriate"
    if score >= 4:
        return "May Be Appropriate"
    return "Usually Not Appropriate"


def parse_radiation(text: str) -> str:
    """Parse radiation level from symbols."""
    if not text:
        return "unknown"
    # Count radiation symbols
    count = text.count("☢") + text.count("●") + text.count("◉")
    if count == 0:
        if any(x in text.lower() for x in ["none", "mri", "us", "ultrasound", "o"]):
            return "none"
        return "unknown"
    if count <= 2:
        return "low"
    if count == 3:
        return "medium"
    return "high"


def extract_modality(text: str) -> Optional[str]:
    """Extract modality from procedure name."""
    text_lower = text.lower()
    if any(x in text_lower for x in ["cta", "ct "]):
        return "CT"
    if any(x in text_lower for x in ["mra", "mri", "mr "]):
        return "MRI"
    if any(x in text_lower for x in ["ultrasound", "us ", "doppler"]):
        return "Ultrasound"
    if any(x in text_lower for x in ["x-ray", "xray", "radiograph"]):
        return "X-ray"
    if any(x in text_lower for x in ["pet", "spect", "nuclear", "scintigraphy"]):
        return "Nuclear"
    if "fluoroscop" in text_lower:
        return "Fluoroscopy"
    if "angiograph" in text_lower:
        return "Angiography"
    return None


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

        # Extract topics
        topics = {}
        links = page.query_selector_all("a[href*='TopicId=']")
        for link in links:
            href = link.get_attribute("href") or ""
            id_match = re.search(r"TopicId=(\d+)", href)
            name_match = re.search(r"TopicName=([^&]+)", href)
            if id_match and name_match:
                topic_id = id_match.group(1)
                topic_name = unquote(name_match.group(1)).replace("+", " ")
                if topic_id not in topics:
                    topics[topic_id] = topic_name

        print(f"Found {len(topics)} topics")

        # Extract doc URLs
        doc_urls = {}
        doc_links = page.query_selector_all("a[href*='/docs/']")
        for link in doc_links:
            href = link.get_attribute("href") or ""
            if "Narrative" in href or "EvidenceTable" in href:
                match = re.search(r"/docs/(\d+)/", href)
                if match:
                    full_url = BASE_URL + href if href.startswith("/") else href
                    doc_urls[match.group(1)] = full_url

        # Build cache
        cached_data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": BASE_URL,
            "topics": {},
        }

        topic_list = sorted(topics.items(), key=lambda x: x[1])
        total = len(topic_list)

        for i, (topic_id, topic_title) in enumerate(topic_list):
            print(f"[{i+1}/{total}] {topic_title[:50]}...")

            topic_url = doc_urls.get(topic_id, f"{BASE_URL}/docs/{topic_id}/Narrative/")

            topic_data = {
                "id": topic_id,
                "title": topic_title,
                "url": topic_url,
                "body_regions": extract_body_regions(topic_title),
                "variants": [],
                "summary": {
                    "first_line": [],
                    "alternatives": [],
                    "avoid": [],
                    "total_procedures": 0,
                },
            }

            try:
                # Navigate to topic page
                page.goto(topic_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1000)  # Extra wait for dynamic content

                # Look for procedure tables
                tables = page.query_selector_all("table")

                variant_num = 0
                for table in tables:
                    rows = table.query_selector_all("tr")
                    if len(rows) < 2:
                        continue

                    header_text = rows[0].inner_text().lower()
                    if "procedure" not in header_text and "appropriateness" not in header_text:
                        continue

                    variant_num += 1
                    procedures = []

                    for row in rows[1:]:
                        cells = row.query_selector_all("td, th")
                        if len(cells) < 2:
                            continue

                        name = cells[0].inner_text().strip()
                        if not name or name.lower() in ("procedure", "radiologic procedure"):
                            continue

                        appropriateness = cells[1].inner_text().strip() if len(cells) > 1 else ""
                        radiation = cells[2].inner_text().strip() if len(cells) > 2 else ""

                        score = parse_score(appropriateness)
                        proc = {
                            "name": name,
                            "score": score,
                            "rating": get_rating_label(score),
                            "modality": extract_modality(name),
                            "radiation": parse_radiation(radiation),
                        }
                        procedures.append(proc)

                        # Update summary
                        if score:
                            summary_item = {"name": name, "modality": proc["modality"], "radiation": proc["radiation"]}
                            if score >= 7:
                                if len(topic_data["summary"]["first_line"]) < 5:
                                    topic_data["summary"]["first_line"].append(summary_item)
                            elif score >= 4:
                                if len(topic_data["summary"]["alternatives"]) < 3:
                                    topic_data["summary"]["alternatives"].append(summary_item)
                            else:
                                if len(topic_data["summary"]["avoid"]) < 3:
                                    topic_data["summary"]["avoid"].append(name)

                    if procedures:
                        topic_data["variants"].append({
                            "number": variant_num,
                            "procedures": procedures,
                        })
                        topic_data["summary"]["total_procedures"] += len(procedures)

            except Exception as e:
                print(f"  Error fetching details: {e}")

            cached_data["topics"][topic_id] = topic_data

        browser.close()

    # Save to file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(cached_data, f, indent=2)

    # Stats
    topics_with_data = sum(1 for t in cached_data["topics"].values() if t.get("variants"))
    print(f"\nSaved {len(cached_data['topics'])} topics to {OUTPUT_FILE}")
    print(f"Topics with procedure data: {topics_with_data}")


if __name__ == "__main__":
    main()
