import csv
import io

from flask import Flask, Response, redirect, render_template, request, url_for

app = Flask(__name__)

CURRENT_YEAR = 2026
CURRENT_TERM = "Winter"
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

TENURE_STATUS = ["scheduled", "passed", "failed"]
NEXT_RENEW_STATUS = ["", "passed", "failed"]
TITLE_OPTIONS = ["", "Assistant Professor", "Associate Professor", "Full Professor"]
SERVICE_ROLE_OPTIONS = [
    "",
    "Fellowship",
    "Faculty Director",
    "Area Chair",
    "Program Director",
    "Committee Chair",
]

# In-memory store for prototype/demo usage.
EMPLOYEES = {
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
        EMPLOYEES[employee_id] = {
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

    if not (name and start_year_raw and start_term_raw and end_year_raw and end_term_raw):
        raise ValueError(f"Incomplete {field_prefix} assignment. Please fill name/start/end year+term.")

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
        parsed_item = parse_optional_assignment(assignment or {}, field_prefix)
        if parsed_item:
            parsed.append(parsed_item)
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
    package_idx = hire_idx + 11
    if package_year_raw and package_term_raw:
        package_idx = get_term_index(parse_int(package_year_raw, "tenure_package_year"), parse_term(package_term_raw, "tenure_package_term"))
        if package_idx < hire_idx:
            package_idx = hire_idx

    tenure_start_idx = package_idx + 1
    checkpoint_schedule = build_checkpoint_schedule(hire_idx, package_idx)
    checkpoint_status = employee.get("checkpoint_status", {})
    tenure_passed = checkpoint_status.get("tenure_review") == "passed"
    title_assignments = parse_assignment_list(employee.get("title_assignments", []), "title")
    if not title_assignments:
        fallback_title = parse_optional_assignment(employee.get("title_assignment", {}), "title")
        if fallback_title:
            title_assignments = [fallback_title]
    role_assignments = parse_assignment_list(employee.get("service_role_assignments", []), "service_role")
    if not role_assignments:
        fallback_role = parse_optional_assignment(employee.get("service_role_assignment", {}), "service_role")
        if fallback_role:
            role_assignments = [fallback_role]

    approved_events = [e for e in employee["events"] if e.get("status") == "approved"]
    sabbatical_starts = set()
    valid_terms = 0
    used = 0

    per_term = {}
    max_idx = max(current_idx, hire_idx + years_ahead * 2)

    for idx in range(hire_idx, max_idx + 1):
        year, term = get_year_term(idx)
        blocked, reason = is_term_blocked(idx, approved_events)
        if not blocked:
            valid_terms += 1

        # Sabbatical "usage" consumes one chance no matter 1 or 2 terms.
        taken_this_term = False
        can_use_sabbatical = tenure_passed and idx >= tenure_start_idx
        for e in approved_events:
            if e["event_type"] != EVENT_SABBATICAL:
                continue
            start_idx = get_term_index(e["start_year"], e["start_term"])
            if start_idx == idx and can_use_sabbatical and start_idx not in sabbatical_starts:
                sabbatical_starts.add(start_idx)
                used += 1
                taken_this_term = True

        earned_total = valid_terms // 12
        available = earned_total - used if tenure_passed else 0
        if tenure_passed:
            # Once bank earns +1, counter should roll over by 12 immediately.
            counter = valid_terms - earned_total * 12
        else:
            # Before tenure is passed, counter can continue beyond 12/12.
            counter = valid_terms
        tenure_active = tenure_passed and idx >= tenure_start_idx

        if taken_this_term:
            eligibility = "Taken"
        elif not tenure_active:
            eligibility = "Pre-tenure" if idx < tenure_start_idx else "Not Eligible"
        elif available >= 1:
            eligibility = "Eligible - Not Taken"
        else:
            eligibility = "Not Eligible"

        per_term[idx] = {
            "year": year,
            "term": term,
            "term_count": idx - hire_idx + 1,
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

    for idx in range(hire_idx, max_idx + 1):
        snap = per_term[idx]
        year = snap["year"]
        term = snap["term"]
        key = f"{year}_{term}"

        renew_event = []
        review_event = []

        first_status = checkpoint_status.get("first_renew", "scheduled")
        first_emoji = " 🎉" if first_status == "passed" else ""
        if checkpoint_schedule["first_renew"] == idx:
            renew_event.append(f"First renew{first_emoji} ({first_status})")
        if checkpoint_schedule["first_renew"] + 2 == idx and checkpoint_status.get("first_renew") == "failed":
            next_status = checkpoint_status.get("first_renew_next", "")
            if next_status:
                next_emoji = " 🎉" if next_status == "passed" else ""
                renew_event.append(f"First renew (next year){next_emoji} ({next_status})")
        second_status = checkpoint_status.get("second_renew", "scheduled")
        second_emoji = " 🎉" if second_status == "passed" else ""
        if checkpoint_schedule["second_renew"] == idx:
            renew_event.append(f"Second renew{second_emoji} ({second_status})")
        if checkpoint_schedule["second_renew"] + 2 == idx and checkpoint_status.get("second_renew") == "failed":
            next_status = checkpoint_status.get("second_renew_next", "")
            if next_status:
                next_emoji = " 🎉" if next_status == "passed" else ""
                renew_event.append(f"Second renew (next year){next_emoji} ({next_status})")
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
            "title": assignment_name_for_term(title_assignments, idx),
            "service_roles": assignment_names_for_term(role_assignments, idx),
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
                if field == "service_roles":
                    base[field] = merge_role_values(val, base[field])
                else:
                    base[field] = val

        rows.append(base)

    return {
        "rows": rows,
        "hire_year": hire_year,
        "hire_term": hire_term,
        "tenure_package_default": get_year_term(hire_idx + 11),
        "tenure_review_default": [get_year_term(hire_idx + 12), get_year_term(hire_idx + 13)],
        "current_term": f"{CURRENT_TERM} {CURRENT_YEAR}",
    }


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


@app.route("/")
def home():
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
        tenure_status=TENURE_STATUS,
        next_renew_status=NEXT_RENEW_STATUS,
        title_options=TITLE_OPTIONS,
        service_role_options=SERVICE_ROLE_OPTIONS,
        error=error,
        current_year=CURRENT_YEAR,
    )


@app.post("/hr/save_employee")
def hr_save_employee():
    try:
        employee_id = (request.form.get("employee_id") or "").strip()
        if not employee_id:
            raise ValueError("Employee ID is required")

        emp = ensure_employee(employee_id)
        emp["name"] = (request.form.get("name") or "").strip()
        emp["hire_year"] = (request.form.get("hire_year") or "").strip()
        emp["hire_term"] = request.form.get("hire_term", "")
        emp["tenure_package_year"] = (request.form.get("tenure_package_year") or "").strip()
        emp["tenure_package_term"] = request.form.get("tenure_package_term", "")
        title_rows = build_assignment_rows_from_form(request.form, "title")
        role_rows = build_assignment_rows_from_form(request.form, "service_role")
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

        for key in ("first_renew", "second_renew", "tenure_review"):
            status_val = request.form.get(f"checkpoint_{key}", "scheduled")
            if status_val not in TENURE_STATUS:
                status_val = "scheduled"
            emp["checkpoint_status"][key] = status_val

        for key in ("first_renew_next", "second_renew_next"):
            status_val = request.form.get(f"checkpoint_{key}", "")
            if status_val not in NEXT_RENEW_STATUS:
                status_val = ""
            emp["checkpoint_status"][key] = status_val

        # validate basic timeline inputs when provided
        if emp["hire_year"] and emp["hire_term"]:
            parse_int(emp["hire_year"], "hire_year")
            parse_term(emp["hire_term"], "hire_term")

        if emp["tenure_package_year"] and emp["tenure_package_term"]:
            parse_int(emp["tenure_package_year"], "tenure_package_year")
            parse_term(emp["tenure_package_term"], "tenure_package_term")

        parse_assignment_list(emp.get("title_assignments", []), "title")
        parse_assignment_list(emp.get("service_role_assignments", []), "service_role")

        return redirect(url_for("home", role="hr", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=request.form.get("employee_id", ""), error=str(exc)))


@app.post("/hr/add_event")
def hr_add_event():
    employee_id = (request.form.get("employee_id") or "").strip()
    try:
        emp = ensure_employee(employee_id)
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
        emp["events"].append(event)
        return redirect(url_for("home", role="hr", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="hr", employee_id=employee_id, error=str(exc)))


@app.post("/hr/delete_employee")
def hr_delete_employee():
    employee_id = (request.form.get("employee_id") or "").strip()
    if not employee_id:
        return redirect(url_for("home", role="hr", error="Employee ID is required"))
    if employee_id not in EMPLOYEES:
        return redirect(url_for("home", role="hr", error="Employee not found"))
    del EMPLOYEES[employee_id]
    return redirect(url_for("home", role="hr"))


@app.post("/employee/request_leave")
def employee_request_leave():
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
        emp["events"].append(event)
        return redirect(url_for("home", role="employee", employee_id=employee_id))
    except ValueError as exc:
        return redirect(url_for("home", role="employee", employee_id=employee_id, error=str(exc)))


@app.get("/timeline/export_csv")
def export_timeline_csv():
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
    employee_id = (request.form.get("employee_id") or "").strip()
    emp = ensure_employee(employee_id)

    keys = request.form.getlist("override_key")
    overrides = emp.get("timeline_overrides", {})

    for key in keys:
        overrides[key] = {
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

    emp["timeline_overrides"] = overrides
    return redirect(url_for("home", role="hr", employee_id=employee_id, edit="0"))


@app.post("/hr/approve_event")
def hr_approve_event():
    employee_id = (request.form.get("employee_id") or "").strip()
    event_idx = parse_int(request.form.get("event_idx"), "event_idx")
    emp = get_employee(employee_id)
    if not emp or event_idx is None or event_idx < 0 or event_idx >= len(emp["events"]):
        return redirect(url_for("home", role="hr", employee_id=employee_id, error="Invalid event selection"))

    emp["events"][event_idx]["status"] = "approved"
    return redirect(url_for("home", role="hr", employee_id=employee_id))


if __name__ == "__main__":
    app.run(debug=True)
