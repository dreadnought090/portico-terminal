"""Skill loader — on-demand load skill content for LLM context or dev reference.

NOT auto-injected anywhere. Callers explicitly load skills when needed.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def list_skills() -> list[str]:
    """Return all available skill names (folder names with SKILL.md)."""
    out = []
    for p in sorted(_SKILLS_DIR.iterdir()):
        if p.is_dir() and (p / "SKILL.md").exists():
            out.append(p.name)
    return out


@lru_cache(maxsize=64)
def load_skill(name: str) -> str:
    """Load full SKILL.md content for the given skill name.

    Cached after first read. Raises ValueError if skill not found.
    """
    skill_path = _SKILLS_DIR / name / "SKILL.md"
    if not skill_path.exists():
        raise ValueError(f"skill '{name}' not found in {_SKILLS_DIR}")
    return skill_path.read_text(encoding="utf-8")


def load_skill_excerpt(name: str, max_chars: int = 400) -> str:
    """Load just the first N chars of a skill — useful for compact LLM context.

    Strips frontmatter (--- ... ---) and returns the opening overview.
    """
    full = load_skill(name)
    # Strip YAML frontmatter
    if full.startswith("---"):
        end = full.find("---", 3)
        if end > 0:
            full = full[end + 3:].lstrip()
    return full[:max_chars].rstrip() + ("..." if len(full) > max_chars else "")


def search_skills(query: str) -> list[tuple[str, str]]:
    """Simple text search across skill names + descriptions. Returns
    [(name, description), ...] for matching skills.
    """
    q = query.lower()
    results = []
    for name in list_skills():
        try:
            content = load_skill(name)
        except Exception:
            continue
        # Description often in YAML frontmatter
        desc = ""
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm = content[3:end]
                for line in fm.split("\n"):
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break
        if q in name.lower() or q in desc.lower() or q in content.lower():
            results.append((name, desc))
    return results
