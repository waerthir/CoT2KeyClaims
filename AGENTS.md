# Repository Guidelines

## Project Structure & Module Organization
`raw2problems.py` is the only executable pipeline today; it reads each work-unit folder in `layer_input/<file_id>/` and writes normalized packages to `layer_problem/<file_id>/<file_id>.json`.
`config.py` holds stage settings, path conventions, JSON encoding, and target-work-unit overrides.
`layer_CoT/` and `layer_key_claims/` are reserved for later stages described in `spec/code spec/`. `materials/` contains reference notes and sample data; do not treat it as runtime input.

## Build, Test, and Development Commands
`python raw2problems.py` runs the raw-to-problem stage for all work units under `layer_input/`.
`python -m py_compile raw2problems.py config.py` performs a quick syntax smoke test before commit.
`python -m json.tool layer_problem/biology/biology.json` validates and pretty-prints generated output during review.
No package manifest is checked in, so keep dependencies in the standard library unless the change explicitly adds project tooling.

## Coding Style & Naming Conventions
Use 4-space indentation, type hints, dataclasses, and `pathlib.Path`, matching `raw2problems.py`.
Keep modules and functions in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`.
Preserve UTF-8 JSON output with `ensure_ascii=False` and 2-space indentation. Prefer config-driven paths over hardcoded subject names.

## Testing Guidelines
There is no committed automated test suite yet. Validate changes by running the pipeline against the sample `biology` and `geography` inputs and checking generated JSON shape, `problem_id` stability, and image paths such as `test/biology_question_00001.png`.
If you add reusable logic, add focused tests in a new `tests/` directory instead of expanding manual checks.

## Commit & Pull Request Guidelines
Local history uses short, direct messages such as `Initial commit`, `Delete ...`, and `update 2 layer spec`. Follow that pattern with a one-line imperative summary and keep unrelated data, spec, and code changes separate.
Pull requests should state which layer or work unit changed, reference the relevant file in `spec/`, and include a small before/after JSON example when output schema changes. Do not hand-edit generated files in `layer_problem/`; regenerate them from source inputs.
