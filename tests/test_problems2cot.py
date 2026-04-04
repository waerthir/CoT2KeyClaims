from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path
from typing import Any

from config import Problems2CotConfig
from problems2cot import (
    AnswerMatcher,
    CoTFragmentScanner,
    CoTFragmentStore,
    CoTGenerator,
    DuplicateMethodChecker,
    FragmentTask,
    FragmentTaskExecutor,
    GeminiDetailChecker,
    GeminiReviewResult,
    GeneratedCoT,
    ProblemPackageReader,
    Problems2CotPipeline,
    Problems2CotReport,
)


class FakeGenerationBackend:
    def __init__(self, generated_answer: str | None = None) -> None:
        self.generated_answer = generated_answer
        self.calls = 0

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
    ):
        self.calls += 1
        answer = self.generated_answer if self.generated_answer is not None else standard_answer
        return GeneratedCoT(cot=f"draft cot for {problem_id}", generated_answer=answer)


class FakeDuplicateBackend:
    def __init__(self, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.calls = 0

    def is_duplicate(
        self,
        *,
        candidate_fragment: dict[str, Any],
        existing_complete_fragments: list[dict[str, Any]],
    ) -> bool:
        self.calls += 1
        return self.duplicate


class FakeGeminiBackend:
    def __init__(self, passed: bool = True) -> None:
        self.passed = passed
        self.calls = 0

    def review(self, *, fragment: dict[str, Any]) -> GeminiReviewResult:
        self.calls += 1
        if not self.passed:
            return GeminiReviewResult(passed=False)
        return GeminiReviewResult(
            passed=True,
            cot=f"refined::{fragment['problem_id']}",
            generated_answer=fragment["generated_answer"],
        )


class Problems2CotTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path.cwd() / "tests" / "_tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self.input_root = self.root / "layer_problem"
        self.output_root = self.root / "layer_CoT"
        self.config = Problems2CotConfig(
            input_root=self.input_root,
            output_root=self.output_root,
            target_work_units=("demo",),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_single_mode_pipeline_completes_fragment_without_duplicate_api(self) -> None:
        self._write_problem_package(
            multi_solution_hint=None,
            standard_answer="标准答案",
        )
        generation_backend = FakeGenerationBackend()
        duplicate_backend = FakeDuplicateBackend()
        gemini_backend = FakeGeminiBackend()

        pipeline = Problems2CotPipeline(
            self.config,
            generation_backend=generation_backend,
            duplicate_backend=duplicate_backend,
            gemini_backend=gemini_backend,
        )
        report = pipeline.run()

        fragment_path = self.output_root / "demo" / "prob_demo_1.json"
        self.assertTrue(fragment_path.exists())
        payload = self._read_json(fragment_path)
        self.assertEqual(payload["cot"], "refined::prob_demo")
        self.assertEqual(payload["generated_answer"], "标准答案")
        self.assertIs(payload["answer_matches_standard"], True)
        self.assertIs(payload["is_duplicate_with_existing_complete_method"], False)
        self.assertIs(payload["gemini_checked"], True)
        self.assertIs(payload["is_complete_fragment"], True)
        self.assertEqual(duplicate_backend.calls, 0)
        self.assertEqual(generation_backend.calls, 1)
        self.assertEqual(gemini_backend.calls, 1)
        self.assertEqual(report.fragments_created, 1)
        self.assertEqual(report.fragments_completed, 1)
        self.assertEqual(report.fragments_cleaned, 0)

    def test_cleanup_pending_is_classified_and_deleted_by_executor(self) -> None:
        self._write_problem_package(
            multi_solution_hint=None,
            standard_answer="标准答案",
        )
        fragment_path = self.output_root / "demo" / "prob_demo_1.json"
        self._write_json(
            fragment_path,
            {
                "file_id": "demo",
                "problem_id": "prob_demo",
                "question_text": "题目文本",
                "standard_answer": "标准答案",
                "images": ["test/example.png"],
                "source_meta": {},
                "multi_solution_hint": None,
                "ingest_status": "ready",
                "method_id": 1,
                "cot": "<cot>",
                "generated_answer": "错误答案",
                "answer_matches_standard": False,
                "is_duplicate_with_existing_complete_method": None,
                "gemini_checked": None,
                "is_complete_fragment": False,
            },
        )

        reader = ProblemPackageReader(self.config)
        store = CoTFragmentStore(self.config)
        scanner = CoTFragmentScanner(self.config, store)
        work_unit = reader.list_work_units()[0]
        scan_result = scanner.scan(work_unit)

        self.assertIn("prob_demo", scan_result.fragments_by_problem)
        group = scan_result.fragments_by_problem["prob_demo"]
        self.assertEqual(len(group.cleanup_pending_fragments), 1)
        self.assertEqual(len(group.pending_fragments), 0)

        executor = FragmentTaskExecutor(
            self.config,
            store,
            scanner,
            CoTGenerator(self.config, store, FakeGenerationBackend()),
            AnswerMatcher(self.config, store),
            DuplicateMethodChecker(self.config, store, FakeDuplicateBackend()),
            GeminiDetailChecker(self.config, store, FakeGeminiBackend()),
        )
        report = Problems2CotReport()
        executor.execute_cleanup_task(
            FragmentTask(
                action="cleanup_fragment",
                work_unit=work_unit,
                fragment_path=fragment_path,
            ),
            report,
        )

        self.assertFalse(fragment_path.exists())
        self.assertEqual(report.fragments_cleaned, 1)

    def test_multi_mode_duplicate_check_deletes_new_duplicate_candidate(self) -> None:
        self._write_problem_package(
            multi_solution_hint="multi",
            standard_answer="标准答案",
        )
        existing_fragment_path = self.output_root / "demo" / "prob_demo_1.json"
        self._write_json(
            existing_fragment_path,
            {
                "file_id": "demo",
                "problem_id": "prob_demo",
                "question_text": "题目文本",
                "standard_answer": "标准答案",
                "images": ["test/example.png"],
                "source_meta": {},
                "multi_solution_hint": "multi",
                "ingest_status": "ready",
                "method_id": 1,
                "cot": "<existing_cot>",
                "generated_answer": "标准答案",
                "answer_matches_standard": True,
                "is_duplicate_with_existing_complete_method": False,
                "gemini_checked": True,
                "is_complete_fragment": True,
            },
        )

        generation_backend = FakeGenerationBackend()
        duplicate_backend = FakeDuplicateBackend(duplicate=True)
        gemini_backend = FakeGeminiBackend()

        pipeline = Problems2CotPipeline(
            self.config,
            generation_backend=generation_backend,
            duplicate_backend=duplicate_backend,
            gemini_backend=gemini_backend,
        )
        report = pipeline.run()

        self.assertTrue(existing_fragment_path.exists())
        self.assertFalse((self.output_root / "demo" / "prob_demo_2.json").exists())
        self.assertEqual(generation_backend.calls, 1)
        self.assertEqual(duplicate_backend.calls, 1)
        self.assertEqual(gemini_backend.calls, 0)
        self.assertEqual(report.fragments_created, 1)
        self.assertEqual(report.fragments_completed, 0)
        self.assertEqual(report.fragments_cleaned, 1)

    def _write_problem_package(self, *, multi_solution_hint: Any, standard_answer: str) -> None:
        package_path = self.input_root / "demo" / "demo.json"
        self._write_json(
            package_path,
            {
                "file_id": "demo",
                "stage": "raw_to_problem",
                "source_file_name": "demo.json",
                "problems": [
                    {
                        "problem_id": "prob_demo",
                        "question_text": "题目文本",
                        "standard_answer": standard_answer,
                        "images": ["test/example.png"],
                        "source_meta": {},
                        "multi_solution_hint": multi_solution_hint,
                        "ingest_status": "ready",
                    }
                ],
            },
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


if __name__ == "__main__":
    unittest.main()
