from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Raw2ProblemsConfig:
    input_root: Path = PROJECT_ROOT / "layer_input"
    output_root: Path = PROJECT_ROOT / "layer_problem"
    input_file_glob: str = "*.json"
    image_dir_name: str = "test"
    output_file_suffix: str = ".json"
    stage_name: str = "raw_to_problem"
    allow_empty_picture: bool = True
    raw_picture_field: str = "picture"
    raw_question_field: str = "question"
    raw_standard_answer_fields: tuple[str, ...] = ("standard_answer", "answer")
    required_problem_fields: tuple[str, ...] = (
        "problem_id",
        "question_text",
        "standard_answer",
        "images",
        "multi_solution_hint",
    )
    optional_problem_fields: tuple[str, ...] = ("source_meta", "ingest_status")
    problem_id_prefix: str = "prob_"
    problem_id_hex_length: int = 24
    hash_algorithm: str = "sha1"
    path_separator: str = "/"
    source_meta_default: dict = field(default_factory=dict)
    multi_solution_hint_default: None = None
    ingest_status_default: str = "ready"
    json_encoding: str = "utf-8"
    json_indent: int = 2
    ensure_ascii: bool = False
    target_work_units: tuple[str, ...] = ()


RAW2PROBLEMS_CONFIG = Raw2ProblemsConfig()
