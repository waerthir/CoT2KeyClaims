from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from config import PROBLEMS2COT_CONFIG, Problems2CotConfig


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {label} to be an object, got {type(value).__name__}.")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected {label} to be a string, got {type(value).__name__}.")
    return value


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected {label} to be an integer, got {type(value).__name__}.")
    return value


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Expected {label} to be a list, got {type(value).__name__}.")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"Expected {label}[{index}] to be a string, got {type(item).__name__}."
            )
        items.append(item)
    return items


@dataclass(frozen=True)
class WorkUnit:
    file_id: str
    input_dir: Path
    input_file: Path
    output_dir: Path


@dataclass(frozen=True)
class ProblemContext:
    config: Problems2CotConfig
    work_unit: WorkUnit
    record_index: int
    problem: dict[str, Any]
    multi_solution_mode: bool

    @property
    def file_id(self) -> str:
        return self.work_unit.file_id

    @property
    def problem_id(self) -> str:
        field_name = self.config.problem_id_field
        return _require_str(self.problem[field_name], field_name)

    @property
    def question_text(self) -> str:
        field_name = self.config.question_text_field
        return _require_str(self.problem[field_name], field_name)

    @property
    def standard_answer(self) -> str:
        field_name = self.config.standard_answer_field
        return _require_str(self.problem[field_name], field_name)

    @property
    def images(self) -> list[str]:
        field_name = self.config.images_field
        return _require_string_list(self.problem[field_name], field_name)

    @property
    def multi_solution_hint(self) -> Any:
        return self.problem.get(self.config.multi_solution_hint_field)


@dataclass(frozen=True)
class GeneratedCoT:
    cot: str
    generated_answer: str


@dataclass(frozen=True)
class GeminiReviewResult:
    passed: bool
    cot: str | None = None
    generated_answer: str | None = None


@dataclass(frozen=True)
class FragmentSnapshot:
    config: Problems2CotConfig
    path: Path
    payload: dict[str, Any]

    @property
    def problem_id(self) -> str:
        field_name = self.config.problem_id_field
        return _require_str(self.payload[field_name], f"fragment.{field_name}")

    @property
    def method_id(self) -> int:
        field_name = self.config.method_id_field
        return _require_int(self.payload[field_name], f"fragment.{field_name}")


@dataclass
class ProblemFragmentGroup:
    complete_fragments: list[FragmentSnapshot] = field(default_factory=list)
    pending_fragments: list[FragmentSnapshot] = field(default_factory=list)
    cleanup_pending_fragments: list[FragmentSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class WorkUnitScanResult:
    work_unit: WorkUnit
    fragments_by_problem: dict[str, ProblemFragmentGroup]


@dataclass(frozen=True)
class FragmentTask:
    action: str
    work_unit: WorkUnit
    problem_context: ProblemContext | None = None
    fragment_path: Path | None = None


@dataclass(frozen=True)
class TaskPlan:
    cleanup_tasks: list[FragmentTask]
    work_tasks: list[FragmentTask]


@dataclass
class Problems2CotReport:
    work_units_processed: int = 0
    fragments_created: int = 0
    fragments_completed: int = 0
    fragments_cleaned: int = 0


@dataclass(frozen=True)
class WorkUnitRuntimeState:
    work_unit: WorkUnit
    package: dict[str, Any]
    problem_contexts: list[ProblemContext]
    scan_result: WorkUnitScanResult


class CoTGenerationBackend(Protocol):
    def generate(
        self,
        *,
        file_id: str,
        problem_id: str,
        method_id: int,
        question_text: str,
        standard_answer: str,
        images: list[str],
        multi_solution_hint: Any,
    ) -> GeneratedCoT:
        ...


class DuplicateCheckBackend(Protocol):
    def is_duplicate(
        self,
        *,
        candidate_fragment: dict[str, Any],
        existing_complete_fragments: list[dict[str, Any]],
    ) -> bool:
        ...


class GeminiReviewBackend(Protocol):
    def review(self, *, fragment: dict[str, Any]) -> GeminiReviewResult:
        ...


class DisabledCoTGenerationBackend:
    def generate(
        self,
        *,
        file_id: str,
        problem_id: str,
        method_id: int,
        question_text: str,
        standard_answer: str,
        images: list[str],
        multi_solution_hint: Any,
    ) -> GeneratedCoT:
        raise RuntimeError(
            "No CoT generation backend configured. Inject a CoTGenerationBackend before running API work."
        )


class DisabledDuplicateCheckBackend:
    def is_duplicate(
        self,
        *,
        candidate_fragment: dict[str, Any],
        existing_complete_fragments: list[dict[str, Any]],
    ) -> bool:
        raise RuntimeError(
            "No duplicate-check backend configured. Inject a DuplicateCheckBackend before running multi-solution duplicate checks."
        )


class DisabledGeminiReviewBackend:
    def review(self, *, fragment: dict[str, Any]) -> GeminiReviewResult:
        raise RuntimeError(
            "No Gemini review backend configured. Inject a GeminiReviewBackend before running detail review."
        )


class ProblemPackageReader:
    def __init__(self, config: Problems2CotConfig) -> None:
        self.config = config

    def list_work_units(self) -> list[WorkUnit]:
        if self.config.target_work_units:
            work_unit_names = list(self.config.target_work_units)
        else:
            work_unit_names = sorted(
                path.name for path in self.config.input_root.iterdir() if path.is_dir()
            )
        return [self._build_work_unit(name) for name in work_unit_names]

    def read(self, work_unit: WorkUnit) -> dict[str, Any]:
        with work_unit.input_file.open("r", encoding=self.config.json_encoding) as handle:
            payload = json.load(handle)

        package = _require_object(payload, f"problem package {work_unit.input_file}")
        problems = package.get(self.config.problem_list_field)
        if not isinstance(problems, list):
            raise ValueError(
                f"Expected {self.config.problem_list_field!r} in {work_unit.input_file} to be a list."
            )

        for index, problem in enumerate(problems):
            record = _require_object(problem, f"problem record {index} in {work_unit.input_file}")
            self._validate_problem_record(record, work_unit=work_unit, index=index)

        return package

    def build_problem_contexts(
        self,
        work_unit: WorkUnit,
        package: dict[str, Any],
        quota_inspector: "MethodQuotaInspector",
    ) -> list[ProblemContext]:
        contexts: list[ProblemContext] = []
        problems = package[self.config.problem_list_field]
        for index, raw_problem in enumerate(problems):
            problem = _require_object(raw_problem, f"problem record {index} in {work_unit.input_file}")
            contexts.append(
                ProblemContext(
                    config=self.config,
                    work_unit=work_unit,
                    record_index=index,
                    problem=problem,
                    multi_solution_mode=quota_inspector.is_multi_solution_mode(problem),
                )
            )
        return contexts

    def _build_work_unit(self, work_unit_name: str) -> WorkUnit:
        input_dir = self.config.input_root / work_unit_name
        if not input_dir.is_dir():
            raise FileNotFoundError(f"Work unit directory not found: {input_dir}")

        input_file = input_dir / f"{work_unit_name}{self.config.package_file_suffix}"
        if not input_file.is_file():
            raise FileNotFoundError(f"Problem package not found: {input_file}")

        return WorkUnit(
            file_id=work_unit_name,
            input_dir=input_dir,
            input_file=input_file,
            output_dir=self.config.output_root / work_unit_name,
        )

    def _validate_problem_record(self, problem: dict[str, Any], work_unit: WorkUnit, index: int) -> None:
        required_fields = (
            self.config.problem_id_field,
            self.config.question_text_field,
            self.config.standard_answer_field,
            self.config.images_field,
        )
        missing_fields = [field_name for field_name in required_fields if field_name not in problem]
        if missing_fields:
            raise ValueError(
                f"Missing required problem fields in {work_unit.input_file}, record {index}: "
                f"{', '.join(missing_fields)}"
            )

        _require_str(problem[self.config.problem_id_field], self.config.problem_id_field)
        _require_str(problem[self.config.question_text_field], self.config.question_text_field)
        _require_str(problem[self.config.standard_answer_field], self.config.standard_answer_field)
        _require_string_list(problem[self.config.images_field], self.config.images_field)


class MethodQuotaInspector:
    def __init__(self, config: Problems2CotConfig) -> None:
        self.config = config

    def is_multi_solution_mode(self, problem: dict[str, Any]) -> bool:
        hint = problem.get(self.config.multi_solution_hint_field)
        if hint is None:
            return False
        if isinstance(hint, bool):
            return hint
        if isinstance(hint, str):
            normalized = hint.strip().lower()
            return normalized not in self.config.multi_solution_false_values
        if isinstance(hint, (int, float)):
            return hint != 0
        return bool(hint)


class CoTFragmentStore:
    def __init__(self, config: Problems2CotConfig) -> None:
        self.config = config

    def list_fragment_paths(self, output_dir: Path) -> list[Path]:
        if not output_dir.is_dir():
            return []
        suffix = self.config.fragment_file_suffix
        return sorted(path for path in output_dir.glob(f"*{suffix}") if path.is_file())

    def read_fragment(self, path: Path) -> FragmentSnapshot:
        with path.open("r", encoding=self.config.json_encoding) as handle:
            payload = json.load(handle)
        fragment_payload = _require_object(payload, f"fragment {path}")
        if self.config.problem_id_field not in fragment_payload:
            raise ValueError(f"Fragment {path} is missing {self.config.problem_id_field!r}.")
        if self.config.method_id_field not in fragment_payload:
            raise ValueError(f"Fragment {path} is missing {self.config.method_id_field!r}.")
        _require_str(fragment_payload[self.config.problem_id_field], self.config.problem_id_field)
        _require_int(fragment_payload[self.config.method_id_field], self.config.method_id_field)
        return FragmentSnapshot(config=self.config, path=path, payload=fragment_payload)

    def write_fragment(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding=self.config.json_encoding) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=self.config.ensure_ascii,
                indent=self.config.json_indent,
            )
            handle.write("\n")

    def delete_fragment(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def build_fragment_path(self, output_dir: Path, problem_id: str, method_id: int) -> Path:
        file_name = f"{problem_id}_{method_id}{self.config.fragment_file_suffix}"
        return output_dir / file_name

    def next_method_id(self, output_dir: Path, problem_id: str) -> int:
        max_method_id = 0
        for path in self.list_fragment_paths(output_dir):
            fragment = self.read_fragment(path)
            if fragment.problem_id != problem_id:
                continue
            max_method_id = max(max_method_id, fragment.method_id)
        return max_method_id + 1

    def build_initial_fragment_payload(
        self,
        problem_context: ProblemContext,
        method_id: int,
        generated: GeneratedCoT,
    ) -> dict[str, Any]:
        payload = dict(problem_context.problem)
        payload["file_id"] = problem_context.file_id
        payload[self.config.method_id_field] = method_id
        payload[self.config.cot_field] = generated.cot
        payload[self.config.generated_answer_field] = generated.generated_answer
        payload[self.config.answer_matches_field] = None
        payload[self.config.duplicate_check_field] = None
        payload[self.config.gemini_checked_field] = None
        payload[self.config.is_complete_field] = False
        return payload


class CoTFragmentScanner:
    def __init__(self, config: Problems2CotConfig, store: CoTFragmentStore) -> None:
        self.config = config
        self.store = store

    def scan(self, work_unit: WorkUnit) -> WorkUnitScanResult:
        fragments_by_problem: dict[str, ProblemFragmentGroup] = {}
        for path in self.store.list_fragment_paths(work_unit.output_dir):
            fragment = self.store.read_fragment(path)
            group = fragments_by_problem.setdefault(fragment.problem_id, ProblemFragmentGroup())
            classification = self._classify(fragment.payload)
            if classification == "cleanup_pending":
                group.cleanup_pending_fragments.append(fragment)
            elif classification == "complete":
                group.complete_fragments.append(fragment)
            else:
                group.pending_fragments.append(fragment)

        for group in fragments_by_problem.values():
            group.complete_fragments.sort(key=lambda fragment: fragment.method_id)
            group.pending_fragments.sort(key=lambda fragment: fragment.method_id)
            group.cleanup_pending_fragments.sort(key=lambda fragment: fragment.method_id)

        return WorkUnitScanResult(work_unit=work_unit, fragments_by_problem=fragments_by_problem)

    def _classify(self, payload: dict[str, Any]) -> str:
        if payload.get(self.config.answer_matches_field) is False:
            return "cleanup_pending"
        if payload.get(self.config.duplicate_check_field) is True:
            return "cleanup_pending"
        if payload.get(self.config.gemini_checked_field) is False:
            return "cleanup_pending"
        if payload.get(self.config.is_complete_field) is True:
            return "complete"
        return "pending"


class GlobalTaskManager:
    def build_plan(self, states: list[WorkUnitRuntimeState]) -> TaskPlan:
        cleanup_tasks: list[FragmentTask] = []
        work_tasks: list[FragmentTask] = []

        for state in states:
            for fragments in state.scan_result.fragments_by_problem.values():
                for fragment in fragments.cleanup_pending_fragments:
                    cleanup_tasks.append(
                        FragmentTask(
                            action="cleanup_fragment",
                            work_unit=state.work_unit,
                            fragment_path=fragment.path,
                        )
                    )

            for problem_context in state.problem_contexts:
                fragments = state.scan_result.fragments_by_problem.get(
                    problem_context.problem_id, ProblemFragmentGroup()
                )

                for fragment in fragments.pending_fragments:
                    work_tasks.append(
                        FragmentTask(
                            action="resume_fragment",
                            work_unit=state.work_unit,
                            problem_context=problem_context,
                            fragment_path=fragment.path,
                        )
                    )

                if problem_context.multi_solution_mode:
                    if not fragments.pending_fragments:
                        work_tasks.append(
                            FragmentTask(
                                action="create_new_fragment",
                                work_unit=state.work_unit,
                                problem_context=problem_context,
                            )
                        )
                elif not fragments.complete_fragments and not fragments.pending_fragments:
                    work_tasks.append(
                        FragmentTask(
                            action="create_new_fragment",
                            work_unit=state.work_unit,
                            problem_context=problem_context,
                        )
                    )

        cleanup_tasks.sort(key=self._task_sort_key)
        work_tasks.sort(key=self._task_sort_key)
        return TaskPlan(cleanup_tasks=cleanup_tasks, work_tasks=work_tasks)

    def _task_sort_key(self, task: FragmentTask) -> tuple[str, int, str]:
        file_id = task.work_unit.file_id
        if task.problem_context is not None:
            record_index = task.problem_context.record_index
            name = task.problem_context.problem_id
        else:
            record_index = -1
            name = task.fragment_path.name if task.fragment_path is not None else ""
        return (file_id, record_index, name)


class CoTGenerator:
    def __init__(
        self,
        config: Problems2CotConfig,
        store: CoTFragmentStore,
        backend: CoTGenerationBackend,
    ) -> None:
        self.config = config
        self.store = store
        self.backend = backend

    def create(self, problem_context: ProblemContext, method_id: int) -> FragmentSnapshot:
        generated = self.backend.generate(
            file_id=problem_context.file_id,
            problem_id=problem_context.problem_id,
            method_id=method_id,
            question_text=problem_context.question_text,
            standard_answer=problem_context.standard_answer,
            images=problem_context.images,
            multi_solution_hint=problem_context.multi_solution_hint,
        )
        path = self.store.build_fragment_path(
            problem_context.work_unit.output_dir,
            problem_context.problem_id,
            method_id,
        )
        payload = self.store.build_initial_fragment_payload(problem_context, method_id, generated)
        self.store.write_fragment(path, payload)
        return self.store.read_fragment(path)


class AnswerMatcher:
    def __init__(self, config: Problems2CotConfig, store: CoTFragmentStore) -> None:
        self.config = config
        self.store = store

    def process(self, fragment: FragmentSnapshot) -> bool:
        payload = dict(fragment.payload)
        generated_answer = _require_str(
            payload[self.config.generated_answer_field], self.config.generated_answer_field
        )
        standard_answer = _require_str(
            payload[self.config.standard_answer_field], self.config.standard_answer_field
        )
        matches = self._normalize(generated_answer) == self._normalize(standard_answer)
        payload[self.config.answer_matches_field] = matches
        self.store.write_fragment(fragment.path, payload)
        if not matches:
            self.store.delete_fragment(fragment.path)
            return False
        return True

    def _normalize(self, text: str) -> str:
        normalized = text
        if self.config.answer_match_strip_whitespace:
            normalized = normalized.strip()
        if self.config.answer_match_collapse_whitespace:
            normalized = re.sub(r"\s+", " ", normalized)
        return normalized


class DuplicateMethodChecker:
    def __init__(
        self,
        config: Problems2CotConfig,
        store: CoTFragmentStore,
        backend: DuplicateCheckBackend,
    ) -> None:
        self.config = config
        self.store = store
        self.backend = backend

    def process(
        self,
        fragment: FragmentSnapshot,
        *,
        existing_complete_fragments: list[FragmentSnapshot],
        multi_solution_mode: bool,
    ) -> bool:
        payload = dict(fragment.payload)
        if not multi_solution_mode:
            payload[self.config.duplicate_check_field] = False
            self.store.write_fragment(fragment.path, payload)
            return True

        is_duplicate = self.backend.is_duplicate(
            candidate_fragment=payload,
            existing_complete_fragments=[candidate.payload for candidate in existing_complete_fragments],
        )
        payload[self.config.duplicate_check_field] = is_duplicate
        self.store.write_fragment(fragment.path, payload)
        if is_duplicate:
            self.store.delete_fragment(fragment.path)
            return False
        return True


class GeminiDetailChecker:
    def __init__(
        self,
        config: Problems2CotConfig,
        store: CoTFragmentStore,
        backend: GeminiReviewBackend,
    ) -> None:
        self.config = config
        self.store = store
        self.backend = backend

    def process(self, fragment: FragmentSnapshot) -> bool:
        payload = dict(fragment.payload)
        result = self.backend.review(fragment=payload)
        payload[self.config.gemini_checked_field] = result.passed
        if not result.passed:
            self.store.write_fragment(fragment.path, payload)
            self.store.delete_fragment(fragment.path)
            return False

        if result.cot is None:
            raise ValueError("Gemini review passed but did not return cot text.")

        payload[self.config.cot_field] = result.cot
        if result.generated_answer is not None:
            payload[self.config.generated_answer_field] = result.generated_answer
        payload[self.config.is_complete_field] = True
        self.store.write_fragment(fragment.path, payload)
        return True


class FragmentTaskExecutor:
    def __init__(
        self,
        config: Problems2CotConfig,
        store: CoTFragmentStore,
        scanner: CoTFragmentScanner,
        cot_generator: CoTGenerator,
        answer_matcher: AnswerMatcher,
        duplicate_checker: DuplicateMethodChecker,
        gemini_checker: GeminiDetailChecker,
    ) -> None:
        self.config = config
        self.store = store
        self.scanner = scanner
        self.cot_generator = cot_generator
        self.answer_matcher = answer_matcher
        self.duplicate_checker = duplicate_checker
        self.gemini_checker = gemini_checker

    def execute_cleanup_task(self, task: FragmentTask, report: Problems2CotReport) -> None:
        if task.fragment_path is None:
            raise ValueError("cleanup_fragment task requires fragment_path.")
        if task.fragment_path.exists():
            self.store.delete_fragment(task.fragment_path)
            report.fragments_cleaned += 1

    def execute_work_task(self, task: FragmentTask, report: Problems2CotReport) -> None:
        if task.problem_context is None:
            raise ValueError(f"{task.action} task requires problem_context.")

        if task.action == "create_new_fragment":
            self._execute_create_task(task.problem_context, report)
            return
        if task.action == "resume_fragment":
            if task.fragment_path is None or not task.fragment_path.exists():
                return
            self._advance_fragment(task.problem_context, task.fragment_path, report)
            return
        raise ValueError(f"Unsupported task action: {task.action}")

    def _execute_create_task(self, problem_context: ProblemContext, report: Problems2CotReport) -> None:
        method_id = self.store.next_method_id(problem_context.work_unit.output_dir, problem_context.problem_id)
        fragment = self.cot_generator.create(problem_context, method_id)
        report.fragments_created += 1
        self._advance_fragment(problem_context, fragment.path, report)

    def _advance_fragment(
        self,
        problem_context: ProblemContext,
        fragment_path: Path,
        report: Problems2CotReport,
    ) -> None:
        if not fragment_path.exists():
            return

        fragment = self.store.read_fragment(fragment_path)
        payload = fragment.payload

        if payload.get(self.config.answer_matches_field) is False:
            self.execute_cleanup_task(
                FragmentTask(
                    action="cleanup_fragment",
                    work_unit=problem_context.work_unit,
                    fragment_path=fragment_path,
                ),
                report,
            )
            return

        if payload.get(self.config.duplicate_check_field) is True:
            self.execute_cleanup_task(
                FragmentTask(
                    action="cleanup_fragment",
                    work_unit=problem_context.work_unit,
                    fragment_path=fragment_path,
                ),
                report,
            )
            return

        if payload.get(self.config.gemini_checked_field) is False:
            self.execute_cleanup_task(
                FragmentTask(
                    action="cleanup_fragment",
                    work_unit=problem_context.work_unit,
                    fragment_path=fragment_path,
                ),
                report,
            )
            return

        if payload.get(self.config.is_complete_field) is True:
            return

        if payload.get(self.config.answer_matches_field) is None:
            if not self.answer_matcher.process(fragment):
                report.fragments_cleaned += 1
                return
            fragment = self.store.read_fragment(fragment_path)
            payload = fragment.payload

        if payload.get(self.config.duplicate_check_field) is None:
            existing_complete_fragments = self._list_current_complete_fragments(
                problem_context.work_unit,
                problem_context.problem_id,
            )
            existing_complete_fragments = [
                candidate for candidate in existing_complete_fragments if candidate.path != fragment_path
            ]
            if not self.duplicate_checker.process(
                fragment,
                existing_complete_fragments=existing_complete_fragments,
                multi_solution_mode=problem_context.multi_solution_mode,
            ):
                report.fragments_cleaned += 1
                return
            fragment = self.store.read_fragment(fragment_path)
            payload = fragment.payload

        if payload.get(self.config.gemini_checked_field) is None:
            if not self.gemini_checker.process(fragment):
                report.fragments_cleaned += 1
                return
            fragment = self.store.read_fragment(fragment_path)
            payload = fragment.payload

        if payload.get(self.config.is_complete_field) is True:
            report.fragments_completed += 1

    def _list_current_complete_fragments(
        self,
        work_unit: WorkUnit,
        problem_id: str,
    ) -> list[FragmentSnapshot]:
        scan_result = self.scanner.scan(work_unit)
        group = scan_result.fragments_by_problem.get(problem_id)
        if group is None:
            return []
        return list(group.complete_fragments)


class Problems2CotPipeline:
    def __init__(
        self,
        config: Problems2CotConfig,
        *,
        generation_backend: CoTGenerationBackend | None = None,
        duplicate_backend: DuplicateCheckBackend | None = None,
        gemini_backend: GeminiReviewBackend | None = None,
    ) -> None:
        self.config = config
        self.reader = ProblemPackageReader(config)
        self.quota_inspector = MethodQuotaInspector(config)
        self.store = CoTFragmentStore(config)
        self.scanner = CoTFragmentScanner(config, self.store)
        self.task_manager = GlobalTaskManager()
        self.cot_generator = CoTGenerator(
            config,
            self.store,
            generation_backend or DisabledCoTGenerationBackend(),
        )
        self.answer_matcher = AnswerMatcher(config, self.store)
        self.duplicate_checker = DuplicateMethodChecker(
            config,
            self.store,
            duplicate_backend or DisabledDuplicateCheckBackend(),
        )
        self.gemini_checker = GeminiDetailChecker(
            config,
            self.store,
            gemini_backend or DisabledGeminiReviewBackend(),
        )
        self.executor = FragmentTaskExecutor(
            config,
            self.store,
            self.scanner,
            self.cot_generator,
            self.answer_matcher,
            self.duplicate_checker,
            self.gemini_checker,
        )

    def run(self) -> Problems2CotReport:
        report = Problems2CotReport()
        states: list[WorkUnitRuntimeState] = []
        work_units = self.reader.list_work_units()

        for work_unit in work_units:
            package = self.reader.read(work_unit)
            problem_contexts = self.reader.build_problem_contexts(
                work_unit,
                package,
                self.quota_inspector,
            )
            scan_result = self.scanner.scan(work_unit)
            states.append(
                WorkUnitRuntimeState(
                    work_unit=work_unit,
                    package=package,
                    problem_contexts=problem_contexts,
                    scan_result=scan_result,
                )
            )

        plan = self.task_manager.build_plan(states)
        for task in plan.cleanup_tasks:
            self.executor.execute_cleanup_task(task, report)
        for task in plan.work_tasks:
            self.executor.execute_work_task(task, report)

        report.work_units_processed = len(work_units)
        return report


def main() -> None:
    pipeline = Problems2CotPipeline(PROBLEMS2COT_CONFIG)
    report = pipeline.run()
    print(
        "Processed "
        f"{report.work_units_processed} work units; "
        f"created={report.fragments_created}, "
        f"completed={report.fragments_completed}, "
        f"cleaned={report.fragments_cleaned}"
    )


if __name__ == "__main__":
    main()
