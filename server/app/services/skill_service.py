"""Load and select compact analysis playbooks."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


@lru_cache(maxsize=1)
def load_analysis_skills() -> List[Dict[str, Any]]:
    return json.loads((KNOWLEDGE_DIR / "analysis_skills.json").read_text(encoding="utf-8"))


def _contains_term(text: str, term: str) -> bool:
    if any("\u4e00" <= character <= "\u9fff" for character in term):
        return term.lower() in text.lower()
    return bool(re.search(rf"\b{re.escape(term.lower())}\b", text.lower()))


def select_analysis_skills(question: str, limit: int = 2) -> List[Dict[str, Any]]:
    ranked = []
    for skill in load_analysis_skills():
        matched = [term for term in skill.get("triggers", []) if _contains_term(question, term)]
        if matched:
            ranked.append((len(matched), skill, matched))

    if not ranked:
        default = next(skill for skill in load_analysis_skills() if skill["id"] == "aggregation_ranking")
        return [{**default, "matched_terms": []}]

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{**skill, "matched_terms": matched} for _, skill, matched in ranked[:limit]]


def compact_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": skill["id"],
        "name": skill["name"],
        "description": skill["description"],
        "plan_rules": skill.get("plan_rules", []),
        "validation_rules": skill.get("validation_rules", []),
        "output_contract": skill.get("output_contract", []),
    }
