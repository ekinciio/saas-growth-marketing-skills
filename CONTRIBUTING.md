# Contributing to SaaS Growth Marketing Skills

Thank you for your interest in contributing! This project welcomes contributions from the community. Whether you're fixing a bug, adding a new skill, or improving documentation, your help is appreciated.

## How to Contribute

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/saas-growth-marketing-skills.git
cd saas-growth-marketing-skills
```

### 2. Create a Branch

```bash
git checkout -b feat/your-feature-name
```

Use the branch naming convention:
- `feat/` - New features or skills
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring

### 3. Make Your Changes

Follow the guidelines below for the type of change you're making.

### 4. Test Your Changes

```bash
# Verify Python scripts compile without errors
python3 -m py_compile skills/your-skill/scripts/your_script.py

# Run the script standalone to verify it works
python3 skills/your-skill/scripts/your_script.py
```

### 5. Commit and Push

```bash
git add .
git commit -m "feat: add new skill for email marketing optimization"
git push origin feat/your-feature-name
```

### 6. Open a Pull Request

Open a PR against the `main` branch with a clear description of your changes.

---

## Adding a New Skill

Every skill must follow this structure:

```
skills/your-skill-name/
  SKILL.md           # Required - skill definition
  references/        # Optional - reference documents
    your-ref.md
  scripts/           # Required - at least one Python script
    your_script.py
```

### SKILL.md Requirements

- Must include YAML frontmatter with `name` and `description`
- Description must explain what the skill does and when to trigger it
- Must define at least one command
- Must include a **Report Output** section defining the `.md` report file each command generates
- Maximum 500 lines (use reference files for additional content)

```yaml
---
name: your-skill-name
description: >
  Clear description of what the skill does. Include trigger keywords
  so the skill activates when users mention relevant topics.
---
```

### Python Script Requirements

- **Python 3.8+ compatible** - No match/case (3.10+), no walrus operator issues
- **Type hints** on all function parameters and return types
- **Docstrings** on all public functions
- **Standalone execution** - Must include `if __name__ == "__main__":` with demo data
- **Dict return type** - All main functions must return JSON-serializable dicts
- **Error handling** - Use try/except with meaningful error messages
- **No extra dependencies** beyond what's in `requirements.txt` (requests, beautifulsoup4, lxml)

Example structure:

```python
"""One-line description of what this script does."""

from typing import Dict, List, Optional


def analyze(data: Dict) -> Dict:
    """Analyze the provided data and return results.

    Args:
        data: Input data dictionary with required fields.

    Returns:
        Dictionary containing analysis results.
    """
    results = {}
    # Your logic here
    return results


def format_report(results: Dict) -> str:
    """Format results into a human-readable report.

    Args:
        results: Analysis results dictionary.

    Returns:
        Formatted report string.
    """
    report = []
    # Format logic here
    return "\n".join(report)


if __name__ == "__main__":
    # Demo with example data
    sample_data = {"key": "value"}
    results = analyze(sample_data)
    print(format_report(results))
```

### Reference File Guidelines

- Markdown format
- Focused on a single topic
- Include practical examples where possible
- Keep each file under 300 lines

---

## Code Style

- **Python**: Follow PEP 8 conventions
- **Markdown**: Use ATX-style headers (`#`, `##`, `###`)
- **Dashes**: Use regular dashes (`-`), never em dashes
- **Language**: All content must be in English
- **Line endings**: LF (Unix style)
- **Encoding**: UTF-8

---

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add email marketing optimization skill
fix: correct ASO score calculation for short titles
docs: update README with new skill descriptions
refactor: simplify citability scoring algorithm
test: add demo data for funnel analyzer
chore: update requirements.txt dependencies
```

---

## What Makes a Good Contribution

All contributions must be relevant to **SaaS growth, marketing, or business optimization**. Specifically:

- **New skills** that help SaaS teams grow (acquisition, activation, retention, revenue, referral)
- **Script improvements** that make existing skills more accurate or useful
- **Reference content** that adds domain knowledge for growth marketers
- **Bug fixes** for existing scripts
- **Documentation improvements** that help users get started faster

### Not in Scope

- Skills unrelated to SaaS or growth marketing
- Features requiring paid API keys or proprietary services
- Machine learning models or heavy dependencies
- Monitoring or alerting services (these are on-demand audit tools)

---

## Reporting Issues

When reporting an issue, please include:

1. **Skill name** - Which skill is affected
2. **Command used** - The exact command you ran
3. **Expected behavior** - What you expected to happen
4. **Actual behavior** - What actually happened
5. **Environment** - Python version, OS, Claude Code version

Use the issue template on GitHub when available.

---

## Questions?

Open a GitHub issue with the `question` label, or reach out to the maintainer.

Thank you for helping make SaaS Growth Marketing Skills better for everyone!
