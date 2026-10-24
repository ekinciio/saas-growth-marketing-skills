#!/usr/bin/env python3
"""Onboarding facts, rubric arithmetic, test sizing and trial-model math.

The model judges the first-run experience against references/rubric.md and
quotes evidence. This script only does the deterministic parts:

    flow        validate a flow ledger (captured steps, or quiz answers),
                derive counts up to the first value moment, say which rubric
                dimensions apply and which facts are unknown
    score       turn the model's per-dimension rubric scores into the
                composite: drops "na" and "not_measured", renormalizes the
                weights, applies the 60 % measured-weight rule, grade and
                overall confidence
    plan        size an onboarding experiment (two proportions, alpha 0.05
                two-sided, power 0.8, 4-week limit) with growthkit stats
    trial       paying customers per 1,000 visitors for a no-card trial
                versus a card-required trial, from the user's own rates
    benchmarks  the onboarding rows of references/_shared/saas-benchmarks.json

Usage (from the user's project folder):

    python3 onboarding_scorer.py flow growth-reports/.cache/flow.json --json
    python3 onboarding_scorer.py flow --demo --json
    python3 onboarding_scorer.py score growth-reports/.cache/scores.json --json
    python3 onboarding_scorer.py plan --baseline 0.31 --weekly 120 --json
    python3 onboarding_scorer.py trial --no-card-v2t 8% --no-card-t2p 15% \\
        --card-v2t 3% --card-t2p 45% --json
    python3 onboarding_scorer.py benchmarks --metric tour_completion --json

Unknown answers ("not sure", "skip", null or a missing key) stay unknown:
they are never scored, never turned into a recommendation and never
replaced by a default. Exit codes follow growthkit cli: 0 ok, 2 usage or
input error, 5 nothing to analyze.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import OrderedDict
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli, stats  # noqa: E402

TOOL = "onboarding_scorer"
RUBRIC_VERSION = "onboarding-rubric-v2"
BENCHMARKS_PATH = os.path.join(os.path.dirname(_HERE), "references", "_shared", "saas-benchmarks.json")

# ---------------------------------------------------------------------------
# Rubric dimensions. Ids and weights must match references/rubric.md (a test
# checks the table there against this map).
# ---------------------------------------------------------------------------

DIMENSIONS: "OrderedDict[str, int]" = OrderedDict([
    ("value_path", 25),
    ("setup_friction", 15),
    ("first_screen", 15),
    ("guidance", 15),
    ("personalization", 10),
    ("reengagement", 10),
    ("team_activation", 5),
    ("trial_fit", 5),
])
SCALE_MAX = 10.0
MIN_MEASURED_SHARE = 0.6          # report-contract.md section 4: composite only at >= 60 %
GRADE_BANDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))
CONFIDENCE_LEVELS = ("high", "medium", "low")
STATUSES = ("scored", "na", "not_measured")

# ---------------------------------------------------------------------------
# Product types: one enum shared with references/rubric.md and
# references/onboarding-patterns.md (a test checks both tables).
# value_horizon is a logical property of the product, not a benchmark:
#   first_session     value can appear in the first session without outside data
#   after_connection  value needs the user's data, code, store or an integration
#   after_team        full value needs other people (solo value can come first)
# ---------------------------------------------------------------------------

PRODUCT_TYPES: "OrderedDict[str, Dict[str, Optional[str]]]" = OrderedDict([
    ("visual", {"label": "Visual and design tools (design, whiteboards, video, diagrams)",
                "value_horizon": "first_session"}),
    ("content", {"label": "Content and creation tools (docs, writing, forms, site builders)",
                 "value_horizon": "first_session"}),
    ("data", {"label": "Data and analytics (BI, product analytics, monitoring)",
              "value_horizon": "after_connection"}),
    ("developer", {"label": "Developer tools and APIs (SDKs, infrastructure, CI)",
                   "value_horizon": "after_connection"}),
    ("collaboration", {"label": "Collaboration and project management (team workspaces, tasks)",
                       "value_horizon": "after_team"}),
    ("communication", {"label": "Communication (chat, meetings, shared inbox, support desk)",
                       "value_horizon": "after_team"}),
    ("business_ops", {"label": "Business operations (CRM, HR, finance, scheduling, ERP)",
                      "value_horizon": "after_connection"}),
    ("ecommerce", {"label": "E-commerce and store builders", "value_horizon": "after_connection"}),
    ("other", {"label": "None of the above (describe the product; pattern fit is judged from it)",
               "value_horizon": None}),
])

HORIZON_NOTES = {
    "first_session": "Value can be shown in the first session without outside data.",
    "after_connection": "Real value needs the user's data, code, store or an integration; aim for a "
                        "first value proxy in session one (sample data, a test event, a preview) and "
                        "real value once the connection lands.",
    "after_team": "Full value needs other people; aim for solo value in session one and team value "
                  "after the first invite is accepted.",
    None: "No horizon for 'other'; judge it from the product description.",
}

_TYPE_ALIASES = {
    "visual": "visual", "design": "visual", "visual design tool": "visual", "visual/design tool": "visual",
    "visual design": "visual", "whiteboard": "visual", "video": "visual", "diagram": "visual",
    "content": "content", "content creative tool": "content", "content/creative tool": "content",
    "creative": "content", "writing": "content", "docs": "content", "forms": "content",
    "data": "data", "analytics": "data", "data analytics": "data", "data/analytics platform": "data",
    "data analytics platform": "data", "bi": "data", "monitoring": "data",
    "developer": "developer", "dev": "developer", "developer tool": "developer", "developer tool api": "developer",
    "developer tool/api": "developer", "api": "developer", "devtools": "developer", "dev tools": "developer",
    "collaboration": "collaboration", "collaboration tool": "collaboration",
    "collaboration productivity tool": "collaboration", "collaboration/productivity tool": "collaboration",
    "project management": "collaboration", "productivity": "collaboration",
    "communication": "communication", "communication tool": "communication", "chat": "communication",
    "messaging": "communication", "support": "communication",
    "business ops": "business_ops", "business_ops": "business_ops", "business operations": "business_ops",
    "business operations crm erp etc": "business_ops", "business operations (crm, erp, etc.)": "business_ops",
    "crm": "business_ops", "erp": "business_ops", "hr": "business_ops", "finance": "business_ops",
    "ecommerce": "ecommerce", "e-commerce": "ecommerce", "e commerce": "ecommerce",
    "e-commerce platform": "ecommerce", "ecommerce platform": "ecommerce", "store builder": "ecommerce",
    "other": "other",
}


def normalize_product_type(value: Any) -> Optional[str]:
    """Map a key or a human label to the enum. None for unknown answers.

    Raises cli.CoercionError for a value that is not in the enum, so an
    unrecognized type is an input error (exit 2) instead of a silent default.
    """
    text = cli.to_text(value, "product_type")
    if text is None:
        return None
    raw = " ".join(text.strip().lower().split())
    for candidate in (raw, re.sub(r"[^a-z0-9/()., -]+", " ", raw).strip(),
                      " ".join(re.sub(r"[^a-z0-9]+", " ", raw).split())):
        if candidate in PRODUCT_TYPES:
            return candidate
        if candidate in _TYPE_ALIASES:
            return _TYPE_ALIASES[candidate]
    raise cli.CoercionError(
        "unknown product type %r; use one of: %s" % (text, ", ".join(PRODUCT_TYPES)),
        "product_type", value,
    )


# ---------------------------------------------------------------------------
# Flow ledger schema
# ---------------------------------------------------------------------------

STEP_KINDS = (
    "welcome", "survey", "profile", "setup", "import", "integration", "install", "verification",
    "invite", "template_picker", "tour", "checklist", "empty_state", "content", "paywall",
    "upgrade_prompt", "value", "other",
)
# Kinds that are work the user does for the product before getting value.
CHORE_KINDS = ("profile", "import", "integration", "install", "verification", "invite", "paywall",
               "upgrade_prompt")
FIRST_SCREEN_STATES = ("blank", "empty_state_cta", "template_gallery", "sample_data", "ai_generated",
                       "value_shown")
TRIAL_MODELS = ("free_trial", "freemium", "reverse_trial", "demo_only", "paid_only", "none")
SOURCES = ("screenshots", "recording", "browser_walk", "interview", "quiz", "data_export", "mixed")


def _enum(choices: Tuple[str, ...], value: Any, field: Optional[str] = None) -> Optional[str]:
    text = cli.to_text(value, field)
    if text is None:
        return None
    key = "_".join(text.strip().lower().replace("-", " ").split())
    if key not in choices:
        raise cli.CoercionError("expected one of %s, got %r" % (", ".join(choices), text), field, value)
    return key


def _count(value: Any, field: Optional[str] = None) -> Optional[int]:
    return cli.to_int(value, field, minimum=0)


def _amount(value: Any, field: Optional[str] = None) -> Optional[float]:
    return cli.to_number(value, field, minimum=0)


def _evidence(value: Any, field: Optional[str] = None) -> Optional[List[str]]:
    if cli.is_missing(value):
        return None
    if isinstance(value, (list, tuple)):
        items = [cli.to_text(item, field) for item in value]
        return [item for item in items if item] or None
    text = cli.to_text(value, field)
    return [text] if text else None


TOP_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("product", cli.to_text),
    ("product_type", lambda v, field=None: normalize_product_type(v)),
    ("source", partial(_enum, SOURCES)),
    ("captured_on", cli.to_text),
    ("activation_event", cli.to_text),
    ("value_moment", cli.to_text),
    ("multiplayer", cli.to_bool),
    ("first_screen", partial(_enum, FIRST_SCREEN_STATES)),
    ("time_to_value_minutes", _amount),
    ("notes", cli.to_text),
])
TRIAL_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("model", partial(_enum, TRIAL_MODELS)),
    ("length_days", _count),
    ("card_required", cli.to_bool),
])
STARTER_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("templates", cli.to_bool),
    ("sample_data", cli.to_bool),
    ("ai_generated", cli.to_bool),
    ("educational_empty_states", cli.to_bool),
])
GUIDANCE_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("in_app_guidance", cli.to_bool),
    ("checklist_items", _count),
    ("tour_steps", _count),
    ("tour_user_launched", cli.to_bool),
    ("contextual_tooltips", cli.to_bool),
])
MESSAGES_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("welcome_email", cli.to_bool),
    ("behavior_triggered", cli.to_bool),
    ("in_app_nudges", cli.to_bool),
])
SUMMARY_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("steps_before_value", _count),
    ("required_inputs_before_value", _count),
    ("progress_shown", cli.to_bool),
    ("skip_available", cli.to_bool),
])
STEP_SCHEMA: Dict[str, Callable[..., Any]] = OrderedDict([
    ("name", cli.to_text),
    ("kind", partial(_enum, STEP_KINDS)),
    ("required_inputs", _count),
    ("optional_inputs", _count),
    ("choices", _count),
    ("can_skip", cli.to_bool),
    ("shows_progress", cli.to_bool),
    ("delivers_value", cli.to_bool),
    ("personalizes_next", cli.to_bool),
    ("seconds", _amount),
    ("evidence", _evidence),
    ("notes", cli.to_text),
])
NESTED = OrderedDict([
    ("trial", TRIAL_SCHEMA),
    ("starter_content", STARTER_SCHEMA),
    ("guidance", GUIDANCE_SCHEMA),
    ("messages", MESSAGES_SCHEMA),
    ("summary", SUMMARY_SCHEMA),
])

# The 1.x quiz keys (11 questions). Each maps to (section, field).
LEGACY_KEYS = OrderedDict([
    ("total_steps", ("summary", "steps_before_value")),
    ("required_fields", ("summary", "required_inputs_before_value")),
    ("has_progress_indicator", ("summary", "progress_shown")),
    ("has_skip_option", ("summary", "skip_available")),
    ("has_template_gallery", ("starter_content", "templates")),
    ("has_empty_state_education", ("starter_content", "educational_empty_states")),
    ("time_to_first_value_minutes", (None, "time_to_value_minutes")),
    ("requires_credit_card_upfront", ("trial", "card_required")),
    ("has_welcome_email_sequence", ("messages", "welcome_email")),
    ("has_in_app_guidance", ("guidance", "in_app_guidance")),
])

DEMO_FLOW: Dict[str, Any] = {
    "product": "Demo Boards (fictional)",
    "product_type": "collaboration",
    "source": "screenshots",
    "activation_event": "Created a board with 3 or more cards and invited 1 teammate within 7 days",
    "value_moment": "Sees their own first board with real tasks",
    "multiplayer": True,
    "trial": {"model": "free_trial", "length_days": 14, "card_required": False},
    "first_screen": "blank",
    "starter_content": {"templates": False, "sample_data": False, "ai_generated": False,
                        "educational_empty_states": False},
    "guidance": {"in_app_guidance": True, "checklist_items": None, "tour_steps": 7,
                 "tour_user_launched": False, "contextual_tooltips": False},
    "messages": {"welcome_email": True, "behavior_triggered": "not sure", "in_app_nudges": False},
    "steps": [
        {"name": "Verify email", "kind": "verification", "required_inputs": 0, "can_skip": False,
         "delivers_value": False, "seconds": 60, "evidence": ["E1"]},
        {"name": "Role and team size survey", "kind": "survey", "required_inputs": 3, "choices": 3,
         "can_skip": False, "shows_progress": True, "personalizes_next": False, "delivers_value": False,
         "seconds": 45, "evidence": ["E2"]},
        {"name": "Name your workspace", "kind": "setup", "required_inputs": 1, "can_skip": False,
         "shows_progress": True, "delivers_value": False, "seconds": 20, "evidence": ["E3"]},
        {"name": "Invite teammates", "kind": "invite", "required_inputs": 0, "optional_inputs": 5,
         "can_skip": True, "shows_progress": True, "delivers_value": False, "seconds": 30,
         "evidence": ["E4"]},
        {"name": "Product tour (7 tooltips) over an empty board", "kind": "tour", "can_skip": True,
         "delivers_value": False, "seconds": 90, "evidence": ["E5"]},
        {"name": "Create the first board from scratch", "kind": "value", "required_inputs": 1,
         "delivers_value": True, "seconds": 240, "evidence": ["E6"]},
    ],
}


def _coerce_section(name: str, payload: Any, schema: Dict[str, Callable[..., Any]],
                    errors: List[str]) -> Dict[str, Any]:
    if payload is None:
        return {key: None for key in schema}
    if not isinstance(payload, dict):
        errors.append("%s: expected an object with %s" % (name, ", ".join(schema)))
        return {key: None for key in schema}
    clean, problems, unknown = cli.coerce_record(payload, schema)
    errors.extend("%s.%s" % (name, item) for item in problems)
    if unknown:
        errors.append("%s: unknown key(s) %s; valid keys: %s" % (
            name, ", ".join(sorted(unknown)), ", ".join(schema)))
    return clean


def normalize_flow(payload: Any) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Validate and coerce a flow ledger. Returns (flow, errors, notes).

    Every field is optional and None means unknown. Errors are input errors
    (exit 2): a value of the wrong type, a negative number, an unknown key or
    an unknown product type.
    """
    if not isinstance(payload, dict):
        raise cli.UsageError("Expected a JSON object (the flow ledger), got %s." % type(payload).__name__)
    errors: List[str] = []
    notes: List[str] = []
    payload = dict(payload)

    # Fold the 1.x quiz keys into their sections, refusing conflicts.
    for legacy, (section, field) in LEGACY_KEYS.items():
        if legacy not in payload:
            continue
        value = payload.pop(legacy)
        if section is None:
            if field in payload and not cli.is_missing(payload[field]):
                errors.append("%s and %s are both set; keep one" % (legacy, field))
                continue
            payload[field] = value
            continue
        target = payload.get(section)
        if target is None:
            target = {}
        if not isinstance(target, dict):
            errors.append("%s: expected an object" % section)
            continue
        target = dict(target)
        if field in target and not cli.is_missing(target[field]):
            errors.append("%s and %s.%s are both set; keep one" % (legacy, section, field))
            continue
        target[field] = value
        payload[section] = target
        notes.append("Read the 1.x quiz key %s as %s.%s." % (legacy, section, field))

    known_top = list(TOP_SCHEMA) + list(NESTED) + ["steps"]
    unknown = [key for key in payload if key not in known_top]
    if unknown:
        errors.append("unknown key(s) %s; valid keys: %s (1.x quiz keys %s are also read)" % (
            ", ".join(sorted(unknown)), ", ".join(known_top), ", ".join(LEGACY_KEYS)))
    flow: Dict[str, Any] = {}
    for key, coercer in TOP_SCHEMA.items():
        try:
            flow[key] = coercer(payload.get(key), field=key)
        except cli.CoercionError as exc:
            flow[key] = None
            errors.append(str(exc))
    for name, schema in NESTED.items():
        flow[name] = _coerce_section(name, payload.get(name), schema, errors)

    steps_raw = payload.get("steps")
    steps: List[Dict[str, Any]] = []
    if steps_raw is not None and not cli.is_missing(steps_raw):
        if not isinstance(steps_raw, list):
            errors.append("steps: expected a list of step objects")
        else:
            for index, item in enumerate(steps_raw, 1):
                if not isinstance(item, dict):
                    errors.append("steps[%d]: expected an object" % index)
                    continue
                clean, problems, unknown_keys = cli.coerce_record(item, STEP_SCHEMA)
                errors.extend("steps[%d].%s" % (index, problem) for problem in problems)
                if unknown_keys:
                    errors.append("steps[%d]: unknown key(s) %s; valid keys: %s" % (
                        index, ", ".join(sorted(unknown_keys)), ", ".join(STEP_SCHEMA)))
                if not clean.get("name"):
                    clean["name"] = "Step %d" % index
                clean["index"] = index
                steps.append(clean)
    flow["steps"] = steps
    return flow, errors, notes


def _sum_known(values: List[Optional[float]]) -> Dict[str, Any]:
    known = [v for v in values if v is not None]
    return {
        "known_sum": (sum(known) if known else None),
        "complete": bool(values) and len(known) == len(values),
        "unknown_steps": len(values) - len(known),
    }


def _tri_any(values: List[Optional[bool]]) -> Optional[bool]:
    """True if any is True, False if all are False, None otherwise."""
    if any(v is True for v in values):
        return True
    if values and all(v is False for v in values):
        return False
    return None


def derive(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Counts up to the first value moment, from the steps or the summary."""
    steps = flow["steps"]
    summary = flow["summary"]
    derived: Dict[str, Any] = {"basis": "steps" if steps else ("summary" if any(
        v is not None for v in summary.values()) else None)}
    if steps:
        value_index = next((s["index"] for s in steps
                            if s.get("delivers_value") is True or s.get("kind") == "value"), None)
        before = [s for s in steps if value_index is None or s["index"] < value_index]
        derived.update({
            "step_count": len(steps),
            "value_reached_in_capture": value_index is not None,
            "value_step": value_index,
            "steps_before_value": len(before),
            "steps_before_value_is_lower_bound": value_index is None,
            "required_inputs_before_value": _sum_known([s.get("required_inputs") for s in before]),
            "optional_inputs_before_value": _sum_known([s.get("optional_inputs") for s in before]),
            "choices_before_value": _sum_known([s.get("choices") for s in before]),
            "seconds_before_value": _sum_known([s.get("seconds") for s in before]),
            "seconds_to_value_including_value_step": (
                _sum_known([s.get("seconds") for s in steps if s["index"] <= value_index])
                if value_index is not None else None),
            "skippable_steps_before_value": sum(1 for s in before if s.get("can_skip") is True),
            "unskippable_steps_before_value": sum(1 for s in before if s.get("can_skip") is False),
            "skip_unknown_steps_before_value": sum(1 for s in before if s.get("can_skip") is None),
            "progress_shown_before_value": _tri_any([s.get("shows_progress") for s in before]),
            "chores_before_value": [
                {"step": s["index"], "name": s["name"], "kind": s["kind"]}
                for s in before if s.get("kind") in CHORE_KINDS],
            "questions_that_do_not_personalize": [
                {"step": s["index"], "name": s["name"]}
                for s in steps if s.get("kind") == "survey" and s.get("personalizes_next") is False],
            "questions_personalization_unknown": [
                {"step": s["index"], "name": s["name"]}
                for s in steps if s.get("kind") == "survey" and s.get("personalizes_next") is None],
            "kinds_in_order": [s.get("kind") or "unknown" for s in steps],
            "invite_steps": [s["index"] for s in steps if s.get("kind") == "invite"],
        })
        if any(v is not None for v in summary.values()):
            derived["summary_ignored"] = True
    elif derived["basis"] == "summary":
        derived.update({
            "steps_before_value": summary["steps_before_value"],
            "required_inputs_before_value": {
                "known_sum": summary["required_inputs_before_value"],
                "complete": summary["required_inputs_before_value"] is not None,
                "unknown_steps": None},
            "progress_shown_before_value": summary["progress_shown"],
            "skip_available_before_value": summary["skip_available"],
        })
    minutes = flow.get("time_to_value_minutes")
    if minutes is None and steps and derived.get("value_step") is not None:
        total = derived["seconds_to_value_including_value_step"]
        if total and total["complete"]:
            minutes = round(total["known_sum"] / 60.0, 2)
            derived["time_to_value_basis"] = "sum of step seconds up to the value step"
    elif minutes is not None:
        derived["time_to_value_basis"] = "time_to_value_minutes as given"
    derived["time_to_value_minutes"] = minutes
    return derived


def applicability(flow: Dict[str, Any], derived: Dict[str, Any]) -> Dict[str, Any]:
    """Which rubric dimensions apply, and which facts each one has.

    suggested_status is "na" when the facts rule the dimension out,
    "not_measured" when no fact for it is known, else "judge" (the model
    scores it, or marks it na with a reason).
    """
    steps_before = derived.get("steps_before_value")
    progress_and_skip = None if steps_before is None else steps_before >= 3
    trial = flow["trial"]
    guidance = flow["guidance"]
    messages = flow["messages"]
    starter = flow["starter_content"]

    def known(*values: Any) -> List[str]:
        return [name for name, value in values if value is not None]

    has_steps = bool(flow["steps"])
    before_skip_known = (derived.get("skippable_steps_before_value", 0)
                         + derived.get("unskippable_steps_before_value", 0)) if has_steps else 0

    facts = OrderedDict([
        ("value_path", known(("activation_event", flow.get("activation_event")),
                             ("value_moment", flow.get("value_moment")),
                             ("steps_before_value", steps_before),
                             ("time_to_value_minutes", derived.get("time_to_value_minutes")),
                             ("first_screen", flow.get("first_screen")))),
        ("setup_friction", known(("steps_before_value", steps_before),
                                 ("required_inputs_before_value",
                                  (derived.get("required_inputs_before_value") or {}).get("known_sum")),
                                 ("chores_before_value", derived.get("chores_before_value")),
                                 ("progress_shown", derived.get("progress_shown_before_value")),
                                 ("skip", derived.get("skip_available_before_value")
                                  if not has_steps else (True if before_skip_known else None)))),
        ("first_screen", known(("first_screen", flow.get("first_screen")),
                               *[("starter_content.%s" % k, v) for k, v in starter.items()])),
        ("guidance", known(*[("guidance.%s" % k, v) for k, v in guidance.items()])),
        ("personalization", known(("survey_steps", [s["index"] for s in flow["steps"]
                                                    if s.get("kind") == "survey"] if has_steps else None),
                                  ("personalizes_next", [s["index"] for s in flow["steps"]
                                                         if s.get("personalizes_next") is not None] or None))),
        ("reengagement", known(*[("messages.%s" % k, v) for k, v in messages.items()])),
        ("team_activation", known(("multiplayer", flow.get("multiplayer")),
                                  ("invite_steps", derived.get("invite_steps") if has_steps else None))),
        ("trial_fit", known(*[("trial.%s" % k, v) for k, v in trial.items()])),
    ])
    dims: Dict[str, Any] = OrderedDict()
    for dim, weight in DIMENSIONS.items():
        status, reason = ("judge", None) if facts[dim] else (
            "not_measured", "no fact for this dimension was captured")
        if dim == "team_activation" and flow.get("multiplayer") is False:
            status, reason = "na", "single-player product (multiplayer: false)"
        if dim == "trial_fit" and trial.get("model") in ("demo_only", "paid_only", "none"):
            status, reason = "na", "no self-serve trial or free plan (trial.model: %s)" % trial["model"]
        if dim == "personalization" and facts[dim] == ["survey_steps"] and not [
                s for s in flow["steps"] if s.get("kind") == "survey"]:
            reason = "no survey step was captured; judge whether routing questions are needed"
        dims[dim] = {"weight": weight, "suggested_status": status, "reason": reason, "facts": facts[dim]}
    return {
        "progress_and_skip": progress_and_skip,
        "progress_and_skip_rule": "progress and skip criteria apply only with 3 or more steps before value",
        "dimensions": dims,
    }


def _load_benchmarks() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        with open(BENCHMARKS_PATH, encoding="utf-8") as handle:
            return json.load(handle), None
    except (OSError, ValueError) as exc:
        return None, "Benchmark file not readable (%s): %s" % (BENCHMARKS_PATH, exc)


def benchmark_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A compact citation-ready view of one benchmark row."""
    stat = OrderedDict()
    for key in ("p25", "median", "p75", "p90", "mean", "value"):
        if row.get(key) is not None:
            stat[key] = row[key]
    return OrderedDict([
        ("id", row.get("id")), ("metric", row.get("metric")), ("label", row.get("metric_label")),
        ("unit", row.get("unit")), ("period", row.get("period")), ("window", row.get("window")),
        ("segment", row.get("segment")), ("stats", stat), ("thresholds", row.get("thresholds")),
        ("source", row.get("source_name")), ("year", row.get("year")), ("url", row.get("source_url")),
        ("confidence", row.get("confidence")), ("verified", row.get("verified")),
        ("verified_on", row.get("verified_on")), ("note", row.get("value_note")),
    ])


ONBOARDING_METRICS = ("activation_rate", "time_to_value", "tour_completion", "checklist_completion",
                      "month_1_retention", "trial_to_paid", "free_to_paid", "visitor_to_signup")


def flow_benchmarks(flow: Dict[str, Any], data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows that give context to the captured facts (never a grade)."""
    if not data:
        return []
    wanted: List[str] = []
    guidance = flow["guidance"]
    if guidance.get("tour_steps") is not None or guidance.get("tour_user_launched") is not None:
        wanted += ["tour_completion.chameleon2024.all", "tour_completion.chameleon2024.self_launched"]
        if (guidance.get("tour_steps") or 0) >= 5:
            wanted.append("tour_completion.chameleon2024.five_step")
    if guidance.get("checklist_items") is not None:
        wanted.append("checklist_completion.userpilot2025.b2b")
    rows = {row.get("id"): row for row in data.get("rows", [])}
    return [benchmark_row(rows[key]) for key in wanted if key in rows]


def _has_any_fact(flow: Dict[str, Any]) -> bool:
    if flow["steps"]:
        return True
    for key in TOP_SCHEMA:
        if key not in ("product", "notes", "source", "captured_on") and flow.get(key) is not None:
            return True
    return any(v is not None for name in NESTED for v in flow[name].values())


def coverage(flow: Dict[str, Any], derived: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Known versus unknown facts (top level, sections and step fields).

    time_to_value_minutes counts as known when it was derived from the step
    timings.
    """
    derived = derived or {}
    tracked: List[Tuple[str, Any]] = [
        (k, derived.get("time_to_value_minutes") if k == "time_to_value_minutes" else flow.get(k))
        for k in TOP_SCHEMA if k not in ("notes", "captured_on")]
    for name, schema in NESTED.items():
        if name == "summary" and flow["steps"]:
            continue
        tracked += [("%s.%s" % (name, key), flow[name].get(key)) for key in schema]
    for step in flow["steps"]:
        for key in ("kind", "required_inputs", "can_skip", "delivers_value", "seconds"):
            tracked.append(("steps[%d].%s" % (step["index"], key), step.get(key)))
    unknown = [name for name, value in tracked if value is None]
    return {"known": len(tracked) - len(unknown), "total": len(tracked), "unknown": unknown}


def analyze_flow(payload: Any) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """normalize + derive + applicability. Returns (result, errors, notes)."""
    flow, errors, notes = normalize_flow(payload)
    if errors:
        return {"flow": flow}, errors, notes
    derived = derive(flow)
    data, problem = _load_benchmarks()
    if problem:
        notes.append(problem)
    if derived.get("summary_ignored"):
        notes.append("Both steps and summary were given; the counts come from the steps.")
    if flow["steps"] and not derived.get("value_reached_in_capture"):
        notes.append("No captured step delivers value (delivers_value: true or kind 'value'), so the "
                     "counts before value are lower bounds: the flow was not followed to its value moment.")
    ptype = flow.get("product_type")
    result = OrderedDict([
        ("rubric_version", RUBRIC_VERSION),
        ("product", flow.get("product")),
        ("product_type", None if ptype is None else OrderedDict([
            ("key", ptype), ("label", PRODUCT_TYPES[ptype]["label"]),
            ("value_horizon", PRODUCT_TYPES[ptype]["value_horizon"]),
            ("horizon_note", HORIZON_NOTES[PRODUCT_TYPES[ptype]["value_horizon"]])])),
        ("flow", flow),
        ("derived", derived),
        ("applicability", applicability(flow, derived)),
        ("benchmarks", flow_benchmarks(flow, data)),
        ("coverage", coverage(flow, derived)),
    ])
    if ptype is None:
        notes.append("product_type is unknown: pattern fit and the value horizon cannot be checked. "
                     "Valid types: %s." % ", ".join(PRODUCT_TYPES))
    if flow["trial"].get("card_required") is not None:
        notes.append("A card at signup is a trade-off, not a defect: judge it under trial_fit with the "
                     "'trial' command when visitor-to-trial and trial-to-paid rates are known.")
    return result, errors, notes


# ---------------------------------------------------------------------------
# Rubric arithmetic
# ---------------------------------------------------------------------------


def grade_for(value: float) -> str:
    for floor, letter in GRADE_BANDS:
        if value >= floor:
            return letter
    return "F"


def compute_score(payload: Any) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Composite from the model's dimension scores. Returns (result, errors, notes)."""
    if not isinstance(payload, dict):
        raise cli.UsageError("Expected a JSON object with a 'dimensions' list, got %s." % type(payload).__name__)
    errors: List[str] = []
    notes: List[str] = []
    version = payload.get("rubric_version")
    if version not in (None, RUBRIC_VERSION):
        errors.append("rubric_version %r does not match this script (%s); rescore with references/rubric.md"
                      % (version, RUBRIC_VERSION))
    items = payload.get("dimensions")
    if isinstance(items, dict):
        items = [dict(value, id=key) if isinstance(value, dict) else {"id": key, "score": value}
                 for key, value in items.items()]
    if not isinstance(items, list):
        errors.append("'dimensions' must be a list of {id, score | status, confidence, evidence, justification}")
        return {}, errors, notes
    seen: Dict[str, Dict[str, Any]] = OrderedDict()
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append("dimensions[%d]: expected an object" % position)
            continue
        dim = str(item.get("id") or "").strip()
        if dim not in DIMENSIONS:
            errors.append("dimensions[%d]: unknown id %r; valid ids: %s" % (position, dim, ", ".join(DIMENSIONS)))
            continue
        if dim in seen:
            errors.append("dimension %s appears twice" % dim)
            continue
        status_raw = item.get("status")
        status = str(status_raw).strip().lower() if status_raw not in (None, "") else None
        raw_score = item.get("score")
        if isinstance(raw_score, str):
            out_of = re.match(r"^\s*(\d+(?:\.\d+)?)\s*/\s*10\s*$", raw_score)
            if out_of:
                raw_score = out_of.group(1)
        try:
            score = cli.to_number(raw_score, "%s.score" % dim, minimum=0, maximum=SCALE_MAX)
        except cli.CoercionError as exc:
            errors.append(str(exc))
            continue
        if status is None:
            status = "scored" if score is not None else "not_measured"
        if status not in STATUSES:
            errors.append("%s.status must be one of %s, got %r" % (dim, ", ".join(STATUSES), status_raw))
            continue
        confidence = str(item.get("confidence") or "").strip().lower() or None
        evidence = item.get("evidence")
        if isinstance(evidence, str):
            evidence = [evidence]
        evidence = [str(e).strip() for e in (evidence or []) if str(e).strip()]
        if status == "scored":
            if score is None:
                errors.append("%s: status 'scored' needs a score from 0 to %g" % (dim, SCALE_MAX))
                continue
            if confidence not in CONFIDENCE_LEVELS:
                errors.append("%s: confidence must be high, medium or low" % dim)
                continue
            if not evidence:
                errors.append("%s: a scored dimension needs at least one evidence id from the report Evidence table (E1, E2, ...)" % dim)
                continue
        elif score is not None:
            notes.append("%s is %s, so its score %g was ignored." % (dim, status, score))
            score = None
        seen[dim] = OrderedDict([
            ("id", dim), ("status", status), ("score", score), ("max", SCALE_MAX),
            ("weight", DIMENSIONS[dim]),
            ("confidence", confidence if status == "scored" else None),
            ("evidence", evidence), ("justification", item.get("justification")),
        ])
    if errors:
        return {}, errors, notes
    for dim in DIMENSIONS:
        if dim not in seen:
            notes.append("%s was missing from the input and is counted as not_measured." % dim)
            seen[dim] = OrderedDict([("id", dim), ("status", "not_measured"), ("score", None),
                                     ("max", SCALE_MAX), ("weight", DIMENSIONS[dim]), ("confidence", None),
                                     ("evidence", []), ("justification", "missing from input")])
    dims = [seen[dim] for dim in DIMENSIONS]
    applicable = [d for d in dims if d["status"] != "na"]
    scored = [d for d in dims if d["status"] == "scored"]
    applicable_weight = sum(d["weight"] for d in applicable)
    scored_weight = sum(d["weight"] for d in scored)
    measured_share = (scored_weight / float(applicable_weight)) if applicable_weight else 0.0
    for d in dims:
        d["points"] = round(d["score"] / SCALE_MAX * d["weight"], 2) if d["status"] == "scored" else None
    composite = None
    if scored_weight:
        composite = sum(d["score"] / SCALE_MAX * d["weight"] for d in scored) / scored_weight * 100.0
    show = composite is not None and measured_share >= MIN_MEASURED_SHARE - 1e-9
    confidence = None
    if scored_weight:
        share = {level: sum(d["weight"] for d in scored if d["confidence"] == level) / float(scored_weight)
                 for level in CONFIDENCE_LEVELS}
        if share["high"] >= 0.8 - 1e-9:
            confidence = "high"
        elif share["low"] > 0.5:
            confidence = "low"
        else:
            confidence = "medium"
    reason = None
    if composite is None:
        reason = "no dimension was scored"
    elif not show:
        reason = ("only %.0f%% of the applicable weight was measured (at least %.0f%% is needed for a "
                  "composite); show the dimension scores only" % (measured_share * 100, MIN_MEASURED_SHARE * 100))
    value = int(round(composite)) if show else None
    result = OrderedDict([
        ("scoring", OrderedDict([
            ("mode", "rubric"), ("version", RUBRIC_VERSION), ("value", value), ("max", 100),
            ("grade", grade_for(value) if value is not None else None),
            ("confidence", confidence if show else None),
            ("measured_weight", round(measured_share, 4)),
            ("applicable_weight", applicable_weight), ("scored_weight", scored_weight),
            ("composite_unrounded", round(composite, 2) if composite is not None else None),
            ("composite_shown", show), ("reason_no_composite", reason),
        ])),
        ("dimensions", dims),
        ("method", "composite = sum(score / 10 x weight) / sum(weight of scored dimensions) x 100; "
                   "na and not_measured dimensions are dropped and the weights renormalized; the "
                   "composite is shown only when scored weight is at least 60% of applicable weight"),
        ("header_line", ("**Score:** %d/100, grade %s (rubric; confidence %s; %.0f%% of weight measured)"
                         % (value, grade_for(value), confidence, measured_share * 100)) if show else None),
    ])
    return result, errors, notes


# ---------------------------------------------------------------------------
# Experiment sizing and trial models
# ---------------------------------------------------------------------------

WEEKS_PER_MONTH = 4.33   # report-contract.md section 6
MIN_TEST_WEEKS = 2


def _rate(value: Any, field: str, allow_edges: bool = False) -> Optional[float]:
    """'31%', '31', '0.31' and '31/100' -> 0.31."""
    percent = cli.to_percent(value, field, assume_fraction=True, minimum=0, maximum=100)
    if percent is None:
        return None
    if not allow_edges and not 0 < percent < 100:
        raise cli.CoercionError("must be between 0% and 100% (exclusive), got %r" % (value,), field, value)
    return percent / 100.0


def experiment_plan(baseline: Any, weekly: Any = None, monthly: Any = None, mde: Any = 0.2,
                    max_weeks: Any = stats.DEFAULT_MAX_WEEKS, label: Optional[str] = None) -> Dict[str, Any]:
    """Test plan for one bet, from the baseline rate and the traffic that reaches the step."""
    base = _rate(baseline, "baseline")
    if base is None:
        raise cli.UsageError("--baseline is required: the current rate of the primary metric "
                             "(the user's measured rate, or a cited benchmark marked as an assumption).")
    effect = cli.to_percent(mde, "mde", assume_fraction=True, minimum=0)
    if effect is None or effect <= 0:
        raise cli.UsageError("--mde must be a positive relative effect, for example 0.2 or 20%.")
    effect = effect / 100.0
    limit = cli.to_number(max_weeks, "max_weeks", minimum=0)
    if not limit:
        raise cli.UsageError("--max-weeks must be greater than 0.")
    weekly_value = cli.to_number(weekly, "weekly", minimum=0)
    monthly_value = cli.to_number(monthly, "monthly", minimum=0)
    traffic_basis = None
    if weekly_value is not None and monthly_value is not None:
        raise cli.UsageError("Pass --weekly or --monthly, not both.")
    if monthly_value is not None:
        weekly_value = monthly_value / WEEKS_PER_MONTH
        traffic_basis = "monthly %g / %.2f" % (monthly_value, WEEKS_PER_MONTH)
    elif weekly_value is not None:
        traffic_basis = "weekly %g as given" % weekly_value
    if weekly_value is not None and weekly_value <= 0:
        raise cli.UsageError("Weekly traffic must be greater than 0.")
    try:
        n_per_arm = stats.sample_size_per_arm(base, effect)
        target = stats.target_rate(base, effect)
    except ValueError as exc:
        raise cli.UsageError(str(exc))
    weekly_needed = int(math.ceil(n_per_arm * 2 / float(limit)))
    out: Dict[str, Any] = OrderedDict([
        ("label", label), ("baseline", base), ("mde_relative", effect), ("target_rate", target),
        ("alpha", stats.DEFAULT_ALPHA), ("power", stats.DEFAULT_POWER), ("two_sided", True), ("arms", 2),
        ("n_per_arm", n_per_arm), ("total_users", n_per_arm * 2), ("max_weeks", limit),
        ("weekly_needed_for_max_weeks", weekly_needed), ("weekly_traffic", weekly_value),
        ("traffic_basis", traffic_basis),
    ])
    if weekly_value is None:
        out.update({
            "test_plan": "traffic_unknown",
            "verdict": "traffic unknown: an A/B test of this size needs about %d users a week reaching "
                       "this step to finish in %g weeks" % (weekly_needed, limit),
        })
        return out
    plan = stats.plan_test(base, weekly_value, effect, max_weeks=limit)
    out["stats_plan"] = plan
    if plan["feasible"]:
        weeks = max(MIN_TEST_WEEKS, plan["weeks_rounded"])
        out.update({
            "test_plan": "ab_test", "weeks": weeks,
            "verdict": "A/B test: %d users per arm, run %d full weeks, stop only at the planned end"
                       % (n_per_arm, weeks),
        })
    else:
        at_max = plan.get("mde_at_max_weeks")
        out.update({
            "test_plan": "ship_and_measure",
            "detectable_relative_in_max_weeks": at_max["relative"] if at_max else None,
            "verdict": "no A/B test: %s. Ship and compare equal windows of at least 2 full weeks before "
                       "and after; watch launches, campaigns and seasonality" % plan["verdict"],
        })
    return out


def trial_comparison(no_card_v2t: Any, no_card_t2p: Any, card_v2t: Any, card_t2p: Any) -> Dict[str, Any]:
    rates = OrderedDict()
    for field, value in (("no_card_visitor_to_trial", no_card_v2t), ("no_card_trial_to_paid", no_card_t2p),
                         ("card_visitor_to_trial", card_v2t), ("card_trial_to_paid", card_t2p)):
        rate = _rate(value, field, allow_edges=True)
        if rate is None:
            raise cli.UsageError("%s is required. Use the user's own rate; when one side is unknown, "
                                 "pass a cited benchmark and label it an assumption." % field)
        rates[field] = rate
    try:
        result = stats.compare_trial_models(*rates.values())
    except ValueError as exc:
        raise cli.UsageError(str(exc))
    data, _problem = _load_benchmarks()
    context = []
    if data:
        ids = ("trial_to_paid.fps2025.trial_opt_in.organic", "trial_to_paid.fps2025.trial_opt_out.organic",
               "visitor_to_signup.fps2025.trial_opt_in.organic", "visitor_to_signup.fps2025.trial_opt_out.organic")
        rows = {row.get("id"): row for row in data.get("rows", [])}
        context = [benchmark_row(rows[key]) for key in ids if key in rows]
    return OrderedDict([("inputs", rates), ("comparison", result), ("benchmark_context", context)])


def benchmark_rows(metric: Optional[str] = None, motion: Optional[str] = None,
                   include_unverified: bool = False) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    data, problem = _load_benchmarks()
    if not data:
        return [], problem
    rows = []
    for row in data.get("rows", []):
        if row.get("metric") not in ONBOARDING_METRICS:
            continue
        if metric and row.get("metric") != metric:
            continue
        if motion and (row.get("segment") or {}).get("motion") not in (motion, "all"):
            continue
        if not include_unverified and not row.get("verified"):
            continue
        rows.append(benchmark_row(row))
    return rows, None


# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------


def _human_flow(env: Dict[str, Any]) -> str:
    if env.get("status") != "ok":
        return "Errors:\n  " + "\n  ".join(env.get("errors") or [])
    lines = ["Flow facts (%s)" % env.get("rubric_version")]
    ptype = env.get("product_type")
    lines.append("Product type: %s" % (ptype["key"] if ptype else "unknown"))
    derived = env.get("derived") or {}
    for key in ("steps_before_value", "time_to_value_minutes"):
        lines.append("%s: %s" % (key, "unknown" if derived.get(key) is None else derived.get(key)))
    req = derived.get("required_inputs_before_value") or {}
    lines.append("required_inputs_before_value: %s%s" % (
        "unknown" if req.get("known_sum") is None else req.get("known_sum"),
        "" if req.get("complete") else " (incomplete)"))
    for item in derived.get("chores_before_value") or []:
        lines.append("chore before value: step %s %s (%s)" % (item["step"], item["name"], item["kind"]))
    lines.append("Dimensions:")
    for dim, info in env["applicability"]["dimensions"].items():
        lines.append("  %-16s %-13s %s" % (dim, info["suggested_status"], ", ".join(info["facts"]) or "-"))
    cov = env.get("coverage") or {}
    lines.append("Coverage: %s of %s facts known" % (cov.get("known"), cov.get("total")))
    lines += ["Note: " + n for n in env.get("notes") or []]
    return "\n".join(lines)


def _human_score(env: Dict[str, Any]) -> str:
    if env.get("status") != "ok":
        return "Errors:\n  " + "\n  ".join(env.get("errors") or [])
    scoring = env["scoring"]
    lines = []
    if scoring["composite_shown"]:
        lines.append("Score: %s/100, grade %s (confidence %s; %.0f%% of weight measured)" % (
            scoring["value"], scoring["grade"], scoring["confidence"], scoring["measured_weight"] * 100))
    else:
        lines.append("No composite: %s" % scoring["reason_no_composite"])
    for d in env["dimensions"]:
        shown = "%g/10" % d["score"] if d["status"] == "scored" else d["status"]
        lines.append("  %-16s w%-3d %s" % (d["id"], d["weight"], shown))
    lines += ["Note: " + n for n in env.get("notes") or []]
    return "\n".join(lines)


def _human_generic(env: Dict[str, Any]) -> str:
    if env.get("status") != "ok":
        return "Errors:\n  " + "\n  ".join(env.get("errors") or [])
    keep = {k: v for k, v in env.items() if k not in ("tool", "version", "demo")}
    return cli.to_json(keep, compact=False)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="onboarding_scorer.py",
        description="Onboarding flow facts, rubric arithmetic, experiment sizing and trial-model math.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + cli.__version__)
    sub = parser.add_subparsers(dest="command")

    def common(name: str, text: str) -> cli.ArgumentParser:
        command = sub.add_parser(name, help=text, description=text)
        command.add_argument("--json", action="store_true", help="print only JSON to stdout")
        command.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
        return command

    flow = common("flow", "validate a flow ledger and derive the facts the rubric needs")
    flow.add_argument("input", nargs="?", help="flow ledger JSON file, or '-' for stdin")
    flow.add_argument("--demo", action="store_true", help="run on a built-in fictional flow (labelled DEMO)")

    score = common("score", "composite from the model's rubric dimension scores")
    score.add_argument("input", nargs="?", help="scores JSON file, or '-' for stdin")

    plan = common("plan", "size an onboarding experiment (two proportions, 4-week limit)")
    plan.add_argument("--baseline", required=True, help="current rate of the primary metric: 0.31 or 31%%")
    plan.add_argument("--weekly", help="users reaching the step per week")
    plan.add_argument("--monthly", help="users reaching the step per month (divided by 4.33)")
    plan.add_argument("--mde", default="0.2", help="relative effect to detect (default 0.2 = 20%%)")
    plan.add_argument("--max-weeks", default=str(stats.DEFAULT_MAX_WEEKS), help="longest acceptable test (default 4)")
    plan.add_argument("--label", help="the bet this plan is for")

    trial = common("trial", "paying customers per 1,000 visitors: no-card vs card-required trial")
    trial.add_argument("--no-card-v2t", required=True, help="visitor-to-trial rate without a card")
    trial.add_argument("--no-card-t2p", required=True, help="trial-to-paid rate without a card")
    trial.add_argument("--card-v2t", required=True, help="visitor-to-trial rate with a card required")
    trial.add_argument("--card-t2p", required=True, help="trial-to-paid rate with a card required")

    bench = common("benchmarks", "onboarding rows from references/_shared/saas-benchmarks.json")
    bench.add_argument("--metric", choices=ONBOARDING_METRICS)
    bench.add_argument("--motion", help="segment motion, e.g. plg, sales_led, freemium, trial_opt_in")
    bench.add_argument("--include-unverified", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        run = cli.Run(TOOL, json_mode="--json" in (argv if argv is not None else sys.argv[1:]))
        return run.fail(cli.STATUS_USAGE, "Pick a command: flow, score, plan, trial or benchmarks.")
    run = cli.Run(TOOL, args, demo=bool(getattr(args, "demo", False)))
    try:
        if args.command == "flow":
            payload, _source = cli.load_json_input(args.input, expect=dict, demo_data=DEMO_FLOW,
                                                   demo=args.demo)
            result, errors, notes = analyze_flow(payload)
            for note in notes:
                run.note(note)
            if errors:
                for error in errors:
                    run.error(error)
                return run.emit({}, status=cli.STATUS_USAGE, human=_human_flow)
            if not _has_any_fact(result["flow"]):
                return run.fail(cli.STATUS_NOTHING,
                                "The flow ledger holds no facts (every field is empty or unknown), so "
                                "there is nothing to score. Capture the flow (screenshots, a browser walk "
                                "or the quiz) first.")
            return run.emit(result, human=_human_flow)
        if args.command == "score":
            payload, _source = cli.load_json_input(args.input, expect=dict)
            result, errors, notes = compute_score(payload)
            for note in notes:
                run.note(note)
            if errors:
                for error in errors:
                    run.error(error)
                return run.emit({}, status=cli.STATUS_USAGE, human=_human_score)
            return run.emit(result, human=_human_score)
        if args.command == "plan":
            result = experiment_plan(args.baseline, args.weekly, args.monthly, args.mde, args.max_weeks,
                                     args.label)
            return run.emit({"plan": result}, human=_human_generic)
        if args.command == "trial":
            result = trial_comparison(args.no_card_v2t, args.no_card_t2p, args.card_v2t, args.card_t2p)
            run.note("Opt-out (card) trial-to-paid in the benchmark source counts a single paid month as a "
                     "conversion; compare retained revenue, not first payments, before switching models.")
            return run.emit(result, human=_human_generic)
        rows, problem = benchmark_rows(args.metric, args.motion, args.include_unverified)
        if problem:
            return run.fail(cli.STATUS_NOTHING, problem)
        run.note("Cite each row with its source, year and segment; activation and time to value depend on "
                 "the user's own event definition.")
        return run.emit({"rows": rows, "count": len(rows)}, human=_human_generic)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))


if __name__ == "__main__":
    sys.exit(main())
