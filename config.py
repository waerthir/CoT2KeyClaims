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


@dataclass(frozen=True)
class Problems2CotConfig:
    input_root: Path = PROJECT_ROOT / "layer_problem"
    output_root: Path = PROJECT_ROOT / "layer_CoT"
    package_file_suffix: str = ".json"
    fragment_file_suffix: str = ".json"
    stage_name: str = "problem_to_cot"
    problem_list_field: str = "problems"
    problem_id_field: str = "problem_id"
    question_text_field: str = "question_text"
    standard_answer_field: str = "standard_answer"
    images_field: str = "images"
    multi_solution_hint_field: str = "multi_solution_hint"
    source_meta_field: str = "source_meta"
    ingest_status_field: str = "ingest_status"
    method_id_field: str = "method_id"
    cot_field: str = "cot"
    generated_answer_field: str = "generated_answer"
    answer_matches_field: str = "answer_matches_standard"
    duplicate_check_field: str = "is_duplicate_with_existing_complete_method"
    gemini_checked_field: str = "gemini_checked"
    is_complete_field: str = "is_complete_fragment"
    multi_solution_false_values: tuple[str, ...] = (
        "",
        "0",
        "false",
        "no",
        "none",
        "single",
        "one",
    )
    answer_match_strip_whitespace: bool = True
    answer_match_collapse_whitespace: bool = True
    json_encoding: str = "utf-8"
    json_indent: int = 2
    ensure_ascii: bool = False
    target_work_units: tuple[str, ...] = ()


PROBLEMS2COT_CONFIG = Problems2CotConfig()
