#!/usr/bin/env python3
"""
Phased ACR Appropriateness Criteria scraper.

Phase 1: Fetch topic list (fast, always succeeds)
Phase 2: Attempt detail pages in batches with delays

Tracks progress and retries failed topics with backoff.
"""

import json
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, quote_plus

OUTPUT_FILE = Path.cwd() / "src" / "data" / "acr_criteria.json"
BASE_URL = "https://acsearch.acr.org"

# Scraping configuration
BATCH_SIZE = 20  # Topics per run
DELAY_MIN = 3  # Min seconds between requests
DELAY_MAX = 8  # Max seconds between requests
MAX_ATTEMPTS = 3  # Max attempts before marking as blocked
RETRY_AFTER_DAYS = 7  # Retry blocked topics after this many days
DETAIL_MAX_AGE_DAYS = 30  # Re-scrape details older than this


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


def parse_score(text: str) -> Optional[int]:
    """Extract numeric score from appropriateness text."""
    if not text:
        return None
    match = re.search(r"\b([1-9])\b", text.strip())
    return int(match.group(1)) if match else None


def get_rating_label(score: Optional[int]) -> str:
    """Get human-readable rating label."""
    if score is None:
        return "Unknown"
    if score >= 7:
        return "Usually Appropriate"
    if score >= 4:
        return "May Be Appropriate"
    return "Usually Not Appropriate"


def load_existing_cache() -> dict:
    """Load existing cache if available."""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "updated_at": None,
        "source": BASE_URL,
        "scrape_state": {
            "phase": "topics",
            "last_run": None,
            "topics_scraped": 0,
            "details_scraped": 0,
            "details_blocked": 0,
        },
        "topics": {},
    }


def save_cache(data: dict):
    """Save cache to file."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def should_attempt_details(topic: dict) -> bool:
    """Check if we should attempt to scrape details for this topic."""
    status = topic.get("status", "pending")

    # Never attempted
    if status == "pending":
        return True

    # Already have details
    if status == "success":
        # Check if stale
        last_attempted = topic.get("last_attempted")
        if last_attempted:
            last_dt = datetime.fromisoformat(last_attempted.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).days
            return age_days > DETAIL_MAX_AGE_DAYS
        return False

    # Blocked - check if we should retry
    if status == "blocked":
        last_attempted = topic.get("last_attempted")
        if last_attempted:
            last_dt = datetime.fromisoformat(last_attempted.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_dt).days
            return age_days > RETRY_AFTER_DAYS
        return True

    # Failed but not blocked yet
    if status == "failed":
        attempts = topic.get("attempts", 0)
        if attempts >= MAX_ATTEMPTS:
            return False  # Will be marked blocked
        return True

    return True


def scrape_topic_details(page, topic: dict) -> dict:
    """Attempt to scrape procedure details from topic page."""
    topic_url = topic.get("detail_url") or topic.get("url", "")

    if not topic_url or "list?q=" in topic_url:
        # No detail URL available
        return {"status": "no_url"}

    try:
        # Random delay to avoid detection
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        time.sleep(delay)

        page.goto(topic_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Check for error page
        if page.query_selector("text=Error"):
            return {"status": "error_page"}

        # Look for procedure tables
        tables = page.query_selector_all("table")

        procedures = []
        for table in tables:
            rows = table.query_selector_all("tr")
            if len(rows) < 2:
                continue

            header_text = rows[0].inner_text().lower()
            if "procedure" not in header_text and "appropriateness" not in header_text:
                continue

            for row in rows[1:]:
                cells = row.query_selector_all("td, th")
                if len(cells) < 2:
                    continue

                name = cells[0].inner_text().strip()
                if not name or name.lower() in ("procedure", "radiologic procedure"):
                    continue

                appropriateness = cells[1].inner_text().strip() if len(cells) > 1 else ""
                score = parse_score(appropriateness)

                procedures.append({
                    "name": name,
                    "score": score,
                    "rating": get_rating_label(score),
                })

        if procedures:
            return {"status": "success", "procedures": procedures}
        else:
            return {"status": "no_tables"}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: playwright not installed")
        sys.exit(1)

    print("Starting phased ACR cache update...")

    # Load existing cache
    cache = load_existing_cache()
    state = cache.get("scrape_state", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Phase 1: Always refresh topic list
        print("\n=== Phase 1: Topic List ===")
        page.goto(f"{BASE_URL}/list", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("a[href*='TopicId=']", timeout=30000)

        # Extract topics
        links = page.query_selector_all("a[href*='TopicId='][href*='TopicName=']")
        new_topics = 0

        for link in links:
            href = link.get_attribute("href") or ""
            id_match = re.search(r"TopicId=(\d+)", href)
            name_match = re.search(r"TopicName=([^&]+)", href)

            if id_match and name_match:
                topic_id = id_match.group(1)
                topic_name = unquote(name_match.group(1)).replace("+", " ")

                if topic_id not in cache["topics"]:
                    cache["topics"][topic_id] = {
                        "id": topic_id,
                        "title": topic_name,
                        "url": f"{BASE_URL}/list?q={quote_plus(topic_name)}",
                        "body_regions": extract_body_regions(topic_name),
                        "status": "pending",
                        "attempts": 0,
                    }
                    new_topics += 1

        # Try to find narrative URLs
        narrative_links = page.query_selector_all("a[href*='/docs/'][href*='/Narrative/']")
        for link in narrative_links:
            href = link.get_attribute("href") or ""
            doc_match = re.search(r"/docs/(\d+)/Narrative/", href)
            if doc_match:
                # Try to find associated topic by checking nearby elements
                parent = link.evaluate_handle("el => el.parentElement?.parentElement")
                if parent:
                    topic_link = parent.query_selector("a[href*='TopicId=']")
                    if topic_link:
                        topic_href = topic_link.get_attribute("href") or ""
                        tid_match = re.search(r"TopicId=(\d+)", topic_href)
                        if tid_match and tid_match.group(1) in cache["topics"]:
                            full_url = BASE_URL + href if href.startswith("/") else href
                            cache["topics"][tid_match.group(1)]["detail_url"] = full_url

        print(f"Total topics: {len(cache['topics'])} ({new_topics} new)")

        # Phase 2: Attempt detail pages in batches
        print(f"\n=== Phase 2: Details (batch of {BATCH_SIZE}) ===")

        # Find topics needing detail scrape
        pending = [
            (tid, topic) for tid, topic in cache["topics"].items()
            if should_attempt_details(topic) and topic.get("detail_url")
        ]

        print(f"Topics needing details: {len(pending)}")

        # Process batch
        batch = pending[:BATCH_SIZE]
        success_count = 0
        blocked_count = 0

        for i, (topic_id, topic) in enumerate(batch):
            print(f"[{i+1}/{len(batch)}] {topic['title'][:50]}...")

            result = scrape_topic_details(page, topic)
            now = datetime.now(timezone.utc).isoformat()

            topic["last_attempted"] = now
            topic["attempts"] = topic.get("attempts", 0) + 1

            if result["status"] == "success":
                topic["status"] = "success"
                topic["procedures"] = result["procedures"]

                # Build summary
                first_line = []
                alternatives = []
                avoid = []
                for proc in result["procedures"]:
                    if proc.get("score"):
                        if proc["score"] >= 7 and len(first_line) < 5:
                            first_line.append(proc["name"])
                        elif proc["score"] >= 4 and len(alternatives) < 3:
                            alternatives.append(proc["name"])
                        elif proc["score"] < 4 and len(avoid) < 3:
                            avoid.append(proc["name"])

                topic["summary"] = {
                    "first_line": first_line,
                    "alternatives": alternatives,
                    "avoid": avoid,
                    "total_procedures": len(result["procedures"]),
                }
                success_count += 1
                print(f"  ✓ Found {len(result['procedures'])} procedures")

            elif result["status"] in ("error_page", "no_tables", "no_url"):
                if topic["attempts"] >= MAX_ATTEMPTS:
                    topic["status"] = "blocked"
                    blocked_count += 1
                    print(f"  ✗ Blocked after {MAX_ATTEMPTS} attempts")
                else:
                    topic["status"] = "failed"
                    print(f"  ✗ {result['status']} (attempt {topic['attempts']})")

            else:
                topic["status"] = "failed"
                print(f"  ✗ {result.get('error', result['status'])}")

        browser.close()

    # Update state
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["topics_scraped"] = len(cache["topics"])
    state["details_scraped"] = sum(1 for t in cache["topics"].values() if t.get("status") == "success")
    state["details_blocked"] = sum(1 for t in cache["topics"].values() if t.get("status") == "blocked")
    cache["scrape_state"] = state

    # Save
    save_cache(cache)

    # Summary
    print(f"\n=== Summary ===")
    print(f"Topics: {state['topics_scraped']}")
    print(f"Details scraped: {state['details_scraped']}")
    print(f"Details blocked: {state['details_blocked']}")
    print(f"Pending: {state['topics_scraped'] - state['details_scraped'] - state['details_blocked']}")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
