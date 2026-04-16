import csv
import copy
from datetime import date
import io
import json
import os
import sqlite3

from flask import Flask, Response, redirect, render_template, request, url_for

app = Flask(__name__)

def get_current_academic_term():
    today = date.today()
    # Simple two-term model:
    # Jan-Jun -> Winter, Jul-Dec -> Fall.
    term = "Winter" if today.month <= 6 else "Fall"
    return today.year, term


CURRENT_YEAR, CURRENT_TERM = get_current_academic_term()
VALID_TERMS = {"Fall", "Winter"}
TERM_ORDER = ["Winter", "Fall"]

EVENT_SABBATICAL = "sabbatical_leave"
EVENT_MEDICAL = "medical_leave"
EVENT_MEDICAL_EXT = "medical_leave_with_extension"
EVENT_MEDICAL_EXCL = "medical_leave_with_exclusion"
EVENT_EXCLUSION = "exclusion"
EVENT_EXTENSION = "extension"

BLOCKING_EVENT_TYPES = {
    EVENT_SABBATICAL,
    EVENT_MEDICAL,
    EVENT_MEDICAL_EXT,
    EVENT_MEDICAL_EXCL,
    EVENT_EXCLUSION,
}

TENURE_COUNTER_STOP_TYPES = {
    EVENT_MEDICAL_EXT,
    EVENT_MEDICAL_EXCL,
    EVENT_EXCLUSION,
    EVENT_EXTENSION,
}

TERM_COUNT_STOP_TYPES = {
    EVENT_MEDICAL_EXT,
    EVENT_MEDICAL_EXCL,
    EVENT_EXCLUSION,
    EVENT_EXTENSION,
}

MEDICAL_MIN_TERMS = {
    EVENT_MEDICAL: 1,
    EVENT_MEDICAL_EXT: 2,
    EVENT_MEDICAL_EXCL: 2,
}

EVENT_LABELS = {
    EVENT_SABBATICAL: "Sabbatical Leave",
    EVENT_MEDICAL: "Medical Leave",
    EVENT_MEDICAL_EXT: "Medical Leave with Extension",
    EVENT_MEDICAL_EXCL: "Medical Leave with Exclusion",
    EVENT_EXCLUSION: "Exclusion",
    EVENT_EXTENSION: "Extension",
}

RENEW_STATUS = ["scheduled", "passed", "failed", "extend"]
TENURE_REVIEW_STATUS = ["scheduled", "passed", "failed"]
NEXT_RENEW_STATUS = ["", "scheduled", "passed", "failed", "extend"]
TITLE_OPTIONS = ["", "Assistant Professor", "Associate Professor", "Full Professor"]
SERVICE_ROLE_OPTIONS = [
    "",
    "Fellowship",
    "Faculty Director",
    "Area Chair",
    "Program Director",
    "Committee Chair",
]
SENIOR_TITLES = {"Associate Professor", "Full Professor"}

# Seed data for app startup / reset fallback.
INITIAL_EMPLOYEES = {
    "E1001": {
        "employee_id": "E1001",
        "name": "",
        "hire_year": "",
        "hire_term": "",
        "tenure_package_year": "",
        "tenure_package_term": "",
        "checkpoint_status": {
            "first_renew": "scheduled",
            "second_renew": "scheduled",
            "tenure_review": "scheduled",
            "first_renew_next": "",
            "second_renew_next": "",
        },
        "events": [],
        "timeline_overrides": {},
        "title_assignments": [],
        "title_assignment": {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        },
        "service_role_assignments": [],
        "service_role_assignment": {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        },
    },
    "123": {
        "employee_id": "123",
        "name": "Roman Kapuscinski",
        "hire_year": "1990",
        "hire_term": "Fall",
        "tenure_package_year": "",
        "tenure_package_term": "",
        "checkpoint_status": {
            "first_renew": "passed",
            "second_renew": "passed",
            "tenure_review": "passed",
            "first_renew_next": "",
            "second_renew_next": "",
        },
        "events": [
            {
                "event_type": EVENT_SABBATICAL,
                "start_year": 2010,
                "start_term": "Fall",
                "end_year": 2011,
                "end_term": "Fall",
                "sabbatical_duration": 2,
                "status": "approved",
                "source": "hr",
            },
            {
                "event_type": EVENT_SABBATICAL,
                "start_year": 1998,
                "start_term": "Fall",
                "end_year": 1998,
                "end_term": "Winter",
                "sabbatical_duration": 1,
                "status": "approved",
                "source": "hr",
            },
        ],
        "timeline_overrides": {},
        "title_assignments": [
            {
                "name": "Assistant Professor",
                "start_year": "1990",
                "start_term": "Fall",
                "end_year": "1996",
                "end_term": "Winter",
            },
            {
                "name": "Associate Professor",
                "start_year": "1997",
                "start_term": "Fall",
                "end_year": "2004",
                "end_term": "Fall",
            },
        ],
        "title_assignment": {
            "name": "Assistant Professor",
            "start_year": "1990",
            "start_term": "Fall",
            "end_year": "1996",
            "end_term": "Winter",
        },
        "service_role_assignments": [
            {
                "name": "Fellowship",
                "start_year": "1999",
                "start_term": "Fall",
                "end_year": "2010",
                "end_term": "Winter",
            }
        ],
        "service_role_assignment": {
            "name": "Fellowship",
            "start_year": "1999",
            "start_term": "Fall",
            "end_year": "2010",
            "end_term": "Winter",
        },
    },
    "666": {
        "employee_id": "666",
        "name": "Adrian",
        "hire_year": "2020",
        "hire_term": "Fall",
        # Custom package timing so tenure review occurs in 2025.
        "tenure_package_year": "2024",
        "tenure_package_term": "Winter",
        "checkpoint_status": {
            "first_renew": "failed",
            "second_renew": "passed",
            "tenure_review": "failed",
            "first_renew_next": "passed",
            "second_renew_next": "",
        },
        "events": [
            {
                "event_type": EVENT_MEDICAL,
                "start_year": 2023,
                "start_term": "Fall",
                "end_year": 2023,
                "end_term": "Fall",
                "sabbatical_duration": 1,
                "status": "approved",
                "source": "hr",
            }
        ],
        "timeline_overrides": {},
        "title_assignments": [
            {
                "name": "Assistant Professor",
                "start_year": "2020",
                "start_term": "Fall",
                "end_year": "2026",
                "end_term": "Winter",
            }
        ],
        "title_assignment": {
            "name": "Assistant Professor",
            "start_year": "2020",
            "start_term": "Fall",
            "end_year": "2026",
            "end_term": "Winter",
        },
        "service_role_assignments": [
            {
                "name": "Committee Chair",
                "start_year": "2023",
                "start_term": "Fall",
                "end_year": "2025",
                "end_term": "Winter",
            }
        ],
        "service_role_assignment": {
            "name": "Committee Chair",
            "start_year": "2023",
            "start_term": "Fall",
            "end_year": "2025",
            "end_term": "Winter",
        },
    },
}

DB_PATH = os.environ.get("SABBATICAL_DB_PATH", os.path.join(os.path.dirname(__file__), "sabbatical.db"))
EMPLOYEES = copy.deepcopy(INITIAL_EMPLOYEES)


def default_employee_record(employee_id):
    return {
        "employee_id": employee_id,
        "name": "",
        "hire_year": "",
        "hire_term": "",
        "tenure_package_year": "",
        "tenure_package_term": "",
        "checkpoint_status": {
            "first_renew": "scheduled",
            "second_renew": "scheduled",
            "tenure_review": "scheduled",
            "first_renew_next": "",
            "second_renew_next": "",
        },
        "events": [],
        "timeline_overrides": {},
        "title_assignments": [],
        "title_assignment": {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        },
        "service_role_assignments": [],
        "service_role_assignment": {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        },
    }


def normalize_employee_record(employee_id, raw):
    base = default_employee_record(employee_id)
    if not isinstance(raw, dict):
        return base

    base["employee_id"] = str(raw.get("employee_id") or employee_id)
    for key in ("name", "hire_year", "hire_term", "tenure_package_year", "tenure_package_term"):
        if key in raw:
            base[key] = str(raw.get(key) or "")

    checkpoint = raw.get("checkpoint_status")
    if isinstance(checkpoint, dict):
        for key in ("first_renew", "second_renew", "tenure_review"):
            val = checkpoint.get(key, "scheduled")
            if key == "tenure_review":
                base["checkpoint_status"][key] = val if val in TENURE_REVIEW_STATUS else "scheduled"
            else:
                base["checkpoint_status"][key] = val if val in RENEW_STATUS else "scheduled"
        for key in ("first_renew_next", "second_renew_next"):
            val = checkpoint.get(key, "")
            base["checkpoint_status"][key] = val if val in NEXT_RENEW_STATUS else ""

    events = raw.get("events")
    if isinstance(events, list):
        base["events"] = [e for e in events if isinstance(e, dict)]

    overrides = raw.get("timeline_overrides")
    if isinstance(overrides, dict):
        cleaned = {}
        for k, v in overrides.items():
            if isinstance(v, dict):
                cleaned[str(k)] = {str(x): ("" if y is None else str(y)) for x, y in v.items()}
        base["timeline_overrides"] = cleaned

    for key in ("title_assignments", "service_role_assignments"):
        arr = raw.get(key)
        if isinstance(arr, list):
            base[key] = [x for x in arr if isinstance(x, dict)]

    for key in ("title_assignment", "service_role_assignment"):
        val = raw.get(key)
        if isinstance(val, dict):
            base[key] = val

    return base


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_employees_to_db():
    init_db()
    data = json.dumps(EMPLOYEES, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_state (id, data, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                data = excluded.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (data,),
        )


def load_employees_from_db():
    global EMPLOYEES
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT data FROM app_state WHERE id = 1").fetchone()
    if not row:
        save_employees_to_db()
        return
    try:
        parsed = json.loads(row[0])
        if not isinstance(parsed, dict):
            return
        normalized = {}
        for employee_id, raw in parsed.items():
            employee_key = str(employee_id)
            normalized[employee_key] = normalize_employee_record(employee_key, raw)
        if normalized:
            EMPLOYEES = normalized
    except (json.JSONDecodeError, TypeError, ValueError):
        # keep current in-memory defaults if DB is malformed
        return


def refresh_employees():
    load_employees_from_db()
    changed = False
    for emp in EMPLOYEES.values():
        if clear_legacy_bulk_calculated_overrides(emp):
            changed = True
        if prune_redundant_timeline_overrides(emp):
            changed = True
    if changed:
        save_employees_to_db()


def append_event_atomic(employee_id, event):
    global EMPLOYEES
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT data FROM app_state WHERE id = 1").fetchone()
        if row:
            try:
                parsed = json.loads(row[0])
                current = parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                current = {}
        else:
            current = {}

        normalized = {}
        for key, raw in current.items():
            employee_key = str(key)
            normalized[employee_key] = normalize_employee_record(employee_key, raw)
        if not normalized:
            normalized = copy.deepcopy(INITIAL_EMPLOYEES)

        emp = normalized.get(employee_id) or default_employee_record(employee_id)
        emp["events"] = list(emp.get("events", []))
        emp["events"].append(event)
        normalized[employee_id] = normalize_employee_record(employee_id, emp)

        conn.execute(
            """
            INSERT INTO app_state (id, data, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                data = excluded.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(normalized, ensure_ascii=False),),
        )
        EMPLOYEES = normalized


def clear_leave_type_overrides(emp):
    overrides = emp.get("timeline_overrides") or {}
    cleaned = {}
    for key, override in overrides.items():
        if not isinstance(override, dict):
            continue
        new_override = dict(override)
        new_override["leave_types"] = ""
        if any((str(v).strip() != "") for k, v in new_override.items() if k != "leave_types"):
            cleaned[key] = new_override
    emp["timeline_overrides"] = cleaned


def clear_calculated_timeline_overrides(emp):
    # Remove stale computed-field overrides so timeline logic can recompute
    # after profile/event changes (e.g., term-count stop rules).
    overrides = emp.get("timeline_overrides") or {}
    cleaned = {}
    computed_fields = {
        "term_count",
        "sabbaticals_counter",
        "sabbatical_bank",
        "eligibility_status",
        "review_event",
        "renew_event",
        "leave_types",
    }
    for key, override in overrides.items():
        if not isinstance(override, dict):
            continue
        new_override = dict(override)
        for field in computed_fields:
            new_override[field] = ""
        if any((str(v).strip() != "") for _, v in new_override.items()):
            cleaned[key] = new_override
    emp["timeline_overrides"] = cleaned


def parse_int(value, field_name, required=True):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"Missing required field: {field_name}")
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for field: {field_name}") from exc


def parse_term(value, field_name, required=True):
    if value is None or value == "":
        if required:
            raise ValueError(f"Missing required field: {field_name}")
        return None
    if value not in VALID_TERMS:
        raise ValueError(f"Invalid term for field: {field_name}")
    return value


def get_term_index(year, term):
    if term not in VALID_TERMS:
        raise ValueError(f"Unknown term: {term}")
    return year * 2 + (0 if term == "Winter" else 1)


def get_year_term(index):
    return index // 2, "Winter" if index % 2 == 0 else "Fall"


def term_count(start_year, start_term, end_year, end_term):
    return get_term_index(end_year, end_term) - get_term_index(start_year, start_term) + 1


def get_employee(employee_id):
    return EMPLOYEES.get(employee_id)


def ensure_employee(employee_id):
    if employee_id not in EMPLOYEES:
        EMPLOYEES[employee_id] = default_employee_record(employee_id)
    return EMPLOYEES[employee_id]


def is_term_blocked(term_idx, approved_events):
    for e in approved_events:
        if e["event_type"] not in BLOCKING_EVENT_TYPES:
            continue
        s = get_term_index(e["start_year"], e["start_term"])
        t = get_term_index(e["end_year"], e["end_term"])
        if s <= term_idx <= t:
            return True, e["event_type"]
    return False, None


def event_types_at_term(term_idx, approved_events):
    types = set()
    for e in approved_events:
        s = get_term_index(e["start_year"], e["start_term"])
        t = get_term_index(e["end_year"], e["end_term"])
        if s <= term_idx <= t:
            types.add(e["event_type"])
    return types


def collect_leave_maps(approved_events):
    term_map = {}
    year_map = {}
    for e in approved_events:
        e_type = e.get("event_type")
        if e_type not in EVENT_LABELS:
            continue
        label = EVENT_LABELS.get(e_type, e_type)
        s_idx = get_term_index(e["start_year"], e["start_term"])
        e_idx = get_term_index(e["end_year"], e["end_term"])
        for idx in range(s_idx, e_idx + 1):
            term_map.setdefault(idx, [])
            if label not in term_map[idx]:
                term_map[idx].append(label)
            year, _ = get_year_term(idx)
            year_map.setdefault(year, [])
            if label not in year_map[year]:
                year_map[year].append(label)
    return term_map, year_map


def build_checkpoint_schedule(hire_idx, package_idx):
    return {
        "first_renew": hire_idx + 3,
        "second_renew": hire_idx + 7,
        "tenure_package": package_idx,
        "tenure_review_1": package_idx + 1,
        "tenure_review_2": package_idx + 2,
    }


def parse_optional_assignment(assignment, field_prefix):
    name = (assignment.get("name") or "").strip()
    start_year_raw = (assignment.get("start_year") or "").strip()
    start_term_raw = assignment.get("start_term") or ""
    end_year_raw = (assignment.get("end_year") or "").strip()
    end_term_raw = assignment.get("end_term") or ""

    any_filled = any([name, start_year_raw, start_term_raw, end_year_raw, end_term_raw])
    if not any_filled:
        return None

    if not (name and start_year_raw and start_term_raw):
        raise ValueError(f"Incomplete {field_prefix} assignment. Please fill name/start year+term.")

    # If end time is omitted, default to current term/year ("until now").
    if end_year_raw == "" and end_term_raw == "":
        end_year_raw = str(CURRENT_YEAR)
        end_term_raw = CURRENT_TERM
    elif end_year_raw == "" or end_term_raw == "":
        raise ValueError(f"Incomplete {field_prefix} assignment end time. Fill both end year and end term, or leave both empty.")

    start_year = parse_int(start_year_raw, f"{field_prefix}_start_year")
    start_term = parse_term(start_term_raw, f"{field_prefix}_start_term")
    end_year = parse_int(end_year_raw, f"{field_prefix}_end_year")
    end_term = parse_term(end_term_raw, f"{field_prefix}_end_term")

    start_idx = get_term_index(start_year, start_term)
    end_idx = get_term_index(end_year, end_term)
    if end_idx < start_idx:
        raise ValueError(f"{field_prefix} end must be after or equal to start")

    return {
        "name": name,
        "start_idx": start_idx,
        "end_idx": end_idx,
    }


def assignment_applies_to_term(assignment, term_idx):
    if not assignment:
        return False
    return assignment["start_idx"] <= term_idx <= assignment["end_idx"]


def parse_assignment_list(assignments, field_prefix):
    parsed = []
    if not assignments:
        return parsed
    for assignment in assignments:
        try:
            parsed_item = parse_optional_assignment(assignment or {}, field_prefix)
            if parsed_item:
                parsed.append(parsed_item)
        except ValueError:
            # Tolerate incomplete rows from UI edits so profile save/render doesn't fail.
            continue
    return parsed


def assignment_name_for_term(assignments, term_idx):
    if not assignments:
        return ""
    selected = ""
    for item in assignments:
        if assignment_applies_to_term(item, term_idx):
            selected = item["name"]
    return selected


def assignment_names_for_term(assignments, term_idx):
    if not assignments:
        return ""
    names = []
    seen = set()
    for item in assignments:
        if assignment_applies_to_term(item, term_idx):
            name = item.get("name", "")
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return " / ".join(names)


def effective_title_assignments(employee):
    assignments = parse_assignment_list(employee.get("title_assignments", []), "title")
    if not assignments:
        fallback_title = parse_optional_assignment(employee.get("title_assignment", {}), "title")
        if fallback_title:
            assignments = [fallback_title]
    return assignments


def checkpoints_disabled_for_employee(employee):
    # Disable renew/review/tenure checkpoints only when faculty starts as
    # Associate/Full at hire time.
    try:
        hire_year = parse_int(employee.get("hire_year"), "hire_year")
        hire_term = parse_term(employee.get("hire_term"), "hire_term")
    except ValueError:
        return False

    hire_idx = get_term_index(hire_year, hire_term)
    title_at_hire = assignment_name_for_term(effective_title_assignments(employee), hire_idx)
    return title_at_hire in SENIOR_TITLES


def merge_role_values(override_roles, computed_roles):
    override_roles = (override_roles or "").strip()
    computed_roles = (computed_roles or "").strip()
    if not override_roles:
        return computed_roles
    if not computed_roles:
        return override_roles

    merged = []
    seen = set()
    for part in (override_roles.split("/") + computed_roles.split("/")):
        name = part.strip()
        if name and name not in seen:
            merged.append(name)
            seen.add(name)
    return " / ".join(merged)


def build_assignment_rows_from_form(form, prefix):
    names = form.getlist(f"{prefix}_name_list")
    start_years = form.getlist(f"{prefix}_start_year_list")
    start_terms = form.getlist(f"{prefix}_start_term_list")
    end_years = form.getlist(f"{prefix}_end_year_list")
    end_terms = form.getlist(f"{prefix}_end_term_list")

    max_len = max(len(names), len(start_years), len(start_terms), len(end_years), len(end_terms), 0)
    rows = []
    for i in range(max_len):
        row = {
            "name": names[i].strip() if i < len(names) and names[i] else "",
            "start_year": start_years[i].strip() if i < len(start_years) and start_years[i] else "",
            "start_term": start_terms[i] if i < len(start_terms) else "",
            "end_year": end_years[i].strip() if i < len(end_years) and end_years[i] else "",
            "end_term": end_terms[i] if i < len(end_terms) else "",
        }
        if any(row.values()):
            rows.append(row)
    return rows


def build_employee_timeline(employee, years_ahead=6):
    hire_year = parse_int(employee.get("hire_year"), "hire_year")
    hire_term = parse_term(employee.get("hire_term"), "hire_term")

    hire_idx = get_term_index(hire_year, hire_term)
    current_idx = get_term_index(CURRENT_YEAR, CURRENT_TERM)

    package_year_raw = employee.get("tenure_package_year")
    package_term_raw = employee.get("tenure_package_term")
    checkpoint_status = employee.get("checkpoint_status", {})
    tenure_passed = checkpoint_status.get("tenure_review") == "passed"
    title_assignments = effective_title_assignments(employee)
    role_assignments = parse_assignment_list(employee.get("service_role_assignments", []), "service_role")
    if not role_assignments:
        fallback_role = parse_optional_assignment(employee.get("service_role_assignment", {}), "service_role")
        if fallback_role:
            role_assignments = [fallback_role]

    approved_events = [e for e in employee["events"] if e.get("status") == "approved"]
    checkpoints_disabled = checkpoints_disabled_for_employee(employee)
    leave_types_by_term, leave_types_by_year = collect_leave_maps(approved_events)
    sabbatical_starts = set()
    valid_terms = 0
    used = 0
    term_counter = 0
    tenure_counter = 0

    first_renew_idx = None
    second_renew_idx = None
    default_package_idx = None

    per_term = {}
    max_idx = max(current_idx, hire_idx + years_ahead * 2)

    for idx in range(hire_idx, max_idx + 1):
        year, term = get_year_term(idx)
        term_event_types = event_types_at_term(idx, approved_events)
        if not any(t in TERM_COUNT_STOP_TYPES for t in term_event_types):
            term_counter += 1
        if not any(t in TENURE_COUNTER_STOP_TYPES for t in term_event_types):
            tenure_counter += 1

        if not checkpoints_disabled:
            if first_renew_idx is None and tenure_counter >= 4:
                first_renew_idx = idx
            if second_renew_idx is None and tenure_counter >= 8:
                second_renew_idx = idx
            if default_package_idx is None and tenure_counter >= 12:
                default_package_idx = idx

        year_leave_types = leave_types_by_year.get(year, [])
        blocked = bool(year_leave_types)
        reason = "leave_year" if blocked else None
        if not blocked:
            valid_terms += 1

        # Sabbatical "usage" consumes one chance no matter 1 or 2 terms.
        taken_this_term = False
        # Tenure becomes active when review passes and package has been submitted.
        # Package submission defaults to the 12th tenure-counted term unless user overrides.
        package_idx_for_gate = default_package_idx if default_package_idx is not None else hire_idx + 11
        if package_year_raw and package_term_raw:
            package_idx_for_gate = get_term_index(
                parse_int(package_year_raw, "tenure_package_year"),
                parse_term(package_term_raw, "tenure_package_term"),
            )
            if package_idx_for_gate < hire_idx:
                package_idx_for_gate = hire_idx
        tenure_start_idx = package_idx_for_gate + 1

        title_this_term = assignment_name_for_term(title_assignments, idx)
        senior_title_this_term = title_this_term in SENIOR_TITLES

        tenure_rights_active = tenure_passed and idx >= tenure_start_idx
        senior_rights_active = senior_title_this_term
        sabbatical_rights_active = tenure_rights_active or senior_rights_active
        earned_total = valid_terms // 12
        available_before_use = earned_total - used if sabbatical_rights_active else 0
        can_use_sabbatical = sabbatical_rights_active and available_before_use >= 1
        for e in approved_events:
            if e["event_type"] != EVENT_SABBATICAL:
                continue
            start_idx = get_term_index(e["start_year"], e["start_term"])
            if start_idx == idx and can_use_sabbatical and start_idx not in sabbatical_starts:
                sabbatical_starts.add(start_idx)
                used += 1
                taken_this_term = True

        available = earned_total - used if sabbatical_rights_active else 0
        if sabbatical_rights_active:
            # Once bank earns +1, counter should roll over by 12 immediately.
            counter = valid_terms - earned_total * 12
        else:
            # Before tenure is passed, counter can continue beyond 12/12.
            counter = valid_terms
        tenure_active = tenure_rights_active

        if taken_this_term:
            eligibility = "Taken"
        elif senior_rights_active and available >= 1:
            eligibility = "Eligible - Not Taken"
        elif senior_rights_active and available < 1:
            eligibility = "Not Eligible"
        elif not tenure_active:
            eligibility = "Pre-tenure" if idx < tenure_start_idx else "Not Eligible"
        elif available >= 1:
            eligibility = "Eligible - Not Taken"
        else:
            eligibility = "Not Eligible"

        per_term[idx] = {
            "year": year,
            "term": term,
            "term_count": term_counter,
            "blocked": blocked,
            "reason": reason,
            "valid_terms": valid_terms,
            "counter": counter,
            "earned_total": earned_total,
            "used": used,
            "available": available,
            "eligibility": eligibility,
            "tenure_active": tenure_active,
            "taken_this_term": taken_this_term,
        }

    rows = []
    prev_available = None

    package_idx = default_package_idx if default_package_idx is not None else hire_idx + 11
    if package_year_raw and package_term_raw:
        package_idx = get_term_index(
            parse_int(package_year_raw, "tenure_package_year"),
            parse_term(package_term_raw, "tenure_package_term"),
        )
        if package_idx < hire_idx:
            package_idx = hire_idx
    tenure_review_1_idx = package_idx + 1
    tenure_review_2_idx = package_idx + 2
    checkpoint_schedule = {
        "first_renew": first_renew_idx,
        "second_renew": second_renew_idx,
        "tenure_package": package_idx,
        "tenure_review_1": tenure_review_1_idx,
        "tenure_review_2": tenure_review_2_idx,
    }
    auto_associate_start_idx = checkpoint_schedule["tenure_package"] + 1

    for idx in range(hire_idx, max_idx + 1):
        snap = per_term[idx]
        year = snap["year"]
        term = snap["term"]
        key = f"{year}_{term}"

        renew_event = []
        review_event = []

        if not checkpoints_disabled:
            first_status = checkpoint_status.get("first_renew", "scheduled")
            allow_first_renew = (
                checkpoint_schedule["first_renew"] is not None
                and checkpoint_schedule["first_renew"] < checkpoint_schedule["tenure_package"]
            )
            first_emoji = " 🎉" if first_status == "passed" else ""
            if allow_first_renew and checkpoint_schedule["first_renew"] is not None and checkpoint_schedule["first_renew"] == idx:
                renew_event.append(f"First renew{first_emoji} ({first_status})")
            if allow_first_renew and checkpoint_schedule["first_renew"] is not None and checkpoint_schedule["first_renew"] + 2 == idx and checkpoint_status.get("first_renew") == "extend":
                next_status = checkpoint_status.get("first_renew_next", "")
                if next_status:
                    next_emoji = " 🎉" if next_status == "passed" else ""
                    renew_event.append(f"First renew (next year){next_emoji} ({next_status})")
            second_status = checkpoint_status.get("second_renew", "scheduled")
            allow_second_renew = (
                checkpoint_schedule["second_renew"] is not None
                and checkpoint_schedule["second_renew"] < checkpoint_schedule["tenure_package"]
            )
            second_emoji = " 🎉" if second_status == "passed" else ""
            if allow_second_renew and checkpoint_schedule["second_renew"] is not None and checkpoint_schedule["second_renew"] == idx:
                renew_event.append(f"Second renew{second_emoji} ({second_status})")
            if checkpoint_schedule["tenure_package"] == idx:
                review_event.append("Tenure package submit")
            if checkpoint_schedule["tenure_review_1"] == idx or checkpoint_schedule["tenure_review_2"] == idx:
                tenure_status = checkpoint_status.get("tenure_review", "scheduled")
                tenure_emoji = " 🎉" if tenure_status == "passed" else ""
                review_event.append(f"Tenure review{tenure_emoji} ({tenure_status})")

        progress = snap["counter"]

        bank_delta = 0
        if prev_available is not None:
            if snap["available"] > prev_available:
                bank_delta = 1
            elif snap["available"] < prev_available:
                bank_delta = -1
        prev_available = snap["available"]

        manual_title = assignment_name_for_term(title_assignments, idx)
        effective_title = manual_title
        if not effective_title and tenure_passed and idx >= auto_associate_start_idx:
            effective_title = "Associate Professor"

        base = {
            "key": key,
            "year": year,
            "term": term,
            "term_label": f"{term} {year}",
            "term_count": snap["term_count"],
            "sabbaticals_counter": f"{progress}/12",
            "sabbatical_bank": snap["available"],
            "bank_delta": bank_delta,
            "eligibility_status": snap["eligibility"],
            "review_event": " / ".join(review_event) if review_event else "",
            "renew_event": " / ".join(renew_event) if renew_event else "",
            "title": effective_title,
            "service_roles": assignment_names_for_term(role_assignments, idx),
            "leave_types": " / ".join(leave_types_by_term.get(idx, [])),
            "side_notes": "",
        }

        override = employee.get("timeline_overrides", {}).get(key, {})
        for field in (
            "term_count",
            "sabbaticals_counter",
            "sabbatical_bank",
            "eligibility_status",
            "review_event",
            "renew_event",
            "title",
            "service_roles",
            "side_notes",
        ):
            val = override.get(field, "")
            if val != "":
                if checkpoints_disabled and field in ("review_event", "renew_event"):
                    continue
                if field == "service_roles":
                    base[field] = merge_role_values(val, base[field])
                else:
                    base[field] = val

        rows.append(base)

    return {
        "rows": rows,
        "hire_year": hire_year,
        "hire_term": hire_term,
        "tenure_package_default": get_year_term(default_package_idx if default_package_idx is not None else hire_idx + 11),
        "tenure_review_default": [
            get_year_term(tenure_review_1_idx if tenure_review_1_idx is not None else (hire_idx + 12)),
            get_year_term(tenure_review_2_idx if tenure_review_2_idx is not None else (hire_idx + 13)),
        ],
        "current_term": f"{CURRENT_TERM} {CURRENT_YEAR}",
    }


def build_employee_timeline_without_overrides(employee, years_ahead=6):
    employee_copy = copy.deepcopy(employee)
    employee_copy["timeline_overrides"] = {}
    return build_employee_timeline(employee_copy, years_ahead=years_ahead)


def prune_redundant_timeline_overrides(emp):
    overrides = emp.get("timeline_overrides") or {}
    if not isinstance(overrides, dict) or not overrides:
        return False

    try:
        baseline = build_employee_timeline_without_overrides(emp)
    except ValueError:
        return False

    row_map = {row["key"]: row for row in baseline.get("rows", [])}
    field_map = {
        "term_count": "term_count",
        "sabbaticals_counter": "sabbaticals_counter",
        "sabbatical_bank": "sabbatical_bank",
        "eligibility_status": "eligibility_status",
        "review_event": "review_event",
        "renew_event": "renew_event",
        "title": "title",
        "service_roles": "service_roles",
        "leave_types": "leave_types",
        "side_notes": "side_notes",
    }

    cleaned = {}
    for key, override in overrides.items():
        if not isinstance(override, dict):
            continue
        row = row_map.get(key, {})
        new_override = {}
        for f, raw_val in override.items():
            val = "" if raw_val is None else str(raw_val).strip()
            if val == "":
                continue
            baseline_field = field_map.get(f)
            baseline_val = str(row.get(baseline_field, "")).strip() if baseline_field else ""
            if baseline_field and val == baseline_val:
                continue
            new_override[f] = raw_val
        if new_override:
            cleaned[key] = new_override

    if cleaned != overrides:
        emp["timeline_overrides"] = cleaned
        return True
    return False


def clear_legacy_bulk_calculated_overrides(emp):
    overrides = emp.get("timeline_overrides") or {}
    if not isinstance(overrides, dict) or not overrides:
        return False

    calc_fields = (
        "term_count",
        "sabbaticals_counter",
        "sabbatical_bank",
        "eligibility_status",
        "review_event",
        "renew_event",
    )
    calc_row_count = 0
    for override in overrides.values():
        if not isinstance(override, dict):
            continue
        if any((str(override.get(f, "")).strip() != "") for f in calc_fields):
            calc_row_count += 1

    try:
        row_count = len(build_employee_timeline_without_overrides(emp).get("rows", []))
    except ValueError:
        return False

    # Legacy bug pattern: finishing edit used to persist computed values for almost
    # every row. In that case, clear computed overrides so current logic can apply.
    if row_count and calc_row_count >= max(10, int(row_count * 0.7)):
        clear_calculated_timeline_overrides(emp)
        return True
    return False


def validate_event(event):
    s_year = parse_int(event.get("start_year"), "start_year")
    s_term = parse_term(event.get("start_term"), "start_term")
    e_year = parse_int(event.get("end_year"), "end_year")
    e_term = parse_term(event.get("end_term"), "end_term")

    if get_term_index(e_year, e_term) < get_term_index(s_year, s_term):
        raise ValueError("Event end must be after or equal to start")

    e_type = event.get("event_type")
    if e_type not in EVENT_LABELS:
        raise ValueError("Invalid event type")

    total_terms = term_count(s_year, s_term, e_year, e_term)

    if e_type in MEDICAL_MIN_TERMS and total_terms < MEDICAL_MIN_TERMS[e_type]:
        raise ValueError(f"{EVENT_LABELS[e_type]} requires at least {MEDICAL_MIN_TERMS[e_type]} term(s)")

    duration = parse_int(event.get("sabbatical_duration", "1"), "sabbatical_duration", required=False)
    if duration is None:
        duration = 1
    if e_type == EVENT_SABBATICAL and duration not in (1, 2):
        raise ValueError("Sabbatical duration must be 1 or 2 terms")

    return {
        "event_type": e_type,
        "start_year": s_year,
        "start_term": s_term,
        "end_year": e_year,
        "end_term": e_term,
        "sabbatical_duration": duration,
        "status": event.get("status", "approved"),
        "source": event.get("source", "hr"),
    }


def validate_sabbatical_eligibility_for_event(employee, event):
    if event.get("event_type") != EVENT_SABBATICAL:
        return

    timeline = build_employee_timeline(employee)
    start_key = f"{event['start_year']}_{event['start_term']}"
    target_row = next((row for row in timeline.get("rows", []) if row.get("key") == start_key), None)
    if not target_row:
        raise ValueError("Cannot evaluate sabbatical eligibility at the selected start term")

    status = (target_row.get("eligibility_status") or "").strip()
    if status != "Eligible - Not Taken":
        raise ValueError(
            f"Cannot take sabbatical leave at {event['start_term']} {event['start_year']} "
            f"because eligibility is '{status}'"
        )


load_employees_from_db()


@app.route("/")
def home():
    refresh_employees()
    role = request.args.get("role", "")
    employee_id = request.args.get("employee_id", "")
    search = (request.args.get("q") or "").strip()
    edit_mode = request.args.get("edit", "0") == "1"

    selected = get_employee(employee_id) if employee_id else None
    timeline = None
    error = request.args.get("error", "")
    employees = sorted(EMPLOYEES.values(), key=lambda x: x["employee_id"])

    if role == "hr" and search:
        q = search.casefold()
        employees = [
            e
            for e in employees
            if q in (e.get("employee_id") or "").casefold() or q in (e.get("name") or "").casefold()
        ]

    if selected and selected.get("hire_year") and selected.get("hire_term"):
        try:
            timeline = build_employee_timeline(selected)
        except ValueError as exc:
            error = str(exc)

    return render_template(
        "index.html",
        role=role,
        edit_mode=edit_mode,
        employees=employees,
        search=search,
        selected=selected,
        timeline=timeline,
        event_labels=EVENT_LABELS,
        renew_status=RENEW_STATUS,
        tenure_review_status=TENURE_REVIEW_STATUS,
        next_renew_status=NEXT_RENEW_STATUS,
        title_options=TITLE_OPTIONS,
        service_role_options=SERVICE_ROLE_OPTIONS,
        checkpoints_disabled=checkpoints_disabled_for_employee(selected) if selected else False,
        error=error,
        current_year=CURRENT_YEAR,
    )


@app.post("/hr/save_employee")
def hr_save_employee():
    try:
        refresh_employees()
        employee_id = (request.form.get("employee_id") or "").strip()
        if not employee_id:
            raise ValueError("Employee ID is required")

        emp = ensure_employee(employee_id)
        emp["name"] = (request.form.get("name") or "").strip()
        emp["hire_year"] = (request.form.get("hire_year") or "").strip()
        emp["hire_term"] = request.form.get("hire_term", "")
        emp["tenure_package_year"] = (request.form.get("tenure_package_year") or "").strip()
        emp["tenure_package_term"] = request.form.get("tenure_package_term", "")
        title_rows_raw = build_assignment_rows_from_form(request.form, "title")
        role_rows_raw = build_assignment_rows_from_form(request.form, "service_role")

        # Validate assignment rows in a tolerant mode: keep only complete rows.
        title_rows = []
        for row in title_rows_raw:
            try:
                if parse_optional_assignment(row, "title"):
                    title_rows.append(row)
            except ValueError:
                continue

        role_rows = []
        for row in role_rows_raw:
            try:
                if parse_optional_assignment(row, "service_role"):
                    role_rows.append(row)
            except ValueError:
                continue

        emp["title_assignments"] = title_rows
        emp["service_role_assignments"] = role_rows
        # Backward-compatible single-record mirrors.
        emp["title_assignment"] = title_rows[0] if title_rows else {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        }
        emp["service_role_assignment"] = role_rows[0] if role_rows else {
            "name": "",
            "start_year": "",
            "start_term": "",
            "end_year": "",
            "end_term": "",
        }

        # Service role assignments are now managed from profile input; clear stale
        # per-term service role overrides so updated periods apply immediately.
        cleaned_overrides = {}
        for key, override in (emp.get("timeline_overrides") or {}).items():
            if not isinstance(override, dict):
                continue
            new_override = dict(override)
            new_override["service_roles"] = ""
            # Keep the row only if other override fields still contain data.
            if any((str(v).strip() != "") for k, v in new_override.items() if k != "service_roles"):
                cleaned_overrides[key] = new_override
        emp["timeline_overrides"] = cleaned_overrides
        clear_calculated_timeline_overrides(emp)

        if not checkpoints_disabled_for_employee(emp):
            for key in ("first_renew", "second_renew"):
                status_val = request.form.get(f"checkpoint_{key}", "scheduled")
                if status_val not in RENEW_STATUS:
                    status_val = "scheduled"
                emp["checkpoint_status"][key] = status_val

            tenure_review_val = request.form.get("checkpoint_tenure_review", "scheduled")
            if tenure_review_val not in TENURE_REVIEW_STATUS:
                tenure_review_val = "scheduled"
            emp["checkpoint_status"]["tenure_review"] = tenure_review_val

            first_next = request.form.get("checkpoint_first_renew_next", "")
            if first_next not in NEXT_RENEW_STATUS:
                first_next = ""
            emp["checkpoint_status"]["first_renew_next"] = first_next
            # Keep legacy field empty; second renew extension follow-up is no longer used.
            emp["checkpoint_status"]["second_renew_next"] = ""

        # validate basic timeline inputs when provided
        if emp["hire_year"] and emp["hire_term"]:
            parse_int(emp["hire_year"], "hire_year")
            parse_term(emp["hire_term"], "hire_term")

        if emp["tenure_package_year"] and emp["tenure_package_term"]:
            parse_int(emp["tenure_package_year"], "tenure_package_year")
            parse_term(emp["tenure_package_term"], "tenure_package_term")

        # Non-fatal normalization for existing mixed-quality records.
        emp["title_assignments"] = [
            row for row in emp.get("title_assignments", [])
            if parse_assignment_list([row], "title")
        ]
        emp["service_role_assignments"] = [
            row for row in emp.get("service_role_assignments", [])
            if parse_assignment_list([row], "service_role")
        ]

        save_employees_to_db()
        return redirect(url_for("home", role="hr", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=request.form.get("employee_id", ""), error=str(exc)))


@app.post("/hr/add_event")
def hr_add_event():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    try:
        if not employee_id:
            raise ValueError("Employee ID is required")
        emp = get_employee(employee_id)
        if not emp:
            raise ValueError("Employee not found")
        event = validate_event(
            {
                "event_type": request.form.get("event_type"),
                "start_year": request.form.get("start_year"),
                "start_term": request.form.get("start_term"),
                "end_year": request.form.get("end_year"),
                "end_term": request.form.get("end_term"),
                "sabbatical_duration": request.form.get("sabbatical_duration", "1"),
                "status": "approved",
                "source": "hr",
            }
        )
        validate_sabbatical_eligibility_for_event(emp, event)
        append_event_atomic(employee_id, event)
        refresh_employees()
        emp = get_employee(employee_id)
        if emp:
            clear_calculated_timeline_overrides(emp)
            clear_leave_type_overrides(emp)
            save_employees_to_db()
        return redirect(url_for("home", role="hr", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=employee_id, error=str(exc)))


@app.post("/hr/delete_employee")
def hr_delete_employee():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    if not employee_id:
        return redirect(url_for("home", role="hr", error="Employee ID is required"))
    if employee_id not in EMPLOYEES:
        return redirect(url_for("home", role="hr", error="Employee not found"))
    del EMPLOYEES[employee_id]
    save_employees_to_db()
    return redirect(url_for("home", role="hr"))


@app.post("/employee/request_leave")
def employee_request_leave():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    try:
        emp = get_employee(employee_id)
        if not emp:
            raise ValueError("Employee not found")

        event = validate_event(
            {
                "event_type": request.form.get("event_type"),
                "start_year": request.form.get("start_year"),
                "start_term": request.form.get("start_term"),
                "end_year": request.form.get("end_year"),
                "end_term": request.form.get("end_term"),
                "sabbatical_duration": request.form.get("sabbatical_duration", "1"),
                "status": "pending",
                "source": "employee",
            }
        )
        validate_sabbatical_eligibility_for_event(emp, event)
        append_event_atomic(employee_id, event)
        refresh_employees()
        emp = get_employee(employee_id)
        if emp:
            clear_calculated_timeline_overrides(emp)
            clear_leave_type_overrides(emp)
            save_employees_to_db()
        return redirect(url_for("home", role="employee", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="employee", employee_id=employee_id, error=str(exc)))


@app.get("/timeline/export_csv")
def export_timeline_csv():
    refresh_employees()
    employee_id = (request.args.get("employee_id") or "").strip()
    emp = get_employee(employee_id)
    if not emp:
        return redirect(url_for("home", role="hr", error="Employee not found"))

    try:
        timeline = build_employee_timeline(emp)
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=employee_id, error=str(exc)))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Term",
            "Term Count",
            "Sabbaticals Counter",
            "Sabbatical Bank",
            "Bank Delta",
            "Eligibility Status",
            "Review Event",
            "Renew Event",
            "Title",
            "Service Roles",
            "Leaves",
            "Side Notes",
        ]
    )
    for row in timeline["rows"]:
        writer.writerow(
            [
                row.get("term_label", ""),
                row.get("term_count", ""),
                row.get("sabbaticals_counter", ""),
                row.get("sabbatical_bank", ""),
                row.get("bank_delta", ""),
                row.get("eligibility_status", ""),
                row.get("review_event", ""),
                row.get("renew_event", ""),
                row.get("title", ""),
                row.get("service_roles", ""),
                row.get("leave_types", ""),
                row.get("side_notes", ""),
            ]
        )

    filename = f"timeline_{employee_id}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/hr/save_overrides")
def hr_save_overrides():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    emp = ensure_employee(employee_id)
    checkpoints_disabled = checkpoints_disabled_for_employee(emp)
    baseline_timeline = build_employee_timeline_without_overrides(emp)
    baseline_map = {row["key"]: row for row in baseline_timeline.get("rows", [])}

    keys = request.form.getlist("override_key")
    overrides = {}

    field_map = {
        "term_count": "term_count",
        "sabbaticals_counter": "sabbaticals_counter",
        "sabbatical_bank": "sabbatical_bank",
        "eligibility_status": "eligibility_status",
        "review_event": "review_event",
        "renew_event": "renew_event",
        "title": "title",
        "service_roles": "service_roles",
        "side_notes": "side_notes",
    }

    for key in keys:
        row = baseline_map.get(key, {})
        candidate = {
            "term_count": (request.form.get(f"term_count_{key}") or "").strip(),
            "sabbaticals_counter": (request.form.get(f"counter_{key}") or "").strip(),
            "sabbatical_bank": (request.form.get(f"bank_{key}") or "").strip(),
            "eligibility_status": (request.form.get(f"eligibility_{key}") or "").strip(),
            "review_event": (request.form.get(f"review_{key}") or "").strip(),
            "renew_event": (request.form.get(f"renew_{key}") or "").strip(),
            "title": (request.form.get(f"title_{key}") or "").strip(),
            "service_roles": (request.form.get(f"roles_{key}") or "").strip(),
            "side_notes": (request.form.get(f"notes_{key}") or "").strip(),
        }
        if checkpoints_disabled:
            candidate["review_event"] = ""
            candidate["renew_event"] = ""
        row_override = {}
        for field, value in candidate.items():
            baseline_val = str(row.get(field_map[field], "")).strip()
            if value != "" and value != baseline_val:
                row_override[field] = value
        if row_override:
            overrides[key] = row_override

    emp["timeline_overrides"] = overrides
    clear_leave_type_overrides(emp)
    save_employees_to_db()
    return redirect(url_for("home", role="hr", employee_id=employee_id, edit="0"))


@app.post("/hr/approve_event")
def hr_approve_event():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    try:
        event_idx = parse_int(request.form.get("event_idx"), "event_idx")
        emp = get_employee(employee_id)
        if not emp or event_idx is None or event_idx < 0 or event_idx >= len(emp["events"]):
            return redirect(url_for("home", role="hr", employee_id=employee_id, error="Invalid event selection"))

        event = emp["events"][event_idx]
        validate_sabbatical_eligibility_for_event(emp, event)
        emp["events"][event_idx]["status"] = "approved"
        clear_calculated_timeline_overrides(emp)
        clear_leave_type_overrides(emp)
        save_employees_to_db()
        return redirect(url_for("home", role="hr", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=employee_id, error=str(exc)))


@app.post("/hr/delete_event")
def hr_delete_event():
    refresh_employees()
    employee_id = (request.form.get("employee_id") or "").strip()
    event_idx = parse_int(request.form.get("event_idx"), "event_idx")
    emp = get_employee(employee_id)
    if not emp or event_idx is None or event_idx < 0 or event_idx >= len(emp["events"]):
        return redirect(url_for("home", role="hr", employee_id=employee_id, error="Invalid event selection"))

    del emp["events"][event_idx]
    clear_calculated_timeline_overrides(emp)
    clear_leave_type_overrides(emp)
    save_employees_to_db()
    return redirect(url_for("home", role="hr", employee_id=employee_id))


if __name__ == "__main__":
    app.run(debug=True)
