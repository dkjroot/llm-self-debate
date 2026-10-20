# llm-self-debate

**[Support my work on Buy Me a Coffee](https://buymeacoffee.com/dkjroot)**

### Free to use. Please help keep it that way.

I develop this project to be freely available to everyone, supported, if at all,
by voluntary contributions. I do not want other people to profit from my work
by selling copies, putting it behind a paywall, or building a paid application
or hosted service around it. I ask you to respect that intention: please keep
this work freely available, credit its origins, and direct people to
[my official GitHub repository](https://github.com/dkjroot/llm-self-debate) for the software.

If you want to help fund my development, please contribute **directly to me**
through [Buy Me a Coffee](https://buymeacoffee.com/dkjroot). Paying a distributor
or hosting provider does not fund my work unless I explicitly say otherwise.
There is no obligation to contribute.

**This is a personal request, not an additional license restriction.** The
[GNU General Public License v3.0](LICENSE) permits commercial use and
redistribution, including forks, subject to its terms. Those legal permissions
remain unchanged by this request. See [licensing details](LICENSING.md) and
[third-party credits](THIRD_PARTY_NOTICES.md).

A python project where multiple LLM personalities debate each other.

The idea is quite simple - set up multiple system prompts for different characters and alternate between them, building up a conversation about a subject that you choose.  I want to make it so that you can intervene, and since I can't be bothered to make a UI that'll be by stopping the script and editing the text files!  

I think the tricky part will be getting something better than a circular conversation that never goes anywhere below the surface of the topic, because LLMs are very good at pretending they're not superficial, but they are basically pretty superficial.  Anyway, lets see how good we can make it...

# Requirements

Uses the OpenAI API so you need to have something to talk to, either an online service or run a local model in something like koboldcpp.  I like koboldcpp, I find it simple to use, and (thanks to beefy graphics card and lots of system RAM) I can run a 70B llama 3.3 8-bit gguf locally with reasonable performance (not real time, but fast enough to get results, and you do need a good model for this experiment to be worth doing at all).  I use a smaller model for speed while I'm working on the script, but the output and instruction following from smaller models is not good.

Some models perform well and others are a pain to use in this format.  I'm finding the pure llama 3 models work fine.

## Setup

Use Python 3.10 or newer. From the repository directory in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe debater.py --dry-run
```

The dry run validates files and shows redacted configuration plus representative
requests for all three generation paths. It imports no SDK, creates no run files,
and makes no API calls. It does not test credentials or model availability.

# Goals

- [x] Alternate between multiple viewpoint characters.
- [x] Multiple characters each have their own personalities and agendas.
- [x] The conversation sent to the API uses 'assistant' for the current character, and 'user' for the other characters, so that the LLM thinks its own character is the only LLM in the conversation.
- [x] Have the LLM update the character system prompts as the conversation progresses.
- [x] Have the LLM update the scenario system prompt as the conversation progresses.

# How does it work?

names.txt contains a comma-separated list of the names of the characters in your debate.  e.g. "May,Ted,Pete,Ben,Violet"

Each character needs a Name_prompt.json, which is that character's initial system prompt.  e.g. May_prompt.json.  This contains two strings, 'fixed_prompt' that will always be used, and 'variable_prompt' that will be used as the initial dynamic prompt, but the LLM will update as the conversation progresses (this is an attempt to introduce some variance and freshness into the debate, otherwise the LLM tends to go round in circles). 

speaker_order.txt can be used to force a specific order for the speakers. When the script comes to the end of this list, it will choose a speaker at random. In both modes, it will avoid using the same speaker twice in a row.

system_prompt.json contains three strings: 'rules' where you can tune the behaviour of the LLM, 'scenario_fixed' where you can define non-variable parts of the debate scenario, and 'scenario_variable' which is an initial value for the dynamic part of the scenario that the LLM will be allowed to update as the debate progresses.

initial_conversation.txt contains the conversation that has occurred to date.  It's a good way to set an initial tone for the conversation.  You can also use this as a way to edit the conversation the characters have had so far - copy the conversation_(datetime).txt over initial_conversation.txt, edit anything you want to edit, then run the script again.

It's useful to have some starting point conversations prepared, and that's what prep_initial_conversation*.txt represent - copy one of those to initial_conversation.txt and start the script to begin a fresh debate.

config.json should be mostly self-explanatory.  The following fields do the following things:
- update_dynamic_character_prompt_every_N_statements - how many times should a specific character speak before the dynamic (aka variable) part of their character prompt is updated?
- new_dynamic_scenario_prompt_every_N_statements - how many times should any character speak before the dynamic part of the scenario prompt is updated?
- print_new_dynamic_prompts - if set true, new dynamic prompts will be printed to the console (but not to the file) - useful if you want to see how well the dynamic feature is working.

Once you run the script, the characters will debate until you stop the script with ctrl+c.  The conversation will be written to the console and also to conversation_(datetime).txt

All the conversation.txt files follow the same format - character name colon "line", e.g. Ted: "Let's get started!".  That way you can always use a conversation_(datetime).txt as initial_conversation.txt to carry on (or edit and carry on) a previous debate.

## Local models and Gemini

`config.json` contains config to use a local KoboldCpp endpoint. It defaults to 20
new dialogue turns and at most 40 API attempts, including prompt updates and retries.
Start it with:

```powershell
.\.venv\Scripts\python.exe debater.py --max-turns 6 --max-calls 12
```

Set `DEBATE_API_KEY` if your local server requires authentication. Without it, local
endpoints use a dummy key (`local-no-key`).

For Gemini, use the supplied secret-free example. Choose a model ID available to
your account; the example deliberately leaves `model` empty rather than assuming
which model your account can use:

```powershell
$env:DEBATE_MODEL = '<YOUR_AVAILABLE_GEMINI_MODEL_ID>'
$env:GEMINI_API_KEY = [Net.NetworkCredential]::new('', (Read-Host 'Gemini API key' -AsSecureString)).Password
.\.venv\Scripts\python.exe debater.py --config config.gemini.example.json --dry-run
.\.venv\Scripts\python.exe debater.py --config config.gemini.example.json --max-turns 4 --max-calls 8
```

The second command after the dry run sends the prompts and transcript to Google and
uses that project's API quota/billing. The example requests scenario updates every
two new dialogue turns; four turns normally exercise all three call paths with the
supplied roster and schedule.

`DEBATE_MODEL` and `DEBATE_BASE_URL` override file settings for fresh runs.
`api_key_env` selects the exact credential variable (Gemini example: `GEMINI_API_KEY`).
There is no provider fallback. `token_parameter` can be `max_tokens` (default) or
`max_completion_tokens` for compatible servers that need it. Adjust the output-token
budget for your model; truncated or empty thinking-model output may need a larger
budget. Sampling support and account/model availability still need a live check.

## Inputs and update policy

- `names.txt`: comma-separated unique character names; at least two are required.
- `<Name>_prompt.json`: `fixed_prompt` and evolving `variable_prompt` strings.
- `speaker_order.txt`: optional initial sequence (the file may be empty), followed by
  seeded random selection. Consecutive turns by the same character are skipped.
- `system_prompt.json`: shared `rules`, `scenario_fixed`, and `scenario_variable`.
- `initial_conversation.txt`: seed conversation in `Name: "speech"` format. Multiline
  speech is joined with spaces. An empty starting conversation is allowed.

Character updates run **before** every Nth prospective speech by that character,
including their seed speeches in the count (preserving the original convention).
Scenario updates run **after** every Nth newly generated dialogue turn, excluding
seed speeches. Set either interval to zero to disable it, or use
`--no-character-updates` / `--no-scenario-updates` for a fresh comparison run.
`--seed` controls speaker selection, not nondeterministic model sampling.

`max_turns` and `max_calls` are hard application-level count limits, not dollar caps.
Retries count as separate calls. SDK retries are disabled; `max_retries` controls
logged application retries for connection/timeouts, 408/409/429, and server errors.
`retry_delay` and `timeout` are seconds. Blank/absent text and empty cleaned speech
stop the run without appending a duplicate turn. Errors preserve a checkpoint.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use fake clients plus the actual pinned SDK with an offline HTTP transport.
They cover scheduling, all request paths, invalid/empty responses, budgets/retries,
redaction, trace inspection, checkpoint continuation, and passive tracing. These tests
do not establish factual accuracy or improved character arguments. See `TODO.md`
for completed first-pass work and remaining behavioral experiments.

## Trace, inspection, and resumption

Each live run creates a unique directory under `runs/`:

- `conversation.txt`: readable conversation, including seed/inherited turns.
- `checkpoint.json`: evolved prompts, conversation, update phase, counters, schedule,
  RNG state, and configuration, written atomically after state transitions.
- `trace.jsonl`: flushed, append-only events with run/turn/call IDs and links.
- `artifacts/`: content-addressed payloads, including exact effective requests, raw
  responses, prompt proposals/diffs, and starting snapshots with source hashes.
- `report.txt`: compact timeline, per-character activity, usage, errors, prompt diffs,
  and evidence-linked heuristic flags for repeated speech or praise language.

Inspect locally without calling a model:

```powershell
.\.venv\Scripts\python.exe debater.py inspect runs/<RUN_ID>
.\.venv\Scripts\python.exe debater.py inspect runs/<RUN_ID> --speaker Violet --event prompt_changed
.\.venv\Scripts\python.exe debater.py inspect runs/<RUN_ID> --turn 3
.\.venv\Scripts\python.exe debater.py inspect runs/<RUN_ID> --failed-only
```

Quote a path if it contains spaces. Trace sequence numbers link report findings to
raw events, and artifact paths link to complete local evidence. Truncated final JSONL
records are tolerated; corruption in earlier records is reported. Heuristic flags
are prompts for review, not judgments of debate quality. Semantic argument tracking,
unresolved-issue reports, and faithful final argument maps remain future work.

Resume from a checkpoint, increasing cumulative limits if necessary:

```powershell
.\.venv\Scripts\python.exe debater.py --resume runs/<RUN_ID>/checkpoint.json --max-turns 12 --max-calls 30
```

A resume creates a new directory linked to its parent and preserves the endpoint,
model, update policy, RNG state, and pending phase from the checkpoint. It does not
reload authored inputs, file config, or endpoint/model environment overrides; it
still reads the credential from the named environment variable. Limits count all
new dialogue/calls across the original run and its resumptions, excluding seed turns.
A pending scenario update is completed before selecting another speaker. Never change
a checkpoint's model/endpoint just to bypass a configuration error; start a fresh run.

Ctrl+C saves state. A call interrupted in transport may already have been charged;
its reserved attempt remains counted, and resumption may issue that unfinished call
again. A checkpoint cannot guarantee exactly-once remote execution. Atomic checkpoint
replacement protects the last completed save; a hard process kill can lose work
since that save. The checkpoint is authoritative if transcript/report writing fails.

Tracing adds no model calls. `--trace-level metadata` omits content payload artifacts;
`--trace-level off` disables the trace/report. Both still save a transcript and full
checkpoint. Default `full` is recommended for investigation. Known configured keys
are redacted across artifacts, transcripts, and errors; avoid putting unrelated
secrets into debate content. Redacted content cannot be reconstructed on resume.
There is no automatic retention/deletion yet; keep or delete run directories locally
as needed. Generated runs are ignored by Git (use the default `runs/` output root).

# FAQ

Q: Why is this better than *other project*?
A: It probably isn't.  I just like to explore ideas myself.
