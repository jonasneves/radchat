"""
Phone Catalog Tool - Duke Radiology contact lookup
Full implementation with time-aware routing and comprehensive search.
"""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
CONTACTS_FILE = Path(__file__).parent.parent / "data" / "contacts.json"


@lru_cache(maxsize=1)
def load_contacts() -> dict:
    """Load contacts from local file."""
    try:
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"metadata": {}, "contacts": [], "routing_rules": []}


def is_after_hours() -> bool:
    """Check if current time is after hours (weekday 5pm-7:30am or weekend)."""
    now = datetime.now(EASTERN)
    day_of_week = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour
    minute = now.minute

    # Weekend (Saturday=5, Sunday=6)
    if day_of_week >= 5:
        return True

    # Weekday after-hours: before 7:30am or after 5pm
    if hour < 7 or (hour == 7 and minute < 30):
        return True
    if hour >= 17:  # 5pm or later
        return True

    return False


def get_time_context() -> dict:
    """Get current time context for routing decisions."""
    now = datetime.now(EASTERN)
    after_hours = is_after_hours()
    day_of_week = now.weekday()

    return {
        "current_time": now.strftime("%I:%M %p"),
        "day": now.strftime("%A"),
        "is_weekend": day_of_week >= 5,
        "is_business_hours": not after_hours,
        "is_after_hours": after_hours,
    }


def is_available_now(contact: dict, time_ctx: dict) -> bool:
    """Check if contact is available based on current time."""
    availability = contact.get("availability", "").lower()
    if not availability:
        return True

    if time_ctx["is_business_hours"]:
        return "business hours" in availability or "7:30am-5pm" in availability
    if time_ctx["is_weekend"]:
        return "weekend" in availability or "after-hours" in availability
    return "after-hours" in availability


def search_by_modality(contacts: list, modality: str) -> list:
    """Search contacts by imaging modality."""
    modality_lower = modality.lower()
    results = []
    for contact in contacts:
        modalities = [m.lower() for m in contact.get("modalities", [])]
        if modality_lower in modalities:
            results.append(contact)
    return results


def search_by_anatomical_region(contacts: list, region: str) -> list:
    """Search contacts by anatomical region."""
    region_lower = region.lower()
    results = []
    for contact in contacts:
        regions = [r.lower() for r in contact.get("anatomical_regions", [])]
        if region_lower in regions or any(region_lower in r for r in regions):
            results.append(contact)
    return results


def search_by_procedure(contacts: list, procedure: str) -> list:
    """Search contacts by procedure type."""
    procedure_lower = procedure.lower()
    results = []
    for contact in contacts:
        procedures = [p.lower() for p in contact.get("procedures", [])]
        if procedure_lower in procedures or any(procedure_lower in p for p in procedures):
            results.append(contact)
    return results


def search_by_department(contacts: list, department: str) -> list:
    """Search contacts by department name."""
    department_lower = department.lower()
    results = []
    for contact in contacts:
        dept = contact.get("department", "").lower()
        if department_lower in dept:
            results.append(contact)
    return results


def search_by_study_status(contacts: list, status: str) -> list:
    """Search contacts by study status."""
    status_lower = status.lower()
    results = []
    for contact in contacts:
        contact_status = contact.get("study_status", "").lower()
        if status_lower in contact_status:
            results.append(contact)
    return results


def search_by_location(contacts: list, location: str) -> list:
    """Search contacts by location."""
    location_lower = location.lower()
    results = []
    for contact in contacts:
        loc = contact.get("location", "").lower()
        if location_lower in loc:
            results.append(contact)
    return results


def get_contact_by_id(contact_id: str) -> Optional[dict]:
    """Get a specific contact by ID."""
    data = load_contacts()
    for contact in data.get("contacts", []):
        if contact.get("id") == contact_id:
            return contact
    return None


def get_after_hours_contacts() -> list:
    """Get after-hours contacts based on current time."""
    after_hours_contacts = []

    # Senior resident for CT/MRI/NucMed
    senior = get_contact_by_id("senior_resident_afterhours")
    if senior:
        after_hours_contacts.append(senior)

    # Junior resident for X-ray/Ultrasound
    xray_after = get_contact_by_id("xray_ed_op_afterhours")
    if xray_after:
        after_hours_contacts.append(xray_after)

    # Ultrasound after-hours
    us_after = get_contact_by_id("ultrasound_afterhours")
    if us_after:
        after_hours_contacts.append(us_after)

    return after_hours_contacts


def semantic_search(contacts: list, query: str) -> list:
    """Perform semantic search across all contact fields."""
    query_lower = query.lower()
    results = []

    for contact in contacts:
        searchable_text = " ".join([
            contact.get("department", ""),
            contact.get("description", ""),
            " ".join(contact.get("modalities", [])),
            " ".join(contact.get("anatomical_regions", [])),
            " ".join(contact.get("procedures", [])),
            contact.get("availability", ""),
            contact.get("notes", ""),
            contact.get("location", ""),
        ]).lower()

        if query_lower in searchable_text:
            results.append(contact)

    return results


def search_contacts(
    query: str,
    modality: Optional[str] = None,
    anatomical_region: Optional[str] = None,
    procedure: Optional[str] = None,
    department: Optional[str] = None,
    contact_type: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """
    Search Duke Radiology phone directory.

    Args:
        query: Free-text search term
        modality: Imaging modality (CT, MRI, XR, US, PET, nuclear medicine)
        anatomical_region: Body region (neuro, chest, abdomen, msk, etc.)
        procedure: Procedure type (tunneled_line, picc_line, biopsy, etc.)
        department: Department name
        contact_type: study_status filter (interpretation_questions, scheduling_inpatient, etc.)
        location: Location filter (Duke North, DMP, Cancer Center, ED)

    Returns:
        Dict with contacts, time_context, and after_hours info
    """
    data = load_contacts()
    contacts = data.get("contacts", [])
    time_ctx = get_time_context()

    # Start with all contacts or semantic search if query provided
    if query:
        results = set(contacts.index(c) for c in semantic_search(contacts, query))
    else:
        results = set(range(len(contacts)))

    # Apply filters
    if modality:
        matches = search_by_modality(contacts, modality)
        results &= {contacts.index(c) for c in matches}

    if anatomical_region:
        matches = search_by_anatomical_region(contacts, anatomical_region)
        results &= {contacts.index(c) for c in matches}

    if procedure:
        matches = search_by_procedure(contacts, procedure)
        results &= {contacts.index(c) for c in matches}

    if department:
        matches = search_by_department(contacts, department)
        results &= {contacts.index(c) for c in matches}

    if contact_type:
        matches = search_by_study_status(contacts, contact_type)
        results &= {contacts.index(c) for c in matches}

    if location:
        matches = search_by_location(contacts, location)
        results &= {contacts.index(c) for c in matches}

    # Get filtered contacts with availability
    filtered = []
    for i in sorted(results):
        contact = contacts[i].copy()
        contact["available_now"] = is_available_now(contact, time_ctx)
        filtered.append(contact)

    # Sort by relevance (available contacts first)
    filtered.sort(key=lambda x: (not x["available_now"], x.get("department", "")))

    response = {
        "results": filtered[:15],
        "total_matches": len(filtered),
        "time_context": time_ctx,
    }

    # Add after-hours information if relevant
    if time_ctx["is_after_hours"] and contact_type == "interpretation_questions":
        response["after_hours_contacts"] = get_after_hours_contacts()
        response["after_hours_note"] = (
            f"It's currently after-hours ({time_ctx['current_time']} on {time_ctx['day']}). "
            "After-hours contacts are included."
        )

    return response


def get_reading_room(modality: str, body_region: Optional[str] = None) -> dict:
    """Get reading room contact for a modality and optional body region."""
    results = search_contacts(
        query=f"{modality} {body_region}" if body_region else modality,
        modality=modality,
        anatomical_region=body_region,
        contact_type="interpretation_questions",
    )

    available = [r for r in results["results"] if r.get("available_now")]
    time_ctx = results["time_context"]

    if available:
        return {
            "contact": available[0],
            "alternatives": available[1:3],
            "time_context": time_ctx,
        }
    if results["results"]:
        response = {
            "contact": results["results"][0],
            "alternatives": [],
            "time_context": time_ctx,
        }
        # Add after-hours contacts if applicable
        if time_ctx["is_after_hours"]:
            response["after_hours_contacts"] = get_after_hours_contacts()
        return response

    return {"error": f"No reading room found for {modality}", "time_context": time_ctx}


def get_procedure_contact(procedure: str) -> dict:
    """Get contact for procedure requests."""
    results = search_contacts(procedure, procedure=procedure, contact_type="procedure_request")
    time_ctx = results["time_context"]

    if results["results"]:
        return {"contact": results["results"][0], "time_context": time_ctx}

    # Fallback to VIR
    vir = get_contact_by_id("vir_resident")
    if vir:
        return {
            "contact": vir,
            "note": f"VIR resident handles {procedure} requests",
            "time_context": time_ctx,
        }

    return {"error": f"No contact found for {procedure}", "time_context": time_ctx}


def get_scheduling_contact(modality: str, location: Optional[str] = None) -> dict:
    """Get scheduling contact for a modality and optional location."""
    results = search_contacts(
        query="",
        modality=modality,
        contact_type="scheduling_inpatient",
        location=location,
    )
    time_ctx = results["time_context"]

    if results["results"]:
        return {
            "contacts": results["results"],
            "time_context": time_ctx,
        }

    return {"error": f"No scheduling contact found for {modality}", "time_context": time_ctx}


def list_contacts_by_type(contact_type: str) -> dict:
    """List all contacts of a specific type."""
    results = search_contacts(query="", contact_type=contact_type)
    return {
        "contacts": results["results"],
        "total": results["total_matches"],
        "time_context": results["time_context"],
    }


# Tool definitions for Claude
PHONE_CATALOG_TOOLS = [
    {
        "name": "search_phone_directory",
        "description": "Search Duke Radiology phone directory for contacts including reading rooms, scheduling lines, tech teams, scanners, and procedure contacts. Returns contacts sorted by relevance with current availability status.",
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
                    "enum": ["CT", "MRI", "XR", "US", "PET", "nuclear medicine", "mammography", "fluoro"],
                },
                "anatomical_region": {
                    "type": "string",
                    "description": "Filter by body region. For breast queries, always use 'breast' regardless of modality.",
                    "enum": ["neuro", "head", "brain", "spine", "chest", "lung", "abdomen", "pelvis", "body", "msk", "musculoskeletal", "breast", "vascular", "pediatric"],
                },
                "procedure": {
                    "type": "string",
                    "description": "Filter by procedure type",
                    "enum": ["tunneled_line", "picc_line", "biopsy", "drain_placement", "paracentesis", "thoracentesis", "LP", "lumbar_puncture", "GI"],
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
                    "description": "Imaging modality",
                    "enum": ["CT", "MRI", "XR", "US", "PET", "nuclear medicine"],
                },
                "body_region": {
                    "type": "string",
                    "description": "Body region",
                    "enum": ["neuro", "chest", "body", "abdomen", "pelvis", "msk", "breast", "pediatric"],
                },
            },
            "required": ["modality"],
        },
    },
    {
        "name": "get_procedure_contact",
        "description": "Get contact for procedure requests like PICC lines, tunneled lines, biopsies, drains, paracentesis, thoracentesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "procedure": {
                    "type": "string",
                    "description": "Procedure type",
                    "enum": ["tunneled_line", "picc_line", "biopsy", "drain_placement", "paracentesis", "thoracentesis", "lumbar_puncture"],
                },
            },
            "required": ["procedure"],
        },
    },
    {
        "name": "get_scheduling_contact",
        "description": "Get scheduling contact for a specific modality and location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "modality": {
                    "type": "string",
                    "description": "Imaging modality",
                    "enum": ["CT", "MRI", "XR", "US", "PET", "nuclear medicine"],
                },
                "location": {
                    "type": "string",
                    "description": "Hospital location",
                    "enum": ["Duke North", "DMP", "Cancer Center", "ED"],
                },
            },
            "required": ["modality"],
        },
    },
    {
        "name": "list_contacts_by_type",
        "description": "List all contacts of a specific type (reading rooms, scheduling, tech teams, scanners, procedures).",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_type": {
                    "type": "string",
                    "description": "Type of contact to list",
                    "enum": ["interpretation_questions", "scheduling_inpatient", "tech_scheduling", "scanner_direct", "procedure_request"],
                },
            },
            "required": ["contact_type"],
        },
    },
]


def execute_phone_tool(name: str, args: dict) -> dict:
    """Execute a phone catalog tool."""
    if name == "search_phone_directory":
        return search_contacts(
            args.get("query", ""),
            args.get("modality"),
            args.get("anatomical_region"),
            args.get("procedure"),
            args.get("department"),
            args.get("contact_type"),
            args.get("location"),
        )
    elif name == "get_reading_room_contact":
        return get_reading_room(args.get("modality", ""), args.get("body_region"))
    elif name == "get_procedure_contact":
        return get_procedure_contact(args.get("procedure", ""))
    elif name == "get_scheduling_contact":
        return get_scheduling_contact(args.get("modality", ""), args.get("location"))
    elif name == "list_contacts_by_type":
        return list_contacts_by_type(args.get("contact_type", ""))
    else:
        return {"error": f"Unknown tool: {name}"}
