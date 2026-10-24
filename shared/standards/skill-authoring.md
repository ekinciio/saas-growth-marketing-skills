# SKILL.md Authoring Standard

Applies to every `skills/<name>/SKILL.md` in this repo. Agents (`agents/*.md`) follow the
sections marked "agents too". Pair this file with:

- `report-contract.md` - what every report contains and how scores are shown
- `growth-context.md` - the shared company context file every skill reads first
- `routing-map.md` - which skill owns which intent, and the "Not for" lines
- `browser-fallback.md` - what to do when a page is blocked, empty or needs visual judgment

`tools/sync_shared.py` copies `report-contract.md`, `growth-context.md`,
`browser-fallback.md`, `volatile-facts.md` and `shared/benchmarks/saas-benchmarks.json` into
every skill folder as `skills/<name>/references/_shared/`, and the growthkit library into
`skills/<name>/scripts/_growthkit/` for every skill that has a `scripts/` folder, so every
installed skill stays self-contained. Edit the files in `shared/`, never the
`references/_shared/` or `scripts/_growthkit/` copies.

## Contents

1. Frontmatter
2. Body section order
3. Script invocation
4. Exit codes and failure handling
5. Progressive disclosure and references
6. "Not for" lines and descriptions
7. Asking the user (agents too)
8. Banned content
9. Merge checklist
10. Sources

---

## 1. Frontmatter

Fields we use, in this order:

| Field | Rule |
|---|---|
| `name` | Equals the directory name. 1-64 chars, lowercase `a-z`, `0-9` and single hyphens, no leading or trailing hyphen. Must not contain `anthropic` or `claude`. |
| `description` | Third person. Lead with the SaaS use case, then inputs, then one "Not for ... (use X)" sentence. Hard limit 1,024 chars (Agent Skills spec); no XML tags, so no `<` or `>` around words. House target: 500 chars or less. |
| `when_to_use` | Trigger phrases and example requests that do not fit in `description`. Claude Code appends it to `description` in the skill listing. |
| `argument-hint` | The subcommand syntax shown in autocomplete, for example `[audit\|score\|copy-review] <url-or-file>`. |
| `allowed-tools` | Only the skill's own scripts, one Bash rule per script (see section 3). Nothing else. |
| `metadata` | A map of string to string. Required key: `version`, the toolkit release, quoted, equal to `__version__` in `shared/growthkit/__init__.py` (the value reports and sidecars print), for example `"2.0.0"`. Optional: `last_verified` (`"YYYY-MM"`). |

Limits that the docs confirm:

- The combined `description` + `when_to_use` text is truncated at 1,536 characters in the
  skill listing. House target for the combined text: 900 characters or less.
- The whole skill listing has a budget of about 1% of the model's context window. When it
  overflows, Claude Code drops descriptions of the least-used skills first. Users who also
  install other skill packs often have 40 or more skills competing for that budget, so every
  extra word costs triggering accuracy.
- `metadata` values must be strings, so quote versions: `version: "2.0.0"`.

Do not use:

- A top-level `version` key. It is not a documented Claude Code field and Claude Code
  ignores unknown keys without an error. Use `metadata.version`.
- `tools` (agents only), `disable-model-invocation` (our skills must auto-trigger), or
  `context: fork` and `model` (reserved for orchestrator skills, decided per skill).
- Broad grants in `allowed-tools` such as `Bash`, `Bash(python3 *)`, `WebFetch` or `Write`.
  `allowed-tools` is applied even in folders the user has not trusted, so keep it minimal.

Portability: `when_to_use` and `argument-hint` are Claude Code fields. A claude.ai upload,
the Skills API and `package_skill.py` accept only `name`, `description`, `license`,
`compatibility`, `metadata` and `allowed-tools`, and fail with a hard error on any other key.
Any packaging step for those channels must strip the Claude Code-only keys.

YAML must parse. If it does not, Claude Code loads the body with empty metadata and the skill
never auto-triggers. Use a folded scalar (`>`) for long text and quote any value that contains
`: ` or starts with a special character. The opening `---` must be the first line of the file.

Example:

```yaml
---
name: landing-page-cro
description: >
  Audits an existing SaaS landing or pricing page for conversion from a URL or saved
  HTML: value proposition, CTA, proof, objections and form friction, with evidence,
  rewritten copy and traffic-aware test plans. Not for writing a new page
  (saas-landing-builder) or the signup flow itself (web-app-growth-engine).
when_to_use: >
  "why isn't my landing page converting", "CRO audit", "review my pricing page for
  conversion", "A/B test ideas for my hero", "score my homepage".
argument-hint: "[audit|score|copy-review|ab-ideas] <url-or-html-file>"
allowed-tools:
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/cro_auditor.py" *)
metadata:
  version: "2.0.0"
  last_verified: "2026-10"
---
```

## 2. Body section order

After compaction Claude Code keeps only the first 5,000 tokens of an invoked skill, and it
never re-reads the file on later turns. So the rules that must hold every time go first, and
everything is written as a standing instruction ("after every fetch, ...") rather than a
one-time step.

Every SKILL.md body uses these sections, in this order:

1. `# <Skill title>` and one sentence on what it does.
2. `## When to use` - 3-6 bullets of situations, then `Not for:` bullets copied from
   `routing-map.md`, each naming the skill to use instead.
3. `## Output contract` - 5-8 lines: the report path pattern, the JSON sidecar, the scoring
   mode rule ("scores follow `references/_shared/report-contract.md`"), the report language,
   the 5-line chat summary. This is the old "Output Rules (MANDATORY)" block, moved to the top.
4. `## Inputs` - what the skill needs, which `growth-context.md` fields matter most, how to get
   each input (read the context file, infer from the site, or ask), and what is optional.
5. `## Workflow` - numbered steps with the exact commands (section 3). One subsection per
   subcommand only when the subcommands really differ.
6. `## Failure handling` - the exit-code table from section 4 plus any skill-specific cases.
7. `## Judgment` - when the model scores or labels: a pointer to `references/rubric.md` and the
   evidence rule. Keep the rubric itself in the reference file.
8. `## References` - one line per file: "Read `references/x.md` when <condition>."
9. `## Notes` - compliance, privacy, rate limits. Short.

Keep the body under 500 lines (Claude Code and Agent Skills guidance) and aim for under
5,000 tokens so the whole skill survives compaction.

The first line inside `## Workflow` is the directory fallback line from section 3.

## 3. Script invocation

Claude Code replaces `${CLAUDE_SKILL_DIR}` with the directory that contains the skill's
SKILL.md. It does this in two places only: the SKILL.md body and Bash rules in
`allowed-tools`. It works the same for skills installed by `install.sh`
(`~/.claude/skills/<name>`), project skills and plugin skills (where it points at the skill's
own subdirectory, not the plugin root).

Rules:

1. Always call scripts with the quoted, braced variable and `--json`:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/cro_auditor.py" "https://example.com" --json
   ```

   Quote the path: install and checkout paths can contain spaces and brackets (this repo
   lives under `My Drive (...)/[04] Quick Shares/`). Never write `python3 scripts/x.py`; the
   working directory is the user's project, not the skill folder.
2. Treat `${CLAUDE_SKILL_DIR}` as a text substitution, not a shell variable. Always use the
   braced form exactly as shown. Scripts must not read it from the environment; a script finds
   its own files with `Path(__file__).resolve().parent`.
3. Put every command in SKILL.md. Substitution is documented for SKILL.md and `allowed-tools`
   only, so `references/*.md` files must not contain commands that depend on it.
4. Add one `allowed-tools` rule per script that mirrors the command text exactly, quotes
   included: `Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/cro_auditor.py" *)`. Bash rules match
   the command text as written, and a trailing ` *` matches any arguments. The grant lasts for
   the turn that invoked the skill; later turns may prompt, which is expected.
5. Run each script as its own Bash call. No `cd`, no `&&` chains, no pipes, no `> file`
   redirects: compound commands are split and every part must match a rule, and redirects
   count as file writes. Use the script's `--out <path>` option to save output instead.
6. Pass user text that may contain quotes or newlines through a file, not as a shell argument:
   save it with the Write tool (for example under `growth-reports/.cache/`) and pass the path.
   Stdin (`-`) works only through a quoted here-doc (`<<'EOF'`), since pipes are not allowed.
7. Never use `--demo` unless the user asked for a demo. Demo output is labelled DEMO in the
   report.
8. Python floor is 3.9 (`python3`). Runtime dependencies are `requests` and `beautifulsoup4`
   only. If a script prints the install hint, show the user
   `python3 -m pip install --user requests beautifulsoup4` and run it only with their OK.
9. Scripts do deterministic work only: fetching, parsing, counting, math, validation against
   hard limits, file import, aggregation. Judgment (copy quality, clarity, intent, sentiment,
   relevance) is done by the model against a written rubric that cites evidence. Do not add
   keyword lists that pretend to judge.
10. API keys come from environment variables only. Never put a key, or a `$VAR` that should
    hold one, into a WebFetch URL: WebFetch does not expand variables, so the literal text is
    sent or the key ends up in the transcript. Call such APIs with `curl` in Bash, where the
    shell expands `$GOOGLE_API_KEY`, and never echo the key.

### Directory fallback

`${CLAUDE_SKILL_DIR}` is a Claude Code feature. Other hosts that load these skills (Codex,
Cursor and others reached through `install.sh`), and older Claude Code builds, may leave it
unreplaced, and the shell then expands it to an empty string (`python3 "/scripts/x.py"`, file
not found). Every SKILL.md starts its Workflow with this line:

> If `${CLAUDE_SKILL_DIR}` appears literally in the commands below, replace it with the
> directory that contains this SKILL.md.

The model resolves that directory in this order:

1. The base directory the host reports when it loads the skill, if it reports one.
2. The directory of the SKILL.md file the model read.
3. The default install path `~/.claude/skills/<name>`.

Never fall back to a path relative to the user's project.

## 4. Exit codes and failure handling

Every script uses the shared CLI contract (`shared/growthkit/cli.py`): with `--json`, stdout
holds only JSON with a top-level `status`, `errors` and `notes`; logs go to stderr. Branch on
the exit code first, then read `status`, `errors` and `notes`.

| Exit | Meaning | What the model does |
|---|---|---|
| 0 | ok | Use the result. Still read `notes` and any per-item status (one keyword or page can fail inside an ok run). |
| 2 | usage or input error | Read `--help`, fix the arguments, retry once. If an input is missing, get it (section 7). |
| 3 | unreachable or blocked | Blocked (bot protection, challenge page): follow `browser-fallback.md`. Unreachable (404, 410, DNS, TLS, refused connection): check the URL with the user; a browser will not help. Never score the page and never report "0", "allowed" or "missing" for something that was not seen. |
| 4 | partial | Use what succeeded. List what failed under "Not measured" in the report coverage. |
| 5 | nothing to analyze (empty page, JS shell, no reviews, no rows) | Pages: follow `browser-fallback.md`. Data: ask for the data. Produce no score. |
| 1 or traceback | unexpected crash (a bug) | Retry at most once. Then continue with other evidence, mark the affected section "Not measured (tool error)" and quote the last error line in the report notes. |

Rules that hold for every exit code:

- A failure is never turned into a result: no score of 0 for a blocked page, no "all crawlers
  allowed" when robots.txt was unreachable, no "section order optimal" for an empty page.
- Never fall back to demo data and never invent the missing value.
- The coverage note of the report (`report-contract.md`) says what failed and why.

## 5. Progressive disclosure and references

- SKILL.md holds the workflow and the contract. Rubrics, checklists, pattern libraries and
  benchmark tables live in `references/`. Scripts and data that only scripts read live in
  `scripts/`.
- Tie each reference to the step that needs it: "Read `references/rubric.md` before scoring."
  Do not list references only at the end with no trigger.
- Keep references one level deep from SKILL.md. A reference must not send the model to a
  third file. The one exception is the `references/_shared/` standards, which name each
  other; a SKILL.md that needs two of them links both directly, so the model never has to
  follow a chain.
- A reference longer than 100 lines starts with a `## Contents` list.
- Each reference that holds facts that go stale carries a `Last verified: YYYY-MM` line near
  the top. Volatile facts (crawler tokens, store limits, API limits, Core Web Vitals) are
  listed in `volatile-facts.md`; verify any that are older than 6 months with WebSearch before
  stating them.
- Shared standards are read from the synced copy:
  `Read "${CLAUDE_SKILL_DIR}/references/_shared/report-contract.md" before writing the report.`
- Benchmarks come from the shared benchmark file (`references/_shared/saas-benchmarks.json`)
  through the scripts, not from numbers typed into SKILL.md.

## 6. "Not for" lines and descriptions

- `routing-map.md` is the single source for who owns which intent. Copy its "Not for" lines
  into the description (short form) and into `## When to use` (long form). When the map
  changes, update both.
- Description pattern:
  `<Verb>s <object> for SaaS <who>: <capabilities>. <Inputs>. Not for <X> (<skill>) or <Y> (<skill>).`
- Lead with the use case: the listing may be cut short, and the first words decide triggering.
- Avoid bare generic tokens that collide with other packs and with ordinary coding work:
  "help", "what can you do", "audit", "optimize", "report", "compare", "robots.txt",
  "any URL". Qualify them ("SaaS AI-search readiness", "month-over-month MRR report").
- Tune the description against `evals/triggering.jsonl` (10 should-trigger and 10
  should-not-trigger prompts per skill) before merging a description change.

## 7. Asking the user (agents too)

- Read `growth-context.md` first (`growth-context.md` standard). Ask only for what is still
  missing and changes the advice.
- Main thread only: ask at most 3 questions per run, in one batch, with AskUserQuestion when
  available. Offer a "Not sure" option and continue with labelled assumptions when skipped.
- Subagents cannot ask: Claude Code removes AskUserQuestion from every subagent. An agent or a
  skill running inside one returns `MISSING_INPUTS: <field>, <field>` for required inputs it
  cannot read or infer, and never invents URLs or numbers.
- Never ask for passwords, API keys or payment details in chat. Keys go in environment
  variables that the user sets.

## 8. Banned content

- Decorative banners, ASCII art, "Intro" or "First Run" blocks, "Starting..." text and
  "proceed without waiting" boilerplate.
- Time estimates ("~60 seconds", "takes 2 minutes").
- Emojis in SKILL.md, reports and chat summaries.
- Em dashes and en dashes anywhere. Use a regular hyphen.
- Mandatory rules placed at the end of the file.
- Unsourced numbers and invented proof (see the bans in `report-contract.md`).
- Marketing copy about the skill itself.

## 9. Merge checklist

- [ ] `name` equals the directory name; frontmatter parses; `metadata.version` is set, quoted
      and equal to the growthkit `__version__`.
- [ ] Description leads with the SaaS use case, ends with a "Not for" sentence, and the combined
      `description` + `when_to_use` is 900 characters or less.
- [ ] Sections appear in the order of section 2, with the output contract near the top.
- [ ] Every command is `python3 "${CLAUDE_SKILL_DIR}/scripts/<x>.py" ... --json`, has a
      matching `allowed-tools` rule, and the directory fallback line is present.
- [ ] Failure handling covers exit codes 0, 1, 2, 3, 4 and 5.
- [ ] Every reference has a "Read X when Y" line; no reference chains.
- [ ] Reads `growth-context.md` first; asks at most 3 questions; subagent path returns
      `MISSING_INPUTS`.
- [ ] Report follows `report-contract.md`, including the scoring switch.
- [ ] No banners, time estimates, emojis, em dashes or en dashes.
- [ ] `evals/triggering.jsonl` rows for the skill pass after the description change.
- [ ] Body under 500 lines.

## 10. Sources

Verified on 2026-10-24:

- Claude Code skills (frontmatter fields, 1,536-character listing cap, string substitutions
  including `${CLAUDE_SKILL_DIR}` and `${CLAUDE_PROJECT_DIR}`, `allowed-tools` substitution,
  500-line guidance, compaction keeps the first 5,000 tokens, listing budget about 1% of
  context, unknown fields ignored, fields accepted outside Claude Code):
  https://code.claude.com/docs/en/skills
- Bash permission rule matching (command text as written, trailing ` *`, compound commands
  split): https://code.claude.com/docs/en/permissions
- Subagents (AskUserQuestion removed from subagents, `skills` preload injects full content):
  https://code.claude.com/docs/en/sub-agents
- Agent Skills specification (name rules, 1,024-character description, metadata string map,
  file references one level deep): https://agentskills.io/specification
- Skill authoring best practices (reserved words `anthropic` and `claude` in names, no XML
  tags in name or description, third-person descriptions, tables of contents for long
  references, execute versus read): https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
