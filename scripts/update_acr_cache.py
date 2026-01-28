#!/usr/bin/env python3
"""
ACR Appropriateness Criteria scraper using the gravitas.acr.org API.

Strategy:
1. Get topic list from acsearch.acr.org/list (TopicId values)
2. Fetch procedure data from gravitas.acr.org/ACPortal/GetDataForOneTopic?topicId=X
3. Parse HTML tables with appropriateness ratings (bg-green, bg-yellow, bg-pink)

Output structure:
- src/data/acr/index.json - topic list with basic info
- src/data/acr/topics/{id}.json - individual topic details
"""

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = Path.cwd() / "src" / "data" / "acr"
INDEX_FILE = OUTPUT_DIR / "index.json"
TOPICS_DIR = OUTPUT_DIR / "topics"
LIST_URL = "https://acsearch.acr.org/list"
DETAIL_API_URL = "https://gravitas.acr.org/ACPortal/GetDataForOneTopic"

# Scraping configuration
BATCH_SIZE = 50  # Topics per run
DELAY_MIN = 1.0
DELAY_MAX = 2.0
MAX_ATTEMPTS = 3
RETRY_AFTER_DAYS = 7
DETAIL_MAX_AGE_DAYS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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


def get_rating_from_cell(cell) -> tuple[Optional[str], Optional[int]]:
    """Get rating and score from a table cell."""
    classes = cell.get("class", [])
    text = cell.get_text(strip=True).lower()

    if "bg-green" in classes or "usually appropriate" in text:
        return "Usually Appropriate", 9
    if "bg-yellow" in classes or "may be appropriate" in text:
        return "May Be Appropriate", 5
    if "bg-pink" in classes or "usually not appropriate" in text:
        return "Usually Not Appropriate", 2
    return None, None


def load_existing_index() -> dict:
    """Load existing index if available."""
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "updated_at": None,
        "source": LIST_URL,
        "scrape_state": {},
        "topics": {},
    }


def save_index(data: dict):
    """Save index to file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(INDEX_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_topic_details(topic_id: str, details: dict):
    """Save individual topic details."""
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOPICS_DIR / f"{topic_id}.json", "w") as f:
        json.dump(details, f, indent=2)


def should_attempt_details(topic: dict) -> bool:
    """Check if we should attempt to scrape details for this topic."""
    status = topic.get("status", "pending")

    if status == "pending":
        return True

    if status == "success":
        last_attempted = topic.get("last_attempted")
        if last_attempted:
            last_dt = datetime.fromisoformat(last_attempted.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).days
            return age_days > DETAIL_MAX_AGE_DAYS
        return False

    if status == "no_data":
        last_attempted = topic.get("last_attempted")
        if last_attempted:
            last_dt = datetime.fromisoformat(last_attempted.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).days
            return age_days > DETAIL_MAX_AGE_DAYS
        return False

    if status == "blocked":
        last_attempted = topic.get("last_attempted")
        if last_attempted:
            last_dt = datetime.fromisoformat(last_attempted.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).days
            return age_days > RETRY_AFTER_DAYS
        return True

    if status == "failed":
        return topic.get("attempts", 0) < MAX_ATTEMPTS

    return True


def fetch_topic_list() -> dict[str, dict]:
    """Fetch topic list from acsearch.acr.org. Returns {doc_id: {name, topic_id}}."""
    print("Fetching topic list from acsearch.acr.org...")

    try:
        response = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching topic list: {e}")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    topics = {}

    # Structure: col-lg-8 > [title div, row div with links]
    # Narrative link is in row > col-lg-3
    # Evidence link with TopicId is in row > col-lg-2
    for narrative_link in soup.find_all("a", href=re.compile(r"/docs/\d+/Narrative/")):
        href = narrative_link.get("href", "")
        doc_match = re.search(r"/docs/(\d+)/Narrative/", href)
        if not doc_match:
            continue

        doc_id = doc_match.group(1)
        if doc_id in topics:
            continue

        # Navigate: link -> parent (col-lg-3) -> parent (row) -> search for Evidence link
        col_div = narrative_link.parent
        row_div = col_div.parent if col_div else None
        if not row_div:
            continue

        topic_id = None
        topic_name = None

        # Search row for Evidence link with TopicId
        for link in row_div.find_all("a", href=True):
            link_href = link.get("href", "")
            if "TopicId=" in link_href and "TopicName=" in link_href:
                id_match = re.search(r"TopicId=(\d+)", link_href)
                name_match = re.search(r"TopicName=([^&]+)", link_href)
                if id_match and name_match:
                    topic_id = id_match.group(1)
                    topic_name = unquote(name_match.group(1)).replace("+", " ")
                    break

        # Fallback: get name from previous sibling of row's parent
        if not topic_name:
            container = row_div.parent
            if container:
                prev_sibling = row_div.find_previous_sibling()
                if prev_sibling:
                    topic_name = prev_sibling.get_text(strip=True)

        if topic_name:
            topics[doc_id] = {"name": topic_name, "topic_id": topic_id}

    print(f"Found {len(topics)} topics")
    return topics


def fetch_topic_details(topic_id: str) -> Optional[dict]:
    """Fetch procedure data from gravitas.acr.org API."""
    url = f"{DETAIL_API_URL}?topicId={topic_id}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  Error fetching topic {topic_id}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Check for "content not available" message
    not_available = soup.find(string=re.compile(r"content.*not available", re.I))
    if not_available:
        return {"no_data": True}

    # Find all procedure tables
    procedures = []
    tables = soup.find_all("table", class_="tblResDocs")

    if not tables:
        tables = soup.find_all("table", class_="basicTable")

    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Find rating cell
            rating, score = None, None
            for cell in cells:
                r, s = get_rating_from_cell(cell)
                if r:
                    rating, score = r, s
                    break

            if not rating:
                continue

            # Get procedure name from first tdResDoc cell
            name = None
            for cell in cells:
                if "tdResDoc" in cell.get("class", []):
                    text = cell.get_text(strip=True)
                    # Skip numeric IDs and dose indicators
                    if text and not text.isdigit() and "mSv" not in text:
                        name = text
                        break

            if name and len(name) > 3:
                procedures.append({
                    "name": name,
                    "score": score,
                    "rating": rating,
                })

    if not procedures:
        return None

    return {"procedures": procedures}


def main():
    print("Starting ACR cache update (gravitas.acr.org API)...")

    index = load_existing_index()

    # Phase 1: Get topic list
    print("\n=== Phase 1: Topic List ===")
    topic_map = fetch_topic_list()

    if not topic_map:
        print("Failed to fetch topic list")
        sys.exit(1)

    # Update index with any new topics
    # topic_map now returns {doc_id: {name, topic_id}}
    new_topics = 0
    for doc_id, data in topic_map.items():
        if doc_id not in index["topics"]:
            index["topics"][doc_id] = {
                "id": doc_id,
                "topic_id": data.get("topic_id"),  # For API calls
                "title": data["name"],
                "url": f"https://acsearch.acr.org/docs/{doc_id}/Narrative/",
                "body_regions": extract_body_regions(data["name"]),
                "status": "pending",
                "attempts": 0,
            }
            new_topics += 1
        elif data.get("topic_id") and not index["topics"][doc_id].get("topic_id"):
            # Update existing entries with topic_id if missing
            index["topics"][doc_id]["topic_id"] = data["topic_id"]

    print(f"Total topics: {len(index['topics'])} ({new_topics} new)")

    # Phase 2: Fetch details for pending topics
    print(f"\n=== Phase 2: Details (batch of {BATCH_SIZE}) ===")

    pending = [
        (topic_id, topic) for topic_id, topic in index["topics"].items()
        if should_attempt_details(topic)
    ]
    print(f"Topics needing details: {len(pending)}")

    batch = pending[:BATCH_SIZE]
    success_count = 0

    for i, (doc_id, topic) in enumerate(batch):
        print(f"[{i+1}/{len(batch)}] {topic['title'][:50]}...")

        # Random delay
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        now = datetime.now(timezone.utc).isoformat()
        topic["last_attempted"] = now
        topic["attempts"] = topic.get("attempts", 0) + 1

        # Use topic_id for API call, fall back to doc_id
        api_id = topic.get("topic_id") or doc_id
        details = fetch_topic_details(api_id)

        if details and details.get("no_data"):
            topic["status"] = "no_data"
            print(f"  ○ Content not available on ACR")
        elif details and details.get("procedures"):
            topic["status"] = "success"

            # Build summary (deduplicated)
            first_line = []
            alternatives = []
            avoid = []
            seen = set()

            for proc in details["procedures"]:
                name = proc.get("name")
                score = proc.get("score")
                if not name or name in seen:
                    continue
                seen.add(name)

                if score:
                    if score >= 7 and len(first_line) < 5:
                        first_line.append(name)
                    elif 4 <= score < 7 and len(alternatives) < 3:
                        alternatives.append(name)
                    elif score < 4 and len(avoid) < 3:
                        avoid.append(name)

            # Store summary in index (for quick access)
            topic["summary"] = {
                "first_line": first_line,
                "alternatives": alternatives,
                "avoid": avoid,
                "total_procedures": len(seen),
            }

            # Save full details to separate file
            save_topic_details(doc_id, {
                "id": doc_id,
                "topic_id": topic.get("topic_id"),
                "title": topic["title"],
                "url": topic["url"],
                "body_regions": topic["body_regions"],
                "procedures": details["procedures"],
                "updated_at": now,
            })

            success_count += 1
            print(f"  ✓ Found {len(seen)} unique procedures")
        else:
            print(f"  ✗ No procedure data found (attempt {topic['attempts']})")
            if topic["attempts"] >= MAX_ATTEMPTS:
                topic["status"] = "blocked"
            else:
                topic["status"] = "failed"

    # Update state
    state = index.get("scrape_state", {})
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["topics_total"] = len(index["topics"])
    state["topics_with_data"] = sum(1 for t in index["topics"].values() if t.get("status") == "success")
    state["topics_no_data"] = sum(1 for t in index["topics"].values() if t.get("status") == "no_data")
    state["topics_blocked"] = sum(1 for t in index["topics"].values() if t.get("status") == "blocked")
    index["scrape_state"] = state

    save_index(index)

    print(f"\n=== Summary ===")
    print(f"Topics total: {state['topics_total']}")
    print(f"Topics with data: {state['topics_with_data']}")
    print(f"No data on ACR: {state['topics_no_data']}")
    print(f"Blocked: {state['topics_blocked']}")
    pending_count = state['topics_total'] - state['topics_with_data'] - state['topics_no_data'] - state['topics_blocked']
    print(f"Pending: {pending_count}")
    print(f"This batch: {success_count}/{len(batch)} succeeded")
    print(f"Saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
