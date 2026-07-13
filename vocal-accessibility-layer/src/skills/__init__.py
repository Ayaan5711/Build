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
