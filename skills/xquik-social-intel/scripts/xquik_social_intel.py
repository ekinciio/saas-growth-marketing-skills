"""Analyze Xquik social data exports for SaaS growth signals."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


INTENT_TERMS = (
    "alternative",
    "buy",
    "cancel",
    "looking for",
    "recommend",
    "switch",
    "tool",
    "trial",
)

PAIN_TERMS = (
    "broken",
    "expensive",
    "frustrated",
    "hard",
    "missing",
    "problem",
    "slow",
    "stuck",
)


def _text_from_record(record: dict[str, Any]) -> str:
    for key in ("text", "content", "body", "tweet", "post"):
        value = record.get(key)
        if isinstance(value, str):
            return value
    return json.dumps(record, ensure_ascii=False)


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("data", "items", "results", "tweets", "posts"):
                items = data.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
            return [data]
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"Unsupported input file: {path}")


def score_record(record: dict[str, Any]) -> dict[str, Any]:
    """Score one normalized X record."""
    text = _text_from_record(record)
    lowered = text.lower()
    intent = sum(1 for term in INTENT_TERMS if term in lowered)
    pain = sum(1 for term in PAIN_TERMS if term in lowered)
    score = min(intent, 5) + min(pain, 5)
    return {
        "score": score,
        "intent_matches": intent,
        "pain_matches": pain,
        "text": text[:280],
        "url": record.get("url") or record.get("tweetUrl") or record.get("link") or "",
    }


def analyze(path: str) -> dict[str, Any]:
    """Analyze an Xquik JSON or CSV export."""
    records = _load_records(Path(path))
    scored = sorted((score_record(record) for record in records), key=lambda item: item["score"], reverse=True)
    top_records = scored[:10]
    return {
        "records_analyzed": len(records),
        "top_records": top_records,
        "average_score": round(sum(item["score"] for item in scored) / len(scored), 2) if scored else 0,
    }


def format_report(results: dict[str, Any]) -> str:
    """Format analysis results as a Markdown report."""
    lines = [
        "# Xquik Social Intel Report",
        "",
        f"Records analyzed: {results['records_analyzed']}",
        f"Average opportunity score: {results['average_score']}",
        "",
        "## Top Signals",
        "",
    ]
    for index, record in enumerate(results["top_records"], start=1):
        lines.append(f"{index}. Score {record['score']} - {record['text']}")
        if record["url"]:
            lines.append(f"   Source: {record['url']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Run the analyzer against a JSON or CSV export."""
    if len(sys.argv) != 2:
        print("Usage: python xquik_social_intel.py <xquik-export.json|csv>")
        raise SystemExit(1)
    print(format_report(analyze(sys.argv[1])))


if __name__ == "__main__":
    main()
