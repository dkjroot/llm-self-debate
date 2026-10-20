"""Exercise the real SDK/socket path against a local KoboldCpp-shaped server.

This verifies HTTP contracts and authentication, not real model generation.
"""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from debater import load_config, load_inputs, main, read_json
from diagnostics import read_events

ROOT = Path(__file__).resolve().parents[1]


class KoboldCppHTTPTests(unittest.TestCase):
    def test_local_cli_uses_real_sdk_and_http_for_all_paths_with_and_without_password(self):
        for password in (None, "test-kobold-password-sentinel"):
            with self.subTest(password_protected=password is not None):
                captured = []
                failures = []

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass

                    def do_POST(self):
                        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        captured.append((self.path, self.headers.get("Authorization"), payload))
                        if password and self.headers.get("Authorization") != "Bearer " + password:
                            self.send_response(401)
                            self.end_headers()
                            self.wfile.write(b'{"error":{"message":"Unauthorized"}}')
                            return
                        valid = (self.path == "/v1/chat/completions"
                                 and payload.get("model") == "koboldcpp"
                                 and payload.get("max_tokens") == 1024
                                 and "max_completion_tokens" not in payload
                                 and payload.get("temperature") == 0.6
                                 and payload.get("top_p") == 0.9
                                 and all(message.get("role") in ("system", "user", "assistant")
                                         and isinstance(message.get("content"), str)
                                         for message in payload.get("messages", [])))
                        if not valid:
                            failures.append(payload)
                        content = json.dumps(dict(
                            id="chatcmpl-koboldcpp-test", object="chat.completion", created=0,
                            model="koboldcpp/test-model",
                            choices=[dict(index=0, message=dict(role="assistant", content='"A local response."'),
                                          finish_reason="stop")],
                            usage=dict(prompt_tokens=25, completion_tokens=5, total_tokens=30))).encode()
                        self.send_response(200 if valid else 400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                scratch = ROOT / "runs" / "tests"
                scratch.mkdir(parents=True, exist_ok=True)
                try:
                    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
                        directory = Path(temporary)
                        configuration = read_json(ROOT / "config.koboldcpp.example.json")
                        configuration.update(base_url=f"http://127.0.0.1:{server.server_port}/v1/",
                                             timeout=3, max_turns=2, max_calls=8,
                                             update_dynamic_character_prompt_every_N_statements=1,
                                             new_dynamic_scenario_prompt_every_N_statements=1)
                        config_path = directory / "config.json"
                        config_path.write_text(json.dumps(configuration), encoding="utf-8")
                        env = {"DEBATE_API_KEY": password or "", "DEBATE_MODEL": "", "DEBATE_BASE_URL": "",
                               "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
                        with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()) as console:
                            status = main(["--config", str(config_path), "--input-dir", str(ROOT),
                                           "--output-dir", str(directory / "output")])
                        self.assertEqual(status, 0, console.getvalue())
                        self.assertFalse(failures)
                        self.assertEqual(len(captured), 6)  # Two turns, all three call kinds per turn.
                        expected_key = password or "local-no-key"
                        self.assertTrue(all(auth == "Bearer " + expected_key for _, auth, _ in captured))
                        run = next((directory / "output").iterdir())
                        events = read_events(run / "trace.jsonl")[0]
                        self.assertEqual({event["kind"] for event in events if event["event"] == "call_started"},
                                         {"dialogue", "character", "scenario"})
                        checkpoint = read_json(run / "checkpoint.json")
                        self.assertEqual(checkpoint["turns"], 2)
                        self.assertEqual(checkpoint["usage"]["total_tokens"], 180)
                        if password:
                            self.assertNotIn(password, console.getvalue())
                            for artifact in run.rglob("*"):
                                if artifact.is_file():
                                    self.assertNotIn(password, artifact.read_text(encoding="utf-8"))
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)

    def test_koboldcpp_example_is_portable_and_can_dry_run_without_key(self):
        with patch.dict(os.environ, {"DEBATE_MODEL": "", "DEBATE_BASE_URL": "", "DEBATE_API_KEY": ""}):
            configuration = load_config(ROOT / "config.koboldcpp.example.json")
            self.assertEqual(configuration["base_url"], "http://127.0.0.1:5001/v1/")
            self.assertEqual(configuration["model"], "koboldcpp")
            self.assertEqual(configuration["timeout"], 600)
            self.assertEqual(configuration["max_retries"], 0)
            load_inputs(ROOT, configuration)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--config", str(ROOT / "config.koboldcpp.example.json"),
                                       "--input-dir", str(ROOT), "--dry-run"]), 0)
            self.assertTrue(json.loads(output.getvalue())["offline"])


if __name__ == "__main__":
    unittest.main()
