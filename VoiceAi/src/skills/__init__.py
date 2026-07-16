import importlib
import pkgutil

from src.skills.base import Skill

_registry = {}


def _discover():
    if _registry:
        return _registry
    package = importlib.import_module(__name__)
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{module_name}")
        for attr in vars(module).values():
            if isinstance(attr, type) and issubclass(attr, Skill) and attr is not Skill:
                instance = attr()
                _registry[instance.name] = instance
    return _registry


def get_skills():
    return _discover()


def select_skill(clean_text: str, llm) -> dict:
    """
    Domain-aware routing (FR-20). Returns
    {"skill": name_or_None, "params": {...}, "clarify": question_or_None}.
    """
    import json

    skills = get_skills()
    payload = {"clean_text": clean_text, "available_skills": [s.schema() for s in skills.values()]}
    raw = llm.complete(
        "Route this request to the best-matching skill, or ask a clarifying question if none fit.",
        json.dumps(payload),
        task="select_skill",
    )
    return json.loads(raw)
