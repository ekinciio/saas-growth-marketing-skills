"""Schema checks for evals/triggering.jsonl.

Each line is one JSON object:

    {"skill": "<folder under skills/>", "prompt": "<user request>", "should_trigger": true}

Optional keys: "note" (why the row exists) and "expected_skill" (for a
should_trigger=false row, the skill that should handle the prompt instead,
or "none").

shared/standards/skill-authoring.md section 6 asks for at least 10
should-trigger and 10 should-not-trigger prompts per skill; these tests
enforce that for every skill folder, so a new skill cannot merge without its
triggering evals. They only check the file, they do not run a model.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import collections
import json
import os
import unittest

from tests import _paths

EVALS_PATH = os.path.join(_paths.REPO_ROOT, "evals", "triggering.jsonl")
REQUIRED_KEYS = {"skill", "prompt", "should_trigger"}
OPTIONAL_KEYS = {"note", "expected_skill"}
MIN_PER_SIDE = 10
MAX_PROMPT_CHARS = 1000
DASHES = (chr(0x2013), chr(0x2014))


def skill_folders():
    """Skill folders that hold a SKILL.md."""
    if not os.path.isdir(_paths.SKILLS_DIR):
        return []
    return sorted(
        name for name in os.listdir(_paths.SKILLS_DIR)
        if not name.startswith(".")
        and os.path.isfile(os.path.join(_paths.SKILLS_DIR, name, "SKILL.md"))
    )


def load_rows():
    """[(line number, parsed value or None, error text or None)] for each non-blank line."""
    rows = []
    with open(EVALS_PATH, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append((number, json.loads(line), None))
            except ValueError as exc:
                rows.append((number, None, str(exc)))
    return rows


class TriggeringEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skills = skill_folders()
        cls.rows = load_rows() if os.path.isfile(EVALS_PATH) else []
        cls.valid = [
            (number, row) for number, row, error in cls.rows
            if error is None and isinstance(row, dict)
        ]

    def test_file_exists_and_has_rows(self):
        self.assertTrue(os.path.isfile(EVALS_PATH), "evals/triggering.jsonl is missing")
        self.assertGreater(len(self.rows), 0)

    def test_every_line_is_a_json_object(self):
        for number, row, error in self.rows:
            self.assertIsNone(error, "line %d: invalid JSON: %s" % (number, error))
            self.assertIsInstance(row, dict, "line %d: expected a JSON object" % number)

    def test_every_row_matches_the_schema(self):
        for number, row in self.valid:
            where = "line %d" % number
            missing = REQUIRED_KEYS - set(row)
            self.assertFalse(missing, "%s: missing %s" % (where, sorted(missing)))
            unknown = set(row) - REQUIRED_KEYS - OPTIONAL_KEYS
            self.assertFalse(unknown, "%s: unknown keys %s" % (where, sorted(unknown)))
            self.assertIsInstance(row["skill"], str, where)
            self.assertIsInstance(row["should_trigger"], bool, "%s: should_trigger must be true or false" % where)
            prompt = row["prompt"]
            self.assertIsInstance(prompt, str, where)
            self.assertTrue(prompt.strip(), "%s: empty prompt" % where)
            self.assertEqual(prompt, prompt.strip(), "%s: prompt has leading or trailing spaces" % where)
            self.assertLessEqual(len(prompt), MAX_PROMPT_CHARS, where)
            for dash in DASHES:
                self.assertNotIn(dash, prompt, "%s: em or en dash in prompt" % where)
            if "note" in row:
                self.assertIsInstance(row["note"], str, where)
            if "expected_skill" in row:
                self.assertFalse(row["should_trigger"],
                                 "%s: expected_skill only makes sense on a should_trigger=false row" % where)
                expected = row["expected_skill"]
                self.assertTrue(expected == "none" or expected in self.skills,
                                "%s: expected_skill %r is not a skill folder" % (where, expected))

    def test_every_row_names_an_existing_skill(self):
        for number, row in self.valid:
            self.assertIn(row.get("skill"), self.skills,
                          "line %d: skills/%s/SKILL.md does not exist" % (number, row.get("skill")))

    def test_every_skill_has_enough_positive_and_negative_prompts(self):
        counts = collections.Counter(
            (row.get("skill"), row.get("should_trigger")) for _number, row in self.valid
        )
        problems = []
        for skill in self.skills:
            positive, negative = counts[(skill, True)], counts[(skill, False)]
            if positive < MIN_PER_SIDE or negative < MIN_PER_SIDE:
                problems.append("%s: %d should-trigger, %d should-not-trigger" % (skill, positive, negative))
        self.assertFalse(
            problems,
            "each skill needs at least %d of each in evals/triggering.jsonl:\n  %s"
            % (MIN_PER_SIDE, "\n  ".join(problems)),
        )

    def test_no_duplicate_prompt_within_a_skill(self):
        seen = {}
        for number, row in self.valid:
            key = (row.get("skill"), " ".join(str(row.get("prompt", "")).lower().split()))
            self.assertNotIn(key, seen, "line %d repeats line %s for %s" % (number, seen.get(key), key[0]))
            seen[key] = number

    def test_no_prompt_should_trigger_two_skills(self):
        # routing-map.md gives every intent exactly one owner.
        owners = collections.defaultdict(set)
        for _number, row in self.valid:
            if row.get("should_trigger") is True:
                owners[" ".join(str(row.get("prompt", "")).lower().split())].add(row.get("skill"))
        clashes = {prompt: sorted(skills) for prompt, skills in owners.items() if len(skills) > 1}
        self.assertFalse(clashes, "prompts marked should_trigger for more than one skill: %r" % clashes)


if __name__ == "__main__":
    unittest.main()
