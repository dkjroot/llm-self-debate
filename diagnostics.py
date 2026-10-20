"""Local, secret-redacted trace artifacts and offline inspection. No model calls."""
import difflib
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = sorted({s for s in secrets if isinstance(s, str) and s},
                              key=len, reverse=True)

    def __call__(self, value):
        if isinstance(value, dict):
            return {self(str(k)): ("[REDACTED]" if re.search(
                r"^(api_key|authorization|access_token|password|secret|headers)$", str(k), re.I)
                else self(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)Bearer\s+[^\s\"',;]+", "Bearer [REDACTED]", value)
        return value


def atomic_replace(temporary, target):
    """Windows scanners/readers can briefly deny replacement of a writable file."""
    for attempt in range(6):
        try:
            temporary.replace(target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 5:
                raise
            time.sleep(0.02 * (attempt + 1))


def write_json(path, value, redact):
    """Atomic replacement; checkpoint is authoritative if transcript writing fails."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    atomic_replace(temporary, path)


class Trace:
    def __init__(self, directory, run_id, redact=None, level="full"):
        self.directory = Path(directory)
        self.run_id = run_id
        self.redact = redact or Redactor()
        self.level = level
        self.sequence = 0
        self.turn = None
        self.speaker = None

    def artifact(self, value):
        if self.level != "full":
            return None
        data = json.dumps(self.redact(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
        relative = f"artifacts/{digest}.json"
        target = self.directory / relative
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            target.write_text(data, encoding="utf-8", newline="\n")
        return relative

    def emit(self, event, *, call_id=None, parent=None, **details):
        if self.level == "off":
            return None
        self.sequence += 1
        row = dict(schema_version=1, run_id=self.run_id, sequence=self.sequence,
                   timestamp=utc_now(), turn_id=self.turn, speaker=self.speaker,
                   call_id=call_id, parent_event=parent, event=event, **details)
        with (self.directory / "trace.jsonl").open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(self.redact(row), ensure_ascii=False) + "\n")
            output.flush()
        return self.sequence


def prompt_diff(before, after):
    return "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                          fromfile="before", tofile="after", lineterm=""))


def read_events(path):
    """Only an incomplete final record is tolerated; corruption elsewhere is an error."""
    data = Path(path).read_bytes()
    lines = data.splitlines(keepends=True)
    events, warnings = [], []
    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("schema_version") != 1:
                raise ValueError("unsupported trace record")
            events.append(event)
        except (ValueError, UnicodeDecodeError) as exc:
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                warnings.append("Ignored incomplete final trace record")
            else:
                raise ValueError(f"Invalid trace record at line {index + 1}") from exc
    return events, warnings


def load_artifact(directory, reference):
    if reference is None:
        return None
    if not re.fullmatch(r"artifacts/[0-9a-f]{64}\.json", reference):
        raise ValueError("Invalid artifact reference")
    return json.loads((directory / reference).read_text(encoding="utf-8"))


def inspect_run(directory, *, speaker=None, turn=None, event_type=None, failed_only=False):
    """Compact evidence-linked report; repetition/praise flags are explicitly heuristic."""
    directory = Path(directory)
    events, warnings = read_events(directory / "trace.jsonl")
    failures = {e["call_id"] for e in events if e["event"] in ("call_error", "validation_failed")}
    selected = [e for e in events
                if (speaker is None or e["speaker"] == speaker)
                and (turn is None or e["turn_id"] == turn)
                and (event_type is None or e["event"] == event_type)
                and (not failed_only or e["call_id"] in failures and e["call_id"] is not None)]
    calls = [e for e in events if e["event"] == "call_started"]
    responses = [e for e in events if e["event"] == "call_completed"]
    lines = [f"Run: {directory.name}",
             f"Calls attempted: {len(calls)}; completed: {len(responses)}; failed calls: {len(failures)}",
             "Usage (reported by provider; missing usage is not zero):"]
    totals = {}
    for response in responses:
        for key, value in (response.get("usage") or {}).items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
    lines.append(json.dumps(totals, sort_keys=True))
    stops = [e for e in events if e["event"] == "run_stopped"]
    if stops:
        last = stops[-1]
        lines.append(f"Checkpoint totals (including any resumed history): {last['turns']} turns, "
                     f"{last['calls_used']} calls; stop={last['reason']}")
    lines.append("Per-character activity in this trace:")
    for name in sorted({e["speaker"] for e in selected if e.get("speaker")}):
        turns = [e["sequence"] for e in selected if e["speaker"] == name and e["event"] == "turn_committed"]
        changes = [e["sequence"] for e in selected if e["speaker"] == name and e["event"] == "prompt_changed"]
        lines.append(f"  {name}: committed turns at events {turns}; prompt updates at events {changes}")
    if len(responses) != sum(e.get("usage") is not None for e in responses):
        warnings.append("Some responses omitted token usage")
    pending_calls = {e["call_id"] for e in calls} - {
        e["call_id"] for e in events if e["event"] in ("call_completed", "call_error")}
    if pending_calls:
        warnings.append("Calls without a completion/error: " + ", ".join(sorted(pending_calls)))
    if not any(e["event"] == "run_stopped" for e in events):
        warnings.append("No run_stopped event; run may have been interrupted")
    lines.extend("Warning: " + warning for warning in warnings)
    lines.append("Timeline (evidence references are trace sequence numbers):")
    seen = {}
    for e in selected:
        if event_type is None and e["event"] in ("checkpoint_written", "transcript_written", "prompt_proposed"):
            continue
        tag = f"[event {e['sequence']}; turn {e['turn_id']}; {e['speaker'] or '-'}]"
        name = e["event"]
        detail = ""
        if name == "speaker_selected":
            detail = f"{e['mode']}; index {e['index_before']} -> {e['index_after']}; skipped {e['skipped']}"
        elif name == "update_decision":
            detail = f"{e['kind']}: {e['reason']}; count={e['count']}, interval={e['interval']}"
            interval = e["interval"]
            expected = bool(interval and e["count"] and e["count"] % interval == 0)
            if e["due"] != expected:
                detail += " [ANOMALY: schedule does not match interval]"
        elif name == "call_started":
            request = load_artifact(directory, e.get("request"))
            detail = f"{e['kind']} attempt {e['attempt']}; {e['call_id']}; request={e.get('request')}"
            if request and any(m.get("role") not in ("system", "user", "assistant")
                               or not isinstance(m.get("content"), str)
                               for m in request.get("messages", [])):
                detail += " [ANOMALY: invalid message role/content]"
        elif name in ("call_error", "validation_failed", "run_error"):
            detail = e.get("error", "")
        elif name == "prompt_changed":
            change = load_artifact(directory, e.get("change"))
            detail = f"{e['kind']}: {e['outcome']}; change={e.get('change')}"
            if change:
                detail += "\n" + change["diff"]
        elif name == "turn_committed":
            speech = load_artifact(directory, e.get("speech"))
            if speech:
                text = speech["accepted"]
                detail = text[:200] + ("..." if len(text) > 200 else "")
                normalized = " ".join(text.lower().split())
                if normalized in seen:
                    detail += f" [heuristic: exact repetition of event {seen[normalized]}]"
                seen[normalized] = e["sequence"]
                if re.search(r"\b(fantastic|wonderful|great point|absolutely right)\b", text, re.I):
                    detail += " [heuristic: praise language; review in context]"
        elif name == "run_stopped":
            detail = e["reason"]
        else:
            detail = ", ".join(f"{k}={e[k]}" for k in ("kind", "phase", "path", "status") if k in e)
        lines.append(f"{tag} {name}: {detail}")
    lines.append("Argument resolution and semantic novelty are not evaluated by this report.")
    return "\n".join(lines) + "\n"
