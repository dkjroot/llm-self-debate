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

Uses an OpenAI-compatible chat API so you need to have something to talk to, either an online service or a local model served through a compatible API. There are various ways to do that locally. I use KoboldCpp in the examples here, and I recommend it because it's very easy to use and I've found the compatibility and speed to be good. Other compatible local servers are available, though, so use whichever suits you.

Thanks to a beefy graphics card and lots of system RAM, I can run a 70B llama 3.3 8-bit gguf locally with reasonable performance (not real time, but fast enough to get results, and you do need a good model for this experiment to be worth doing at all).  I use a smaller model for speed while I'm working on the script, but the output and instruction following from smaller models is not good.

Some models perform well and others are a pain to use in this format.  I'm finding the pure llama 3 models work fine.

## Install it

You'll need Git and Python 3.10 or newer (Python 3.12 is a good choice), plus
something to run the model. The Python bit is the same whichever compatible
server you're using. There isn't a UI to install - it's just a script.

### Windows (PowerShell)

Install [Python](https://www.python.org/downloads/) and
[Git](https://git-scm.com/downloads), then open PowerShell:

```powershell
git clone https://github.com/dkjroot/llm-self-debate.git
cd llm-self-debate
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe debater.py --config config.koboldcpp.example.json --dry-run
```

If you've already cloned the repo, just open PowerShell in that folder and skip
the first two lines. If Windows doesn't recognise `py`, try `python` instead.
There's no need to activate the environment, so you don't have to fiddle with
PowerShell's script execution policy either.

### Linux (bash)

You'll need `git`, `python3` and Python's `venv` support. On Ubuntu or Debian you
can install them with `sudo apt install git python3 python3-venv python3-pip`.
Then:

```bash
git clone https://github.com/dkjroot/llm-self-debate.git
cd llm-self-debate
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python debater.py --config config.koboldcpp.example.json --dry-run
```

Again, skip the clone and `cd` if you're already in the repo. On other Linux
distributions, use your usual package manager to install Python and Git.
Create the virtual environment on the OS you're running it on; a Windows one
won't work on Linux, or vice versa.

The dry run checks the files and shows what would be sent to the model. It doesn't
connect to anything, so you can do this before you've even started KoboldCpp.
If it reports a problem, sort that out before asking the characters to talk.

## Start a local model (KoboldCpp example)

Here's the setup for the server used in these examples. If you've already got a
local server with an OpenAI-compatible chat API, you can use that instead. Copy
the example config and set `base_url`, `model` and `api_key_env` to suit that
server; its own documentation should tell you what it expects. The model name,
port and password options below are for the KoboldCpp example.

Get the Windows or Linux build for your machine from the
[official KoboldCpp releases](https://github.com/LostRuins/koboldcpp/releases).
Launch it, load your GGUF model, and wait for it to finish loading. On Linux you
may need to make the downloaded file executable first, e.g.
`chmod +x koboldcpp-linux-x64`, then run it with `./koboldcpp-linux-x64` (use the
name of the file you actually downloaded).

You should be able to open KoboldCpp's own chat page at
[http://127.0.0.1:5001](http://127.0.0.1:5001). Leave it running while you run the
debate script. If you've chosen a different port, use that instead of `5001`.

KoboldCpp's [OpenAI-compatible API](https://github.com/LostRuins/koboldcpp/wiki)
is already part of the server; you don't need a separate OpenAI account or an
OpenAI API key for a local model. Use `http://127.0.0.1:5001/v1/` as the base URL,
not the chat page URL or the native `/api` endpoint. The script adds
`chat/completions` to that URL itself.

`config.koboldcpp.example.json` is set up for this, with `model` set to `koboldcpp`.
KoboldCpp supplies the model you've loaded - that setting doesn't download a model.
The older `config.json` points at my own `WRAITH.local` machine, so use the example
unless that's the server you actually want!

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

initial_conversation.txt contains the conversation that has occurred to date.  It's a good way to set an initial tone for the conversation.  You can also use this as a way to edit the conversation the characters have had so far - copy a run's conversation.txt over initial_conversation.txt, edit anything you want to edit, then run the script again.

It's useful to have some starting point conversations prepared - keep your own copies, then copy whichever one you want to initial_conversation.txt before starting a fresh debate.

The settings in the config files should be mostly self-explanatory. The following fields do the following things:

- update_dynamic_character_prompt_every_N_statements - how many times should a specific character speak before the dynamic (aka variable) part of their character prompt is updated?
- new_dynamic_scenario_prompt_every_N_statements - how many times should any character speak before the dynamic part of the scenario prompt is updated?
- print_new_dynamic_prompts - if set true, new dynamic prompts will be printed to the console (but not to the file) - useful if you want to see how well the dynamic feature is working.

Once you run the script, the characters will debate until they reach the turn or API-call limit, or you stop them with Ctrl+C. The conversation is written to the console and also to runs/<run-id>/conversation.txt. That folder also contains the evolving prompts and diagnostic logs, which are useful when you're trying to work out why they've all started agreeing again.

All the conversation.txt files follow the same format - character name colon "line", e.g. Ted: "Let's get started!".  That way you can use a run's conversation.txt as initial_conversation.txt to carry on (or edit and carry on) a previous debate. That starts from the authored prompts again; use a checkpoint if you want to keep the characters' evolved prompts as well.

## Run a debate

Start with a short one to make sure everything is talking to everything else.
From the repository folder, with KoboldCpp running:

**Windows:**

```powershell
.\.venv\Scripts\python.exe debater.py --config config.koboldcpp.example.json --max-turns 6 --max-calls 12
```

**Linux:**

```bash
.venv/bin/python debater.py --config config.koboldcpp.example.json --max-turns 6 --max-calls 12
```

You'll see the characters' replies as they come back. There may be a fair wait
between them, depending on the model and your hardware. Without those two limit
options, the example allows 20 new dialogue turns and up to 40 API calls. Updating
a character's prompt or the scenario also takes a call.

The KoboldCpp example waits up to 600 seconds for a response and doesn't retry a
failed request automatically. A big local model can be slow, and I'd rather find
out what's wrong than ask it to generate the same thing twice. You can change
`timeout` and `max_retries` in the config if you want different behaviour.

### A password, or a model running on another computer

If you set a password in KoboldCpp (the `--password` option), that's the key you
need here. Set it in the terminal you're going to run the debate from.

**Windows:**

```powershell
$env:DEBATE_API_KEY = [Net.NetworkCredential]::new('', (Read-Host 'KoboldCpp password' -AsSecureString)).Password
```

**Linux:**

```bash
read -rsp 'KoboldCpp password: ' DEBATE_API_KEY; echo
export DEBATE_API_KEY
```

Leave it unset if you haven't given KoboldCpp a password. The script supplies a
dummy key for the SDK in that case. Don't put a real password in a tracked JSON
file; `.env` files aren't loaded automatically either.

For a server elsewhere on your local network, set its address before running the
same command. For example:

**Windows:**

```powershell
$env:DEBATE_BASE_URL = 'http://WRAITH.local:5001/v1/'
```

**Linux:**

```bash
export DEBATE_BASE_URL='http://WRAITH.local:5001/v1/'
```

Use your own server's `.local` name or private IP address and port. KoboldCpp must
be listening on that network interface, and its port needs to be reachable from
the machine running this script. If you'd rather keep those settings in a file,
copy the example to `config.koboldcpp.local.json`, edit it and pass that filename
to `--config`. Files named `config.*.local.json` are ignored by Git.

### If it doesn't talk back

- **Connection refused:** check KoboldCpp is running and the model has finished
  loading. Check the hostname and port, especially if it's on another computer.
- **401/403:** check `DEBATE_API_KEY` matches the password on that server.
- **404:** check the base URL ends in `/v1/`; don't append `chat/completions` yourself.
- **Timeout:** try a smaller model or increase `timeout` in your config. After a
  timeout, check the server has finished its earlier request before trying again.
- **Odd role tags or gibberish:** check KoboldCpp's chat template/Chat Completions
  adapter matches your model. A model answering nicely in its own chat window
  doesn't necessarily mean the API is using the right format.
- **Losing track of earlier arguments:** each call includes the conversation so
  far, so give KoboldCpp enough context for both that and the next reply. Start
  with short runs; the server's context limit still applies.

Environment settings override file settings for a fresh run. If you're switching
back from another provider, clear `DEBATE_MODEL` and `DEBATE_BASE_URL` so an old
setting doesn't quietly win over the KoboldCpp example. In PowerShell, use
`Remove-Item Env:DEBATE_MODEL, Env:DEBATE_BASE_URL -ErrorAction SilentlyContinue`;
in bash, use `unset DEBATE_MODEL DEBATE_BASE_URL`.

### Gemini

For Gemini, use the supplied secret-free example. Choose a model ID available to
your account; the example deliberately leaves `model` empty rather than assuming
which model your account can use:

```powershell
$env:DEBATE_MODEL = '<YOUR_AVAILABLE_GEMINI_MODEL_ID>'
$env:GEMINI_API_KEY = [Net.NetworkCredential]::new('', (Read-Host 'Gemini API key' -AsSecureString)).Password
.\.venv\Scripts\python.exe debater.py --config config.gemini.example.json --dry-run
.\.venv\Scripts\python.exe debater.py --config config.gemini.example.json --max-turns 4 --max-calls 8
```

On Linux:

```bash
export DEBATE_MODEL='<YOUR_AVAILABLE_GEMINI_MODEL_ID>'
read -rsp 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
.venv/bin/python debater.py --config config.gemini.example.json --dry-run
.venv/bin/python debater.py --config config.gemini.example.json --max-turns 4 --max-calls 8
```

The run command sends the prompts and transcript to Google and
uses that project's API quota/billing. The example requests scenario updates every
two new dialogue turns; four turns normally exercise all three call paths with the
supplied roster and schedule.

`DEBATE_MODEL` and `DEBATE_BASE_URL` override file settings for fresh runs.
`api_key_env` selects the exact credential variable (Gemini example: `GEMINI_API_KEY`).
There is no provider fallback. `token_parameter` can be `max_tokens` (default) or
`max_completion_tokens` for compatible servers that need it. Adjust the output-token
budget for your model; truncated or empty thinking-model output may need a larger
budget. Check that your chosen service and model accept those settings.

## Inputs and update policy

- `names.txt`: comma-separated unique character names; at least two are required.
- `<Name>_prompt.json`: `fixed_prompt` and evolving `variable_prompt` strings.
- `speaker_order.txt`: optional initial sequence (the file may be empty), followed by
  seeded random selection. Consecutive turns by the same character are skipped.
- `system_prompt.json`: shared `rules`, `scenario_fixed`, and `scenario_variable`.
- `initial_conversation.txt`: seed conversation in `Name: "speech"` format. Multiline
  speech is joined with spaces. An empty starting conversation is allowed.

Character updates run **before** every Nth prospective speech by that character,
including their seed speeches in the count.
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

On Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use fake clients and the actual SDK, including a small local HTTP server
that checks the KoboldCpp-style requests and password handling. No model is needed.
They cover scheduling, all request paths, invalid/empty responses, budgets/retries,
redaction, trace inspection, checkpoint continuation, and passive tracing. These tests
don't tell you whether the characters are making good arguments. You'll still
have to read what they say!

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
.\.venv\Scripts\python.exe debater.py inspect runs/RUN_ID
.\.venv\Scripts\python.exe debater.py inspect runs/RUN_ID --speaker Violet --event prompt_changed
.\.venv\Scripts\python.exe debater.py inspect runs/RUN_ID --turn 3
.\.venv\Scripts\python.exe debater.py inspect runs/RUN_ID --failed-only
```

On Linux the options are the same, just use the other Python path:

```bash
.venv/bin/python debater.py inspect runs/RUN_ID
.venv/bin/python debater.py inspect runs/RUN_ID --speaker Violet --event prompt_changed
```

Replace `RUN_ID` with the actual folder name printed at the end of the run.
Quote a path if it contains spaces. Trace sequence numbers link report findings to
raw events, and artifact paths link to complete local evidence. Truncated final JSONL
records are tolerated; corruption in earlier records is reported. Heuristic flags
just point out things you might want to look at; they don't tell you whether
the debate is any good.

Resume from a checkpoint, increasing cumulative limits if necessary:

```powershell
.\.venv\Scripts\python.exe debater.py --resume runs/RUN_ID/checkpoint.json --max-turns 12 --max-calls 30
```

Or on Linux:

```bash
.venv/bin/python debater.py --resume runs/RUN_ID/checkpoint.json --max-turns 12 --max-calls 30
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
