"""Validated inputs, bounded requests, and checkpointed debate orchestration."""
import argparse
import copy
import hashlib
import importlib.metadata
import ipaddress
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

from diagnostics import Redactor, Trace, atomic_replace, inspect_run, prompt_diff, utc_now, write_json
from prompts import character_messages, dialogue_messages, scenario_messages

DEFAULTS = dict(max_turns=20, max_calls=40, timeout=60, max_retries=1,
                retry_delay=1, seed=0, trace_level="full", max_tokens=1024,
                temperature=0.6, top_p=0.9,
                update_dynamic_character_prompt_every_N_statements=3,
                new_dynamic_scenario_prompt_every_N_statements=8,
                print_new_dynamic_prompts=False)


class DebateError(ValueError):
    pass


class BudgetReached(DebateError):
    pass


class InvalidResponse(DebateError):
    def __init__(self, kind, raw, call_id, parent):
        super().__init__(f"{kind}: missing or empty text response")
        self.raw, self.call_id, self.parent = raw, call_id, parent


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DebateError(f"Cannot read JSON file {Path(path).name}") from exc


def read_list(path):
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    values = [item.strip() for item in text.split(",")]
    if not all(values):
        raise DebateError(f"Empty name in {Path(path).name}")
    return values


def is_local_endpoint(hostname):
    if hostname == "localhost" or hostname.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
        return address.is_private or address.is_loopback
    except ValueError:
        return False


def validate_config(config):
    for name, minimum in (("max_turns", 1), ("max_calls", 1), ("max_retries", 0),
                          ("max_tokens", 1), ("seed", 0),
                          ("update_dynamic_character_prompt_every_N_statements", 0),
                          ("new_dynamic_scenario_prompt_every_N_statements", 0)):
        if type(config.get(name)) is not int or config[name] < minimum:
            raise DebateError(f"{name} must be an integer >= {minimum}")
    for name, low, high in (("temperature", 0, 2), ("top_p", 0, 1),
                            ("timeout", 0.001, 3600), ("retry_delay", 0, 60)):
        value = config.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise DebateError(f"{name} must be a finite number between {low} and {high}")
    if config.get("trace_level") not in ("full", "metadata", "off"):
        raise DebateError("trace_level must be full, metadata, or off")
    if not isinstance(config.get("model"), str) or not config["model"].strip():
        raise DebateError("Configure a nonempty model ID (or DEBATE_MODEL)")
    if not isinstance(config.get("base_url"), str):
        raise DebateError("Configure base_url")
    url = urlsplit(config["base_url"])
    if (url.scheme not in ("http", "https") or not url.hostname or url.username
            or url.password or url.query or url.fragment):
        raise DebateError("base_url must be an http(s) endpoint without credentials, query, or fragment")
    if not is_local_endpoint(url.hostname) and url.scheme != "https":
        raise DebateError("Remote endpoints must use HTTPS")
    variable = config.get("api_key_env", "DEBATE_API_KEY")
    if not isinstance(variable, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
        raise DebateError("api_key_env must be an environment variable name")
    if "api_key" in config and not isinstance(config["api_key"], str):
        raise DebateError("Legacy api_key must be text; prefer an environment variable")
    if config.get("token_parameter", "max_tokens") not in ("max_tokens", "max_completion_tokens"):
        raise DebateError("token_parameter must be max_tokens or max_completion_tokens")
    if type(config.get("print_new_dynamic_prompts")) is not bool:
        raise DebateError("print_new_dynamic_prompts must be a boolean")


def load_config(path, overrides=None):
    loaded = read_json(path)
    if not isinstance(loaded, dict):
        raise DebateError("Configuration must be an object")
    config = {**DEFAULTS, **loaded}
    for env_name, field in (("DEBATE_BASE_URL", "base_url"), ("DEBATE_MODEL", "model")):
        if os.environ.get(env_name):
            config[field] = os.environ[env_name]
    config.update({k: v for k, v in (overrides or {}).items() if v is not None})
    validate_config(config)
    return config


def resolve_key(config, required=True):
    variable = config.get("api_key_env", "DEBATE_API_KEY")
    key = os.environ.get(variable, "").strip()
    local = is_local_endpoint(urlsplit(config["base_url"]).hostname)
    legacy = config.get("api_key")
    if legacy and not local:
        raise DebateError("Remove api_key from remote config; use api_key_env instead")
    if not key and local:
        key = legacy or "local-no-key"
    if required and not key:
        raise DebateError(f"Set the {variable} environment variable before a live run")
    return key


def text_fields(value, fields, label):
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) for k in fields):
        raise DebateError(f"{label} needs text fields: {', '.join(fields)}")


def parse_transcript(text, names):
    conversation = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        prefix, separator, speech = line.partition(":")
        if separator and prefix in names:
            if not speech.strip():
                raise DebateError(f"Empty speech on transcript line {number}")
            conversation.append(dict(role=prefix, content=f"{prefix}: {speech.strip()}",
                                     turn_id=f"initial-{len(conversation) + 1}"))
        elif not conversation:
            raise DebateError(f"Expected a known speaker on transcript line {number}")
        elif separator and re.fullmatch(r"[\w -]+", prefix) and not line.startswith(('"', "'")):
            raise DebateError(f"Unknown speaker on transcript line {number}: {prefix}")
        else:
            conversation[-1]["content"] += " " + line
    return conversation


def load_inputs(directory, config):
    names = read_list(directory / "names.txt")
    if len(names) < 2 or len(set(names)) != len(names):
        raise DebateError("At least two unique characters are required")
    if any(not re.fullmatch(r"[\w -]+", name) for name in names):
        raise DebateError("Character names must contain only letters, digits, spaces, underscores or hyphens")
    personas = {name: read_json(directory / f"{name}_prompt.json") for name in names}
    for name, persona in personas.items():
        text_fields(persona, ("fixed_prompt", "variable_prompt"), name)
    scenario = read_json(directory / "system_prompt.json")
    text_fields(scenario, ("rules", "scenario_fixed", "scenario_variable"), "Scenario")
    order = read_list(directory / "speaker_order.txt")
    if set(order) - set(names):
        raise DebateError("speaker_order.txt includes unknown characters")
    conversation = parse_transcript((directory / "initial_conversation.txt").read_text(
        encoding="utf-8-sig"), names)
    return dict(schema_version=1, config=config, names=names, personas=personas,
                scenario=scenario, order=order, index=0, conversation=conversation,
                turns=0, counts={name: sum(line["role"] == name for line in conversation)
                                 for name in names}, calls_used=0, usage={}, usage_missing=0,
                rng_state=random.Random(config["seed"]).getstate(),
                last_speaker=conversation[-1]["role"] if conversation else None,
                phase="select", pending_speaker=None)


def choose_speaker(last_speaker, order, names, index, rng):
    if len(set(names)) < 2 or set(order) - set(names):
        raise DebateError("Speaker selection requires two characters and a valid order")
    before, skipped = index, []
    candidates = [name for name in names if name != last_speaker]
    while index < len(order):
        speaker = order[index]
        index += 1
        if speaker != last_speaker:
            return speaker, index, dict(mode="scheduled", candidates=candidates,
                                       skipped=skipped, index_before=before, index_after=index)
        skipped.append(speaker)
    return rng.choice(candidates), index, dict(mode="random", candidates=candidates,
                                             skipped=skipped, index_before=before, index_after=index)


def clean_speech(text, names):
    original = text
    for name in names:
        if text.startswith(name + ":"):
            text = text[len(name) + 1:].lstrip()
            break
    if text.startswith('"') and '"' in text[1:]:
        text = text[:text.rfind('"') + 1]
    text = text.strip()
    if not text or not text.strip('"').strip():
        raise DebateError("Dialogue became empty after cleanup")
    return text, {"prefix_or_trailing_text_removed": text != original}


def request_parameters(config, messages):
    if (not messages or any(m.get("role") not in ("system", "user", "assistant")
                           or not isinstance(m.get("content"), str) for m in messages)):
        raise DebateError("Invalid API message role or content")
    return dict(model=config["model"], messages=messages, temperature=config["temperature"],
                top_p=config["top_p"], **{config.get("token_parameter", "max_tokens"): config["max_tokens"]})


def usage_dict(usage):
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return usage if isinstance(usage, dict) else vars(usage)


def retryable(exc):
    status = getattr(exc, "status_code", None)
    return (isinstance(exc, (TimeoutError, ConnectionError))
            or type(exc).__name__ in ("APIConnectionError", "APITimeoutError")
            or type(status) is int and (status in (408, 409, 429) or status >= 500))


class Requester:
    def __init__(self, client, state, trace, save):
        self.client, self.state, self.trace, self.save = client, state, trace, save

    def call(self, kind, messages):
        config = self.state["config"]
        request = request_parameters(config, messages)
        reference = self.trace.artifact(request)
        parent = None
        for attempt in range(config["max_retries"] + 1):
            if self.state["calls_used"] >= config["max_calls"]:
                raise BudgetReached("call_limit")
            self.state["calls_used"] += 1
            call_id = f"{self.trace.run_id}:{self.state['calls_used']}"
            self.save()  # Reserve attempts even if interrupted in transport.
            parent = self.trace.emit("call_started", call_id=call_id, parent=parent,
                                     kind=kind, attempt=attempt + 1, request=reference)
            start = time.monotonic()
            try:
                response = self.client.chat.completions.create(**request)
            except Exception as exc:
                retry = retryable(exc) and attempt < config["max_retries"]
                parent = self.trace.emit("call_error", call_id=call_id, parent=parent,
                                         kind=kind, error=f"{type(exc).__name__}: {exc}",
                                         elapsed=time.monotonic() - start, retry=retry)
                if not retry:
                    raise DebateError(f"{kind} request failed: {type(exc).__name__}: {exc}") from exc
                time.sleep(config["retry_delay"])
                continue
            choices = getattr(response, "choices", None)
            choice = choices[0] if choices else None
            text = getattr(getattr(choice, "message", None), "content", None)
            usage = usage_dict(getattr(response, "usage", None))
            for key, value in (usage or {}).items():
                if type(value) is int:
                    self.state["usage"][key] = self.state["usage"].get(key, 0) + value
            if usage is None:
                self.state["usage_missing"] += 1
            payload = self.trace.artifact(dict(raw=text, response_id=getattr(response, "id", None),
                                              refusal=getattr(getattr(choice, "message", None), "refusal", None),
                                              finish_reason=getattr(choice, "finish_reason", None), usage=usage))
            parent = self.trace.emit("call_completed", call_id=call_id, parent=parent,
                                     kind=kind, response=payload, usage=usage,
                                     response_id=getattr(response, "id", None),
                                     finish_reason=getattr(choice, "finish_reason", None),
                                     elapsed=time.monotonic() - start)
            self.save()
            if not isinstance(text, str) or not text.strip():
                self.trace.emit("validation_failed", call_id=call_id, parent=parent,
                                kind=kind, error="Missing or empty text response")
                raise InvalidResponse(kind, text, call_id, parent)
            return text.strip(), call_id, parent


def tuple_tree(value):
    return tuple(tuple_tree(item) for item in value) if isinstance(value, list) else value


def code_metadata():
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                  text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
              for name in ("debater.py", "prompts.py", "diagnostics.py")}
    try:
        sdk = importlib.metadata.version("openai")
    except importlib.metadata.PackageNotFoundError:
        sdk = None
    return dict(git_revision=revision, source_sha256=hashes, python=sys.version, openai=sdk)


def make_client(config, key):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise DebateError("Install requirements.txt before a live run") from exc
    return OpenAI(api_key=key, base_url=config["base_url"], timeout=config["timeout"], max_retries=0)


def validate_checkpoint(state):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise DebateError("Unsupported checkpoint format")
    validate_config(state["config"])
    names = state["names"]
    if len(set(names)) != len(names) or len(names) < 2 or set(state["order"]) - set(names):
        raise DebateError("Invalid checkpoint roster/order")
    if state["phase"] not in ("select", "character", "dialogue", "scenario"):
        raise DebateError("Invalid checkpoint phase")
    for field in ("turns", "index", "calls_used", "usage_missing"):
        if type(state[field]) is not int or state[field] < 0:
            raise DebateError(f"Invalid checkpoint {field}")
    if state["index"] > len(state["order"]):
        raise DebateError("Invalid checkpoint schedule index")
    for name in names:
        text_fields(state["personas"][name], ("fixed_prompt", "variable_prompt"), name)
        if state["counts"][name] != sum(line["role"] == name for line in state["conversation"]):
            raise DebateError("Checkpoint character counts do not match transcript")
    text_fields(state["scenario"], ("rules", "scenario_fixed", "scenario_variable"), "Scenario")
    for line in state["conversation"]:
        if line["role"] not in names or not isinstance(line["content"], str) or not line["content"].strip():
            raise DebateError("Invalid checkpoint conversation")
    if state["phase"] != "select" and state["pending_speaker"] not in names:
        raise DebateError("Missing pending checkpoint speaker")
    random.Random().setstate(tuple_tree(state["rng_state"]))


def run_debate(state, output_root, *, client=None, key="", parent_run=None):
    state = copy.deepcopy(state)
    config = state["config"]
    redact = Redactor((key, config.get("api_key")))
    config.pop("api_key", None)
    run_id = utc_now().replace(":", "").replace("+", "_") + "_" + uuid.uuid4().hex[:8]
    directory = Path(output_root) / run_id
    directory.mkdir(parents=True)
    trace = Trace(directory, run_id, redact, config["trace_level"])
    rng = random.Random()
    rng.setstate(tuple_tree(state["rng_state"]))

    def save():
        state["rng_state"] = rng.getstate()
        write_json(directory / "checkpoint.json", state, redact)
        trace.emit("checkpoint_written", path="checkpoint.json", phase=state["phase"])

    def transcript():
        target = directory / "conversation.txt"
        temporary = target.with_suffix(".txt.tmp")
        temporary.write_text(redact("\n\n".join(line["content"] for line in state["conversation"]) + "\n"),
                             encoding="utf-8", newline="\n")
        atomic_replace(temporary, target)
        trace.emit("transcript_written", path="conversation.txt", statements=len(state["conversation"]))

    def update(kind, target, field, messages):
        before = target[field]
        try:
            result, call_id, parent = requester.call(kind, messages)
        except InvalidResponse as exc:
            change = trace.artifact(dict(before=before, proposed=exc.raw, after=before,
                                         diff="", source_turns=[line["turn_id"] for line in state["conversation"]]))
            trace.emit("prompt_changed", call_id=exc.call_id, parent=exc.parent, kind=kind,
                       outcome="rejected", validation="missing or empty text", change=change)
            raise
        change = trace.artifact(dict(before=before, proposed=result, after=result,
                                     diff=prompt_diff(before, result),
                                     source_turns=[line["turn_id"] for line in state["conversation"]]))
        trace.emit("prompt_proposed", call_id=call_id, parent=parent, kind=kind, change=change)
        target[field] = result
        state["phase"] = "dialogue" if kind == "character" else "select"
        if kind == "scenario":
            state["pending_speaker"] = None
        save()  # Commit accepted prompt and next phase before logging/printing it.
        trace.emit("prompt_changed", call_id=call_id, parent=parent, kind=kind,
                   outcome="unchanged" if before == result else "accepted",
                   validation="nonempty text only", change=change)
        if config["print_new_dynamic_prompts"]:
            print(redact(f"{kind}: {result}"))

    def due(kind, count, interval):
        result = bool(interval and count and count % interval == 0)
        trace.emit("update_decision", kind=kind, count=count, interval=interval, due=result,
                   reason="interval reached" if result else "disabled" if not interval else "interval not reached")
        return result

    snapshot = trace.artifact(dict(state=state, code=code_metadata(), parent_run=parent_run))
    trace.emit("run_started", snapshot=snapshot, parent_run=parent_run)
    save()
    transcript()
    requester = Requester(client, state, trace, save)
    status, reason = "complete", "turn_limit"
    try:
        if client is None:
            requester.client = make_client(config, key)
        while True:
            if state["phase"] != "scenario" and state["turns"] >= config["max_turns"]:
                break
            if state["phase"] == "select":
                if state["calls_used"] >= config["max_calls"]:
                    raise BudgetReached("call_limit")
                trace.turn = state["turns"] + 1
                speaker, index, decision = choose_speaker(state["last_speaker"], state["order"],
                                                          state["names"], state["index"], rng)
                trace.speaker = speaker
                state.update(pending_speaker=speaker, index=index, phase="character")
                trace.emit("speaker_selected", last_speaker=state["last_speaker"], **decision)
                save()
            else:
                trace.turn = state["turns"] if state["phase"] == "scenario" else state["turns"] + 1
                trace.speaker = state["pending_speaker"]
            speaker = state["pending_speaker"]
            if state["phase"] == "character":
                if due("character", state["counts"][speaker] + 1,
                       config["update_dynamic_character_prompt_every_N_statements"]):
                    update("character", state["personas"][speaker], "variable_prompt",
                           character_messages(speaker, state["personas"], state["conversation"]))
                state["phase"] = "dialogue"
                save()
            if state["phase"] == "dialogue":
                raw, call_id, parent = requester.call("dialogue", dialogue_messages(
                    speaker, state["personas"], state["scenario"], state["conversation"]))
                try:
                    accepted, transformations = clean_speech(raw, state["names"])
                except DebateError as exc:
                    trace.emit("validation_failed", call_id=call_id, parent=parent, kind="dialogue", error=str(exc))
                    raise
                speech = trace.artifact(dict(raw=raw, accepted=accepted, transformations=transformations))
                state["turns"] += 1
                state["counts"][speaker] += 1
                state["conversation"].append(dict(role=speaker, content=f"{speaker}: {accepted}",
                                                   turn_id=state["turns"]))
                state.update(last_speaker=speaker, phase="scenario")
                save()
                trace.emit("turn_committed", call_id=call_id, parent=parent, speech=speech,
                           turns=state["turns"], character_count=state["counts"][speaker])
                transcript()
                print(redact(f"{speaker}: {accepted}\n"))
            if state["phase"] == "scenario":
                if due("scenario", state["turns"], config["new_dynamic_scenario_prompt_every_N_statements"]):
                    update("scenario", state["scenario"], "scenario_variable",
                           scenario_messages(state["scenario"], state["conversation"]))
                state.update(phase="select", pending_speaker=None)
                save()
    except BudgetReached as exc:
        reason = str(exc)
    except KeyboardInterrupt:
        status, reason = "interrupted", "keyboard_interrupt"
    except Exception as exc:
        status, reason = "error", redact(f"{type(exc).__name__}: {exc}")
        trace.emit("run_error", error=reason)
    finally:
        save()
        trace.emit("run_stopped", status=status, reason=reason, calls_used=state["calls_used"],
                   turns=state["turns"], usage=state["usage"], usage_missing=state["usage_missing"])
        if trace.level != "off":
            (directory / "report.txt").write_text(inspect_run(directory), encoding="utf-8", newline="\n")
    return dict(directory=directory, state=state, status=status, reason=reason)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "inspect":
        parser = argparse.ArgumentParser(description="Inspect a local trace without calling a model")
        parser.add_argument("directory", type=Path)
        parser.add_argument("--speaker")
        parser.add_argument("--turn", type=int)
        parser.add_argument("--event", dest="event_type")
        parser.add_argument("--failed-only", action="store_true")
        args = vars(parser.parse_args(argv[1:]))
        directory = args.pop("directory")
        try:
            print(inspect_run(directory, **args), end="")
            return 0
        except (OSError, ValueError, KeyError) as exc:
            print(f"Inspection failed: {exc}", file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--input-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    parser.add_argument("--resume", type=Path, help="checkpoint.json from a previous run")
    parser.add_argument("--dry-run", action="store_true")
    for option in ("max-turns", "max-calls", "seed"):
        parser.add_argument("--" + option, type=int)
    parser.add_argument("--trace-level", choices=("full", "metadata", "off"))
    parser.add_argument("--no-character-updates", action="store_true")
    parser.add_argument("--no-scenario-updates", action="store_true")
    args = parser.parse_args(argv)
    redact = Redactor()
    try:
        overrides = {name: getattr(args, name) for name in ("max_turns", "max_calls", "seed", "trace_level")}
        if args.no_character_updates:
            overrides["update_dynamic_character_prompt_every_N_statements"] = 0
        if args.no_scenario_updates:
            overrides["new_dynamic_scenario_prompt_every_N_statements"] = 0
        if args.resume:
            if args.seed is not None or args.no_character_updates or args.no_scenario_updates:
                raise DebateError("Resume preserves RNG and update policy; start fresh to change them")
            state = read_json(args.resume)
            validate_checkpoint(state)
            state["config"].update({k: v for k, v in overrides.items() if v is not None})
            validate_config(state["config"])
            config = state["config"]
        else:
            config = load_config(args.config, overrides)
            key = resolve_key(config, required=not args.dry_run)
            redact = Redactor((key, config.get("api_key")))
            state = load_inputs(args.input_dir, config)
        key = resolve_key(config, required=not args.dry_run)
        redact = Redactor((key, config.get("api_key")))
        state["config"].pop("api_key", None)
        if args.dry_run:
            example = state["pending_speaker"] or state["names"][0]
            requests = dict(dialogue=request_parameters(config, dialogue_messages(
                example, state["personas"], state["scenario"], state["conversation"])),
                character=request_parameters(config, character_messages(example, state["personas"], state["conversation"])),
                scenario=request_parameters(config, scenario_messages(state["scenario"], state["conversation"])))
            print(json.dumps(redact(dict(offline=True, config=config, credentials_present=bool(key),
                                          names=state["names"], requests=requests)), ensure_ascii=False, indent=2))
            return 0
        result = run_debate(state, args.output_dir, key=key,
                            parent_run=str(args.resume) if args.resume else None)
        print(redact(f"Run {result['status']}: {result['reason']}\nArtifacts: {result['directory']}"))
        print("Calls:", result["state"]["calls_used"], "Usage:", result["state"]["usage"],
              "Responses without usage:", result["state"]["usage_missing"])
        return 1 if result["status"] == "error" else 130 if result["status"] == "interrupted" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, DebateError) else f"Invalid input ({type(exc).__name__})"
        print(redact(message), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
