from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path
from typing import Any

from config import OpenAICompatibleBackendConfig, Problems2CotConfig
from problems2cot import (
    AnswerMatcher,
    OpenAICompatibleChatClient,
    OpenAICompatibleCoTGenerationBackend,
    OpenAICompatibleDuplicateCheckBackend,
    OpenAICompatibleGeminiReviewBackend,
    CoTFragmentScanner,
    CoTFragmentStore,
    CoTGenerator,
    DuplicateMethodChecker,
    FragmentTask,
    FragmentTaskExecutor,
    GeminiDetailChecker,
    GeminiReviewResult,
    GeneratedCoT,
    ProblemImageLocator,
    ProblemPackageReader,
    Problems2CotPipeline,
    Problems2CotReport,
)


class RecordingTransport:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload
        self.calls = 0
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None
        self.last_payload: dict[str, Any] | None = None
        self.last_timeout_seconds: float | None = None

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls += 1
        self.last_url = url
        self.last_headers = dict(headers)
        self.last_payload = dict(payload)
        self.last_timeout_seconds = timeout_seconds
        return self.response_payload


class FakeGenerationBackend:
    def __init__(self, generated_answer: str | None = None) -> None:
        self.generated_answer = generated_answer
        self.calls = 0
        self.last_image_root: Path | None = None
        self.last_image_paths: list[Path] | None = None

    def generate(
        self,
        *,
        file_id: str,
        problem_id: str,
        method_id: int,
        question_text: str,
        standard_answer: str,
        images: list[str],
        image_root: Path,
        image_paths: list[Path],
        multi_solution_hint: Any,
    ):
        self.calls += 1
        self.last_image_root = image_root
        self.last_image_paths = list(image_paths)
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
        self.last_image_root: Path | None = None
        self.last_image_paths: list[Path] | None = None

    def review(
        self,
        *,
        fragment: dict[str, Any],
        image_root: Path,
        image_paths: list[Path],
    ) -> GeminiReviewResult:
        self.calls += 1
        self.last_image_root = image_root
        self.last_image_paths = list(image_paths)
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
            image_root=self.root / "layer_input",
            cot_generation_backend=OpenAICompatibleBackendConfig(
                name="test_generation",
                base_url="https://example.test/openai",
                api_key="sk-test-generation",
                model="gpt-test",
                timeout_seconds=11.0,
                temperature=0.2,
                max_tokens=512,
            ),
            duplicate_check_backend=OpenAICompatibleBackendConfig(
                name="test_duplicate",
                base_url="https://example.test/openai",
                api_key="sk-test-duplicate",
                model="gpt-test-mini",
                timeout_seconds=7.0,
                temperature=0.0,
                max_tokens=256,
            ),
            gemini_review_backend=OpenAICompatibleBackendConfig(
                name="test_gemini",
                base_url="https://example.test/gemini-openai",
                api_key="sk-test-gemini",
                model="gemini-test",
                timeout_seconds=13.0,
                temperature=0.0,
                max_tokens=1024,
            ),
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
        self.assertEqual(generation_backend.last_image_root, self.root / "layer_input" / "demo")
        self.assertEqual(
            generation_backend.last_image_paths,
            [self.root / "layer_input" / "demo" / "test" / "example.png"],
        )
        self.assertEqual(gemini_backend.last_image_root, self.root / "layer_input" / "demo")
        self.assertEqual(
            gemini_backend.last_image_paths,
            [self.root / "layer_input" / "demo" / "test" / "example.png"],
        )
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
        image_locator = ProblemImageLocator()
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
            CoTGenerator(self.config, store, image_locator, FakeGenerationBackend()),
            AnswerMatcher(self.config, store),
            DuplicateMethodChecker(self.config, store, FakeDuplicateBackend()),
            GeminiDetailChecker(self.config, store, image_locator, FakeGeminiBackend()),
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

    def test_openai_compatible_generation_backend_builds_multimodal_request(self) -> None:
        self._write_problem_package(
            multi_solution_hint=None,
            standard_answer="42",
        )
        image_path = self.root / "layer_input" / "demo" / "test" / "example.png"
        transport = RecordingTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"cot": "generated cot", "generated_answer": "42"}'
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleChatClient(self.config.cot_generation_backend, transport=transport)
        backend = OpenAICompatibleCoTGenerationBackend(self.config, client=client)

        result = backend.generate(
            file_id="demo",
            problem_id="prob_demo",
            method_id=1,
            question_text="question",
            standard_answer="42",
            images=["test/example.png"],
            image_root=self.root / "layer_input" / "demo",
            image_paths=[image_path],
            multi_solution_hint=None,
        )

        self.assertEqual(result.cot, "generated cot")
        self.assertEqual(result.generated_answer, "42")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(transport.last_url, "https://example.test/openai/chat/completions")
        self.assertEqual(
            transport.last_headers,
            {"Authorization": "Bearer sk-test-generation"},
        )
        self.assertEqual(transport.last_timeout_seconds, 11.0)
        self.assertEqual(transport.last_payload["model"], "gpt-test")
        self.assertEqual(transport.last_payload["temperature"], 0.2)
        self.assertEqual(transport.last_payload["max_tokens"], 512)
        self.assertEqual(
            transport.last_payload["messages"][0]["content"],
            self.config.cot_generation_system_prompt,
        )
        user_content = transport.last_payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_openai_compatible_duplicate_backend_parses_boolean_result(self) -> None:
        transport = RecordingTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": 'duplicate decision\n{"is_duplicate": true, "reason": "same method"}'
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleChatClient(self.config.duplicate_check_backend, transport=transport)
        backend = OpenAICompatibleDuplicateCheckBackend(self.config, client=client)

        is_duplicate = backend.is_duplicate(
            candidate_fragment={"problem_id": "prob_demo", "cot": "candidate", "generated_answer": "42"},
            existing_complete_fragments=[
                {"problem_id": "prob_demo", "cot": "existing", "generated_answer": "42"}
            ],
        )

        self.assertIs(is_duplicate, True)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(transport.last_url, "https://example.test/openai/chat/completions")
        user_content = transport.last_payload["messages"][1]["content"]
        self.assertEqual(len(user_content), 1)
        self.assertEqual(user_content[0]["type"], "text")

    def test_openai_compatible_gemini_backend_parses_review_result(self) -> None:
        self._write_problem_package(
            multi_solution_hint=None,
            standard_answer="42",
        )
        image_path = self.root / "layer_input" / "demo" / "test" / "example.png"
        transport = RecordingTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        '{"passed": true, "cot": "refined cot", '
                                        '"generated_answer": "42", "reason": "ok"}'
                                    ),
                                }
                            ]
                        }
                    }
                ]
            }
        )
        client = OpenAICompatibleChatClient(self.config.gemini_review_backend, transport=transport)
        backend = OpenAICompatibleGeminiReviewBackend(self.config, client=client)

        result = backend.review(
            fragment={
                "problem_id": "prob_demo",
                "question_text": "question",
                "standard_answer": "42",
                "cot": "draft cot",
                "generated_answer": "42",
            },
            image_root=self.root / "layer_input" / "demo",
            image_paths=[image_path],
        )

        self.assertIs(result.passed, True)
        self.assertEqual(result.cot, "refined cot")
        self.assertEqual(result.generated_answer, "42")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(transport.last_url, "https://example.test/gemini-openai/chat/completions")

    def _write_problem_package(self, *, multi_solution_hint: Any, standard_answer: str) -> None:
        package_path = self.input_root / "demo" / "demo.json"
        image_root = self.root / "layer_input" / "demo" / "test"
        image_root.mkdir(parents=True, exist_ok=True)
        (image_root / "example.png").write_bytes(b"fake-image")
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
