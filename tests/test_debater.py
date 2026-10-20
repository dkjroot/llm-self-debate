import contextlib
import copy
import io
import json
import os
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from diagnostics import Redactor, Trace, atomic_replace, inspect_run, load_artifact, read_events
from prompts import character_messages, dialogue_messages, scenario_messages
from debater import (DEFAULTS, DebateError, choose_speaker, clean_speech, load_config,
                     load_inputs, main, make_client, parse_transcript, read_json,
                     request_parameters, resolve_key, run_debate, validate_checkpoint,
                     validate_config)

ROOT = Path(__file__).resolve().parents[1]


def config(**overrides):
    return {**DEFAULTS, "base_url": "http://localhost:5001/v1/", "model": "fake",
            "retry_delay": 0, **overrides}


def state(**overrides):
    return load_inputs(ROOT, config(**overrides))


def response(text='"A concrete objection."', usage=True):
    return NS(id="response-1", choices=[NS(message=NS(content=text), finish_reason="stop")],
              usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15) if usage else None)


class FakeClient:
    def __init__(self, replies=None):
        self.replies = iter(replies) if replies is not None else None
        self.requests = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        value = next(self.replies) if self.replies is not None else response()
        if isinstance(value, BaseException):
            raise value
        return value


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "runs" / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def run_fake(self, initial=None, client=None, key=""):
        with contextlib.redirect_stdout(io.StringIO()):
            return run_debate(initial or state(max_turns=2), self.output,
                              client=client or FakeClient(), key=key)

    def events(self, result):
        return read_events(result["directory"] / "trace.jsonl")[0]

    def test_all_paths_valid_and_global_scenario_schedule(self):
        client = FakeClient()
        result = self.run_fake(state(max_turns=4,
            update_dynamic_character_prompt_every_N_statements=2,
            new_dynamic_scenario_prompt_every_N_statements=2), client)
        self.assertEqual(result["status"], "complete")
        events = self.events(result)
        starts = [e for e in events if e["event"] == "call_started"]
        self.assertEqual({e["kind"] for e in starts}, {"character", "dialogue", "scenario"})
        self.assertEqual([e["turn_id"] for e in starts if e["kind"] == "scenario"], [2, 4])
        for request in client.requests:
            for message in request["messages"]:
                self.assertIn(message["role"], ("system", "assistant", "user"))
                self.assertIsInstance(message["content"], str)
        for e, actual in zip(starts, client.requests):
            self.assertEqual(load_artifact(result["directory"], e["request"]), actual)
        self.assertEqual(result["state"]["usage"]["total_tokens"], len(client.requests) * 15)
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))
        checkpoint = read_json(result["directory"] / "checkpoint.json")
        validate_checkpoint(checkpoint)
        self.assertNotEqual(checkpoint["scenario"]["scenario_variable"], state()["scenario"]["scenario_variable"])

    def test_schedule_exhaustion_skips_final_repeated_speaker(self):
        speaker, index, detail = choose_speaker("Ted", ["Ted", "Ted"], ["Ted", "May"], 0, random.Random(0))
        self.assertEqual((speaker, index), ("May", 2))
        self.assertEqual(detail["skipped"], ["Ted", "Ted"])
        self.assertEqual(detail["mode"], "random")

    def test_single_character_and_unknown_schedule_rejected(self):
        for names, order in [(["Ted"], []), (["Ted", "May"], ["Nobody"])]:
            with self.assertRaises(DebateError):
                choose_speaker("Ted", order, names, 0, random.Random(0))

    def test_transcript_empty_and_multiline(self):
        self.assertEqual(parse_transcript("\n", ["Ted", "May"]), [])
        self.assertEqual(parse_transcript('Ted: "first\nsecond"', ["Ted"])[0]["content"], 'Ted: "first second"')
        for text in ("unlabelled", "Nobody: hello", "Ted: ", 'Ted: "hello"\nNobody: no'):
            with self.assertRaises(DebateError):
                parse_transcript(text, ["Ted", "May"])

    def test_roster_and_schedule_input_validation(self):
        inputs = self.output / "inputs"
        inputs.mkdir()
        for filename in ("names.txt", "speaker_order.txt", "initial_conversation.txt", "system_prompt.json",
                         "May_prompt.json", "Ben_prompt.json", "Violet_prompt.json", "Pete_prompt.json", "Ted_prompt.json"):
            (inputs / filename).write_bytes((ROOT / filename).read_bytes())
        (inputs / "names.txt").write_text(" May , Ben , Violet , Pete , Ted ", encoding="utf-8")
        self.assertEqual(load_inputs(inputs, config())["names"][0], "May")
        for bad in ("May", "May,May", "May,Ben,", "../outside,Ben"):
            (inputs / "names.txt").write_text(bad, encoding="utf-8")
            with self.assertRaises(DebateError):
                load_inputs(inputs, config())
        (inputs / "names.txt").write_text("May,Ben", encoding="utf-8")
        with self.assertRaisesRegex(DebateError, "unknown"):
            load_inputs(inputs, config())

    def test_bad_config(self):
        for field, value in [("max_turns", 0), ("max_calls", True), ("max_retries", -1),
                             ("timeout", float("nan")), ("top_p", 2), ("trace_level", "verbose"),
                             ("new_dynamic_scenario_prompt_every_N_statements", -1),
                             ("base_url", "https://user:pass@example.com/v1/"),
                             ("base_url", "https://example.com/v1/?key=secret"),
                             ("base_url", "http://example.com/v1/"), ("model", ""),
                             ("api_key_env", None), ("api_key", 123)]:
            with self.subTest(field=field, value=value), self.assertRaises((DebateError, TypeError)):
                validate_config(config(**{field: value}))

    def test_credentials_env_only_for_remote(self):
        remote = config(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                        api_key_env="GEMINI_API_KEY")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_key(config()), "local-no-key")
            self.assertEqual(resolve_key(remote, required=False), "")
            with self.assertRaises(DebateError):
                resolve_key(remote)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sentinel-key"}, clear=True):
            self.assertEqual(resolve_key(remote), "sentinel-key")
        with self.assertRaises(DebateError):
            resolve_key({**remote, "api_key": "inline-key"})

    def test_env_endpoint_and_model_are_explicit_overrides(self):
        with patch.dict(os.environ, {"DEBATE_BASE_URL": "https://example.com/v1/", "DEBATE_MODEL": "chosen"}):
            loaded = load_config(ROOT / "config.json")
        self.assertEqual(loaded["model"], "chosen")
        self.assertEqual(loaded["base_url"], "https://example.com/v1/")

    def test_cleanup_preserves_embedded_names(self):
        text, detail = clean_speech('Ted: "Ask May: what about cost?" trailing', ["Ted", "May"])
        self.assertEqual(text, '"Ask May: what about cost?"')
        self.assertTrue(detail["prefix_or_trailing_text_removed"])
        for invalid in ('Ted:', '""'):
            with self.assertRaises(DebateError):
                clean_speech(invalid, ["Ted"])

    def test_malformed_response_does_not_commit_or_repeat_turn(self):
        for malformed in (response(None), response(" "), NS(choices=[], usage=None), response('Violet:')):
            with self.subTest(malformed=malformed):
                initial = state(max_turns=1, update_dynamic_character_prompt_every_N_statements=0)
                result = self.run_fake(initial, FakeClient([malformed]))
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["state"]["turns"], 0)
                self.assertEqual(result["state"]["conversation"], initial["conversation"])
                self.assertIn("validation_failed", [e["event"] for e in self.events(result)])

    def test_empty_prompt_update_is_not_accepted(self):
        initial = state(max_turns=1, update_dynamic_character_prompt_every_N_statements=1)
        result = self.run_fake(initial, FakeClient([response("")]))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["state"]["personas"], initial["personas"])
        changes = [e for e in self.events(result) if e["event"] == "prompt_changed"]
        self.assertEqual(changes[0]["outcome"], "rejected")

    def test_empty_scenario_update_keeps_committed_dialogue_and_prior_scenario(self):
        initial = state(max_turns=1, update_dynamic_character_prompt_every_N_statements=0,
                        new_dynamic_scenario_prompt_every_N_statements=1)
        result = self.run_fake(initial, FakeClient([response(), response(None)]))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["state"]["turns"], 1)
        self.assertEqual(result["state"]["phase"], "scenario")
        self.assertEqual(result["state"]["scenario"], initial["scenario"])
        self.assertIn("rejected", inspect_run(result["directory"]))

    def test_retries_and_updates_count_toward_call_limit(self):
        client = FakeClient([TimeoutError("temporary"), response(), response()])
        result = self.run_fake(state(max_turns=5, max_calls=2,
            update_dynamic_character_prompt_every_N_statements=1), client)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(result["reason"], "call_limit")
        self.assertEqual(result["state"]["turns"], 0)
        self.assertEqual(result["state"]["phase"], "dialogue")
        self.assertEqual(len([e for e in self.events(result) if e["event"] == "call_error"]), 1)

    def test_nontransient_error_not_retried(self):
        result = self.run_fake(state(max_turns=1), FakeClient([ValueError("bad request")]))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["state"]["calls_used"], 1)

    def test_resume_pending_scenario_and_rng_matches_uninterrupted(self):
        initial = state(max_turns=8, max_calls=100,
                        update_dynamic_character_prompt_every_N_statements=2,
                        new_dynamic_scenario_prompt_every_N_statements=2)
        initial["order"] = []  # Exercise seeded random selection and RNG restoration.
        all_client = FakeClient()
        complete = self.run_fake(initial, all_client)
        first_client = FakeClient()
        partial = self.run_fake({**initial, "config": {**initial["config"], "max_calls": 4}}, first_client)
        resumed_state = read_json(partial["directory"] / "checkpoint.json")
        validate_checkpoint(resumed_state)
        resumed_state["config"]["max_calls"] = 100
        second_client = FakeClient()
        resumed = self.run_fake(resumed_state, second_client)
        self.assertEqual(complete["status"], "complete", complete["reason"])
        self.assertEqual(resumed["status"], "complete", resumed["reason"])
        self.assertEqual(first_client.requests + second_client.requests, all_client.requests)
        for field in ("conversation", "personas", "scenario", "turns", "index", "counts", "calls_used", "rng_state"):
            # JSON converts tuples into lists; compare canonical serialization.
            self.assertEqual(json.dumps(resumed["state"][field]), json.dumps(complete["state"][field]))

    def test_interrupt_after_dialogue_preserves_pending_scenario(self):
        initial = state(max_turns=2, new_dynamic_scenario_prompt_every_N_statements=1,
                        update_dynamic_character_prompt_every_N_statements=0)
        partial = self.run_fake(initial, FakeClient([response(), KeyboardInterrupt()]))
        self.assertEqual(partial["status"], "interrupted")
        saved = read_json(partial["directory"] / "checkpoint.json")
        self.assertEqual(saved["phase"], "scenario")
        self.assertEqual(saved["turns"], 1)
        resumed = self.run_fake(saved)
        self.assertEqual(resumed["state"]["turns"], 2)
        self.assertEqual(len(resumed["state"]["conversation"]), len(initial["conversation"]) + 2)

    def test_interrupt_printing_prompt_does_not_repeat_accepted_update(self):
        initial = state(max_turns=1, print_new_dynamic_prompts=True,
                        update_dynamic_character_prompt_every_N_statements=1)
        with patch("builtins.print", side_effect=KeyboardInterrupt()):
            partial = self.run_fake(initial)
        saved = read_json(partial["directory"] / "checkpoint.json")
        self.assertEqual(saved["phase"], "dialogue")
        saved["config"]["print_new_dynamic_prompts"] = False
        resumed = self.run_fake(saved)
        starts = [e for e in self.events(resumed) if e["event"] == "call_started"]
        self.assertEqual(starts[0]["kind"], "dialogue")

    def test_checkpoints_validate_and_detect_inconsistent_counts(self):
        saved = state()
        validate_checkpoint(saved)
        saved["counts"]["Ted"] += 1
        with self.assertRaises(DebateError):
            validate_checkpoint(saved)

    def test_atomic_replace_retries_transient_windows_denial_and_preserves_other_errors(self):
        denied = PermissionError("brief sharing violation")
        denied.winerror = 32
        with patch.object(Path, "replace", side_effect=[denied, None]) as replace, \
                patch("diagnostics.time.sleep"):
            atomic_replace(Path("temporary"), Path("checkpoint"))
        self.assertEqual(replace.call_count, 2)
        with patch.object(Path, "replace", side_effect=denied) as replace, \
                patch("diagnostics.time.sleep"), self.assertRaises(PermissionError):
            atomic_replace(Path("temporary"), Path("checkpoint"))
        self.assertEqual(replace.call_count, 6)
        with patch.object(Path, "replace", side_effect=OSError("disk error")) as replace, \
                self.assertRaises(OSError):
            atomic_replace(Path("temporary"), Path("checkpoint"))
        self.assertEqual(replace.call_count, 1)

    def test_trace_is_passive_and_metadata_or_off_options(self):
        requests = []
        for level in ("full", "metadata", "off"):
            client = FakeClient()
            result = self.run_fake(state(max_turns=5, trace_level=level), client)
            requests.append(client.requests)
            if level == "off":
                self.assertFalse((result["directory"] / "trace.jsonl").exists())
            else:
                self.assertTrue((result["directory"] / "report.txt").exists())
            if level == "metadata":
                self.assertFalse((result["directory"] / "artifacts").exists())
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(requests[0], requests[2])

    def test_no_secret_in_artifacts_console_or_errors(self):
        secret = "SENTINEL_REAL_API_KEY_12345"
        initial = state(max_turns=2)
        initial["personas"]["Violet"]["variable_prompt"] += secret
        initial["config"]["api_key"] = secret
        client = FakeClient([response(f'"echo {secret}"'), ValueError(f"Authorization: Bearer {secret}")])
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            result = run_debate(initial, self.output, client=client, key=secret)
        self.assertNotIn(secret, console.getvalue())
        for path in result["directory"].rglob("*"):
            if path.is_file():
                self.assertNotIn(secret, path.read_text(encoding="utf-8"), str(path))

    def test_dry_run_never_constructs_client_or_writes_runs(self):
        console = io.StringIO()
        with patch("debater.make_client", side_effect=AssertionError("network forbidden")), \
                contextlib.redirect_stdout(console):
            result = main(["--input-dir", str(ROOT), "--config", str(ROOT / "config.json"),
                           "--output-dir", str(self.output), "--dry-run"])
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(console.getvalue())["offline"])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_report_filters_diffs_and_anomalies(self):
        result = self.run_fake(state(max_turns=2, update_dynamic_character_prompt_every_N_statements=1))
        report = inspect_run(result["directory"], speaker="Violet", event_type="prompt_changed")
        self.assertIn("--- before", report)
        self.assertIn("+++ after", report)
        self.assertNotIn("] turn_committed", report)
        trace = Trace(result["directory"], "faulty")
        trace.sequence = 1000
        trace.emit("update_decision", kind="scenario", count=3, interval=2, due=True, reason="fault")
        bad = trace.artifact(dict(messages=[dict(role="Ted", content={})]))
        trace.emit("call_started", call_id="bad", kind="scenario", attempt=1, request=bad)
        report = inspect_run(result["directory"])
        self.assertIn("schedule does not match interval", report)
        self.assertIn("invalid message role/content", report)
        self.assertIn("Calls without a completion/error", report)

    def test_failed_call_filter_and_repetition_heuristic(self):
        result = self.run_fake(state(max_turns=2,
            update_dynamic_character_prompt_every_N_statements=0),
            FakeClient([TimeoutError("temporary"), response(), response()]))
        self.assertIn("call_error", inspect_run(result["directory"], failed_only=True))
        self.assertNotIn("turn_committed", inspect_run(result["directory"], failed_only=True))
        self.assertIn("heuristic: exact repetition", inspect_run(result["directory"]))
        self.assertIn("turn 2", inspect_run(result["directory"], turn=2))

    def test_truncated_final_trace_and_corrupt_middle(self):
        path = self.output / "trace.jsonl"
        path.write_bytes(b'{"schema_version":1}\n{"sche')
        events, warnings = read_events(path)
        self.assertEqual(len(events), 1)
        self.assertTrue(warnings)
        path.write_bytes(b'not json\n{"schema_version":1}\n')
        with self.assertRaises(ValueError):
            read_events(path)

    def test_missing_usage_is_visible(self):
        result = self.run_fake(state(max_turns=1,
            update_dynamic_character_prompt_every_N_statements=0), FakeClient([response(usage=False)]))
        self.assertEqual(result["state"]["usage_missing"], 1)
        self.assertIn("omitted token usage", inspect_run(result["directory"]))

    def test_model_request_custom_token_parameter(self):
        request = request_parameters(config(token_parameter="max_completion_tokens"),
                                     [dict(role="user", content="Hi")])
        self.assertNotIn("max_tokens", request)
        self.assertEqual(request["max_completion_tokens"], 1024)


class SDKTransportTests(unittest.TestCase):
    def test_cli_gemini_shape_run_inspect_and_resume_with_offline_sdk(self):
        import httpx
        from openai import OpenAI
        captured = []

        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=dict(id="mock", object="chat.completion", created=0,
                model="offline-model", choices=[dict(index=0, message=dict(role="assistant", content='"Example."'),
                                                      finish_reason="stop")]))

        scratch = ROOT / "runs" / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary, \
                httpx.Client(transport=httpx.MockTransport(handle)) as http_client, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "offline-dummy", "DEBATE_MODEL": "offline-model"}), \
                contextlib.redirect_stdout(io.StringIO()) as console:
            directory = Path(temporary)
            client = OpenAI(api_key="offline-dummy", base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                            http_client=http_client, max_retries=0)
            with patch("debater.make_client", return_value=client):
                self.assertEqual(main(["--config", str(ROOT / "config.gemini.example.json"),
                    "--input-dir", str(ROOT), "--output-dir", str(directory), "--max-turns", "4"]), 0)
                first = next(directory.iterdir())
                events = read_events(first / "trace.jsonl")[0]
                self.assertEqual({e["kind"] for e in events if e["event"] == "call_started"},
                                 {"dialogue", "character", "scenario"})
                self.assertEqual(main(["inspect", str(first), "--speaker", "Violet"]), 0)
                os.environ["DEBATE_MODEL"] = "must-not-override-resume"
                self.assertEqual(main(["--resume", str(first / "checkpoint.json"),
                    "--output-dir", str(directory), "--max-turns", "5", "--max-calls", "12"]), 0)
                second = next(path for path in directory.iterdir() if path != first)
                self.assertEqual(read_json(second / "checkpoint.json")["turns"], 5)
            self.assertNotIn("offline-dummy", console.getvalue())
            self.assertTrue(all(request["model"] == "offline-model" for request in captured))

    def test_actual_pinned_sdk_serializes_three_paths_without_network(self):
        import httpx
        from openai import OpenAI
        requests = []

        def handle(request):
            requests.append(json.loads(request.content))
            self.assertEqual(request.url.path, "/v1beta/openai/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer dummy")
            return httpx.Response(200, json=dict(id="mock", object="chat.completion", created=0,
                model="configured-model", choices=[dict(index=0, message=dict(role="assistant", content="ok"),
                                                       finish_reason="stop")]))

        with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
            client = OpenAI(api_key="dummy", base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                            http_client=http_client, max_retries=0, timeout=1)
            initial = state()
            for messages in (dialogue_messages("Ted", initial["personas"], initial["scenario"], initial["conversation"]),
                             character_messages("Ted", initial["personas"], initial["conversation"]),
                             scenario_messages(initial["scenario"], initial["conversation"])):
                self.assertEqual(client.chat.completions.create(**request_parameters(config(), messages)).choices[0].message.content, "ok")
        self.assertEqual(len(requests), 3)


if __name__ == "__main__":
    unittest.main()
