"""Per-skill evaluation spec — the only skill-specific surface of the substrate.

Everything else (transcript parser, check engine, judge prompt, aggregator) is
skill-agnostic and reads what it needs from an EvalSpec. To evaluate a new skill,
author one `evals/skills/<name>/eval_config.py` exporting `SPEC = EvalSpec(...)`.
"""
from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalSpec:
    name: str                       # "should-i-buy"
    command: str                    # "/parallax-should-i-buy" (the registered slash command)
    skill_md_path: Path             # orchestrator file, for the length guard
    required_sections: list[str]    # sections sections_present demands
    section_labels: list[str]       # all labels the skill can emit (section-text boundaries)
    check_ids: list[str]            # check ids to run (generic CHECK_REGISTRY ∪ extra_checks)
    tier2_criteria: list[dict]      # the rubric-judge criteria for this skill
    tasks_path: str                 # JSONL of {id, args, lang, ...}
    orchestrator_max_lines: int = 250
    rollout_prefix: str = ""        # output filename prefix; defaults to name
    # Skill-specific checks authored in this skill's eval_config.py: {id: fn(t, spec)}.
    # These overlay the generic CHECK_REGISTRY — the split (generic vs extra) is the
    # criteria-reuse measurement.
    extra_checks: dict[str, Callable] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        return self.rollout_prefix or self.name


def load_spec(skill: str) -> EvalSpec:
    """Import evals/skills/<skill>/eval_config.py and return its SPEC."""
    evals_root = Path(__file__).resolve().parents[1]
    path = evals_root / "skills" / skill / "eval_config.py"
    if not path.exists():
        raise FileNotFoundError(f"no eval spec for skill {skill!r}: {path}")
    mod_spec = importlib.util.spec_from_file_location(f"eval_config_{skill.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    return module.SPEC
