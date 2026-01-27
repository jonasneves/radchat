"""
Phone Catalog Tool - Duke Radiology contact lookup
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_FILE = Path(__file__).parent.parent / "data" / "contacts.json"
_contacts_cache: Optional[dict] = None


def load_contacts() -> dict:
    global _contacts_cache
    if _contacts_cache is not None:
        return _contacts_cache

    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            _contacts_cache = json.load(f)
    else:
        _contacts_cache = {"metadata": {}, "contacts": [], "routing_rules": []}

    return _contacts_cache


def get_time_context() -> dict:
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()

    is_weekend = weekday >= 5
    is_business_hours = 7 <= hour < 17 and not is_weekend

    return {
        "current_time": now.strftime("%H:%M"),
        "day": now.strftime("%A"),
        "is_weekend": is_weekend,
        "is_business_hours": is_business_hours,
        "is_after_hours": not is_business_hours,
    }


def is_available_now(contact: dict, time_ctx: dict) -> bool:
    availability = contact.get("availability", "").lower()
    if not availability:
        return True

    if time_ctx["is_business_hours"]:
        return "business hours" in availability or "7:30am-5pm" in availability
    if time_ctx["is_weekend"]:
        return "weekend" in availability or "after-hours" in availability
    return "after-hours" in availability


def search_contacts(
    query: str,
    modality: Optional[str] = None,
    contact_type: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """Search Duke Radiology phone directory."""
    data = load_contacts()
    contacts = data.get("contacts", [])
    query_lower = query.lower() if query else ""
    time_ctx = get_time_context()

    results = []

    for contact in contacts:
        score = 0

        if query_lower:
            if query_lower in contact.get("department", "").lower():
                score += 10
            if query_lower in contact.get("description", "").lower():
                score += 5
            for mod in contact.get("modalities", []):
                if query_lower in mod.lower():
                    score += 8
            for region in contact.get("anatomical_regions", []):
                if query_lower in region.lower():
                    score += 6
            for proc in contact.get("procedures", []):
                if query_lower in proc.lower():
                    score += 7
            if score == 0:
                continue

        if modality:
            mods = [m.lower() for m in contact.get("modalities", [])]
            if modality.lower() not in mods:
                continue
            score += 3

        if contact_type and contact.get("study_status") != contact_type:
            continue

        if location and location.lower() not in contact.get("location", "").lower():
            continue

        results.append({
            **contact,
            "relevance_score": score,
            "available_now": is_available_now(contact, time_ctx),
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)

    return {
        "results": results[:10],
        "total_matches": len(results),
        "time_context": time_ctx,
    }


def get_reading_room(modality: str, body_region: Optional[str] = None) -> dict:
    """Get reading room contact for a modality."""
    query = f"{modality} {body_region}" if body_region else modality
    results = search_contacts(query, contact_type="interpretation_questions")

    available = [r for r in results["results"] if r.get("available_now")]
    time_ctx = results["time_context"]

    if available:
        return {"contact": available[0], "alternatives": available[1:3], "time_context": time_ctx}
    if results["results"]:
        return {"contact": results["results"][0], "alternatives": [], "time_context": time_ctx}
    return {"error": f"No reading room found for {modality}", "time_context": time_ctx}


def get_procedure_contact(procedure: str) -> dict:
    """Get contact for procedure requests."""
    results = search_contacts(procedure, contact_type="procedure_request")
    time_ctx = results["time_context"]

    if results["results"]:
        return {"contact": results["results"][0], "time_context": time_ctx}

    # Fallback to VIR
    vir = search_contacts("VIR", contact_type="procedure_request")
    if vir["results"]:
        return {
            "contact": vir["results"][0],
            "note": f"VIR resident handles {procedure} requests",
            "time_context": time_ctx,
        }

    return {"error": f"No contact found for {procedure}", "time_context": time_ctx}


# Tool definitions for Claude
PHONE_CATALOG_TOOLS = [
    {
        "name": "search_phone_directory",
        "description": "Search Duke Radiology phone directory for contacts including reading rooms, scheduling lines, tech teams, and procedure contacts. Returns contacts sorted by relevance with current availability status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (e.g., 'CT reading room', 'MRI scheduling', 'VIR', 'chest')",
                },
                "modality": {
                    "type": "string",
                    "description": "Filter by imaging modality",
                    "enum": ["CT", "MRI", "XR", "US", "PET", "nuclear medicine", "mammography"],
                },
                "contact_type": {
                    "type": "string",
                    "description": "Filter by contact type",
                    "enum": ["interpretation_questions", "scheduling_inpatient", "tech_scheduling", "scanner_direct", "procedure_request"],
                },
                "location": {
                    "type": "string",
                    "description": "Filter by location",
                    "enum": ["Duke North", "DMP", "Cancer Center", "ED"],
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_reading_room_contact",
        "description": "Get the reading room phone number for a specific imaging modality. Automatically considers current time for after-hours routing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modality": {
                    "type": "string",
                    "description": "Imaging modality (CT, MRI, XR, US, PET)",
                },
                "body_region": {
                    "type": "string",
                    "description": "Body region (neuro, chest, body, abdomen, msk, breast, pediatric)",
                },
            },
            "required": ["modality"],
        },
    },
    {
        "name": "get_procedure_contact",
        "description": "Get contact for procedure requests like PICC lines, biopsies, drains, paracentesis, thoracentesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "procedure": {
                    "type": "string",
                    "description": "Procedure type (picc_line, tunneled_line, biopsy, drain, paracentesis, thoracentesis, lumbar_puncture)",
                },
            },
            "required": ["procedure"],
        },
    },
]


def execute_phone_tool(name: str, args: dict) -> dict:
    """Execute a phone catalog tool."""
    if name == "search_phone_directory":
        return search_contacts(
            args.get("query", ""),
            args.get("modality"),
            args.get("contact_type"),
            args.get("location"),
        )
    elif name == "get_reading_room_contact":
        return get_reading_room(args.get("modality", ""), args.get("body_region"))
    elif name == "get_procedure_contact":
        return get_procedure_contact(args.get("procedure", ""))
    else:
        return {"error": f"Unknown tool: {name}"}
