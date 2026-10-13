# claude-code-autonudge

Reference implementation of a Claude Code plugin. When the session sits idle for a minute, it asks [jev](https://typesafe.ai) whether the agent stopped short of its goal. If so, it sends a fixed message telling it to keep going.

The goal is the first user message in the session transcript (`~/.claude/projects/<cwd>/<session>.jsonl`). jev gets the goal plus the tail of the conversation (~30k tokens) and answers yes/no.

## Install

```
/plugin marketplace add franciscocarloserra/claude-code-autonudge
/plugin install autonudge@claude-code-autonudge
```

Then `/autonudge` toggles it for the session.

## Config

Constants at the top of `hooks/register.ts`: idle time, threshold, max nudges in a row (reset when you type), and the nudge text.

Needs `TYPESAFE_API_KEY` in `~/.secrets.sh`. Main session only, not subagents. Reads at most the first 2 MB of the transcript to find the goal.

## Codex

`codex/autonudge.py` does the same for Codex CLI. Codex has no way to inject a message into a running TUI, so it hooks `notify` (runs after each turn) and sends the nudge with `codex exec resume <thread>`, which runs headless: the turn lands in the session's transcript, but an open TUI won't show it live.

In `~/.codex/config.toml`:

```
notify = ["python3", "/path/to/codex/autonudge.py"]
```

`notify` takes a single command; if you already use one, call this script from it with the same JSON argument. Same constants at the top of the script; nudge counts per thread in `~/.codex/autonudge/`.
