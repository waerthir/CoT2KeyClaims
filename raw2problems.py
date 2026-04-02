from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import RAW2PROBLEMS_CONFIG, Raw2ProblemsConfig


@dataclass(frozen=True)
class WorkUnit:
    file_id: str
    input_dir: Path
    input_file: Path
    image_dir: Path
    output_dir: Path
    output_file: Path


class RawJsonReader:
    def __init__(self, config: Raw2ProblemsConfig) -> None:
        self.config = config

    def list_work_units(self) -> list[WorkUnit]:
        if self.config.target_work_units:
            work_unit_names = list(self.config.target_work_units)
        else:
            work_unit_names = sorted(
                path.name for path in self.config.input_root.iterdir() if path.is_dir()
            )

        return [self._build_work_unit(name) for name in work_unit_names]

    def read(self, work_unit: WorkUnit) -> list[dict[str, Any]]:
        with work_unit.input_file.open("r", encoding=self.config.json_encoding) as handle:
            payload = json.load(handle)

        if not isinstance(payload, list):
            raise ValueError(
                f"Expected top-level list in {work_unit.input_file}, got {type(payload).__name__}."
            )

        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Expected record at index {index} in {work_unit.input_file} to be an object."
                )

        return payload

    def _build_work_unit(self, work_unit_name: str) -> WorkUnit:
        input_dir = self.config.input_root / work_unit_name
        if not input_dir.is_dir():
            raise FileNotFoundError(f"Work unit directory not found: {input_dir}")

        input_file = self._resolve_input_file(input_dir)
        image_dir = input_dir / self.config.image_dir_name
        output_dir = self.config.output_root / work_unit_name
        output_file = output_dir / f"{work_unit_name}{self.config.output_file_suffix}"

        return WorkUnit(
            file_id=work_unit_name,
            input_dir=input_dir,
            input_file=input_file,
            image_dir=image_dir,
            output_dir=output_dir,
            output_file=output_file,
        )

    def _resolve_input_file(self, input_dir: Path) -> Path:
        matches = sorted(
            path
            for path in input_dir.glob(self.config.input_file_glob)
            if path.is_file()
        )
        if not matches:
            raise FileNotFoundError(
                f"No input file matching {self.config.input_file_glob!r} found in {input_dir}."
            )
        if len(matches) > 1:
            names = ", ".join(path.name for path in matches)
            raise ValueError(f"Multiple input files found in {input_dir}: {names}")
        return matches[0]


class ProblemIdGenerator:
    def __init__(self, config: Raw2ProblemsConfig) -> None:
        self.config = config

    def generate(self, file_id: str, record_index: int, raw_record: dict[str, Any]) -> str:
        standard_answer = raw_record.get("standard_answer")
        if standard_answer is None:
            standard_answer = raw_record.get("answer")
        digest_input = json.dumps(
            {
                "file_id": file_id,
                "record_index": record_index,
                "picture": raw_record.get(self.config.raw_picture_field),
                "question": raw_record.get(self.config.raw_question_field),
                "standard_answer": standard_answer,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.new(self.config.hash_algorithm, digest_input.encode("utf-8")).hexdigest()
        hex_part = digest[: self.config.problem_id_hex_length].lower()
        return f"{self.config.problem_id_prefix}{hex_part}"


class ImagePathResolver:
    def __init__(self, config: Raw2ProblemsConfig) -> None:
        self.config = config

    def resolve(self, picture_value: Any) -> list[str]:
        picture_names = self._normalize_picture_names(picture_value)
        prefix = self.config.image_dir_name.strip("/\\")
        return [self._join_relative_path(prefix, picture_name) for picture_name in picture_names]

    def _normalize_picture_names(self, picture_value: Any) -> list[str]:
        if picture_value is None:
            if self.config.allow_empty_picture:
                return []
            raise ValueError("Picture entry cannot be null.")

        if isinstance(picture_value, str):
            picture_names = [picture_value]
        elif isinstance(picture_value, list):
            picture_names = picture_value
        else:
            raise ValueError(
                f"Unsupported picture field type: {type(picture_value).__name__}."
            )

        normalized: list[str] = []
        for picture_name in picture_names:
            if not isinstance(picture_name, str):
                raise ValueError(
                    f"Picture entry must be a string, got {type(picture_name).__name__}."
                )
            clean_name = picture_name.strip().replace("\\", self.config.path_separator)
            clean_name = clean_name.lstrip(self.config.path_separator)
            if not clean_name:
                raise ValueError("Picture entry cannot be empty.")
            normalized.append(clean_name)
        return normalized

    def _join_relative_path(self, prefix: str, picture_name: str) -> str:
        return f"{prefix}{self.config.path_separator}{picture_name}"


class ProblemFieldProcessor:
    def __init__(
        self,
        config: Raw2ProblemsConfig,
        id_generator: ProblemIdGenerator,
        image_path_resolver: ImagePathResolver,
    ) -> None:
        self.config = config
        self.id_generator = id_generator
        self.image_path_resolver = image_path_resolver

    def process_records(self, file_id: str, raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        processed_records: list[dict[str, Any]] = []
        for index, raw_record in enumerate(raw_records):
            self._validate_required_raw_fields(raw_record, file_id=file_id, record_index=index)
            processed_records.append(
                self._process_single_record(file_id=file_id, record_index=index, raw_record=raw_record)
            )
        return processed_records

    def _process_single_record(
        self, file_id: str, record_index: int, raw_record: dict[str, Any]
    ) -> dict[str, Any]:
        question_text = self._extract_question(raw_record)
        standard_answer = self._extract_standard_answer(raw_record)
        picture_value = self._extract_picture(raw_record)
        return {
            "problem_id": self.id_generator.generate(file_id, record_index, raw_record),
            "question_text": question_text,
            "standard_answer": standard_answer,
            "images": self.image_path_resolver.resolve(picture_value),
            "source_meta": dict(self.config.source_meta_default),
            "multi_solution_hint": self.config.multi_solution_hint_default,
            "ingest_status": self.config.ingest_status_default,
        }

    def _validate_required_raw_fields(
        self, raw_record: dict[str, Any], file_id: str, record_index: int
    ) -> None:
        missing_fields: list[str] = []
        if self.config.raw_picture_field not in raw_record:
            missing_fields.append(self.config.raw_picture_field)
        if self.config.raw_question_field not in raw_record:
            missing_fields.append(self.config.raw_question_field)
        if not any(field_name in raw_record for field_name in self.config.raw_standard_answer_fields):
            missing_fields.append("/".join(self.config.raw_standard_answer_fields))

        if missing_fields:
            raise ValueError(
                f"Missing required fields in work unit {file_id}, record {record_index}: "
                f"{', '.join(missing_fields)}"
            )

    def _extract_picture(self, raw_record: dict[str, Any]) -> Any:
        return raw_record[self.config.raw_picture_field]

    def _extract_question(self, raw_record: dict[str, Any]) -> str:
        question = raw_record[self.config.raw_question_field]
        if not isinstance(question, str):
            raise ValueError(f"Question field must be a string, got {type(question).__name__}.")
        return question

    def _extract_standard_answer(self, raw_record: dict[str, Any]) -> str:
        for field_name in self.config.raw_standard_answer_fields:
            value = raw_record.get(field_name)
            if isinstance(value, str):
                return value
        raise ValueError(
            "Standard answer field must exist and be a string under one of: "
            f"{', '.join(self.config.raw_standard_answer_fields)}"
        )


class ProblemPackageWriter:
    def __init__(self, config: Raw2ProblemsConfig) -> None:
        self.config = config

    def build_package(
        self, file_id: str, source_file_name: str, processed_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "file_id": file_id,
            "stage": self.config.stage_name,
            "source_file_name": source_file_name,
            "problems": processed_records,
        }

    def write(self, output_file: Path, package: dict[str, Any]) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding=self.config.json_encoding) as handle:
            json.dump(
                package,
                handle,
                ensure_ascii=self.config.ensure_ascii,
                indent=self.config.json_indent,
            )
            handle.write("\n")


class Raw2ProblemsPipeline:
    def __init__(self, config: Raw2ProblemsConfig) -> None:
        self.config = config
        self.reader = RawJsonReader(config)
        self.problem_id_generator = ProblemIdGenerator(config)
        self.image_path_resolver = ImagePathResolver(config)
        self.field_processor = ProblemFieldProcessor(
            config=config,
            id_generator=self.problem_id_generator,
            image_path_resolver=self.image_path_resolver,
        )
        self.writer = ProblemPackageWriter(config)

    def run(self) -> list[Path]:
        written_files: list[Path] = []
        for work_unit in self.reader.list_work_units():
            written_files.append(self.process_work_unit(work_unit))
        return written_files

    def process_work_unit(self, work_unit: WorkUnit) -> Path:
        if not work_unit.image_dir.is_dir():
            raise FileNotFoundError(f"Image directory not found: {work_unit.image_dir}")

        raw_records = self.reader.read(work_unit)
        processed_records = self.field_processor.process_records(work_unit.file_id, raw_records)
        package = self.writer.build_package(
            file_id=work_unit.file_id,
            source_file_name=work_unit.input_file.name,
            processed_records=processed_records,
        )
        self.writer.write(work_unit.output_file, package)
        return work_unit.output_file


def main() -> None:
    pipeline = Raw2ProblemsPipeline(RAW2PROBLEMS_CONFIG)
    written_files = pipeline.run()
    for path in written_files:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
