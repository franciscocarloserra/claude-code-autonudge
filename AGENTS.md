# AGENTS.md

Everything is in `hooks/register.ts`, constants at the top. Reference implementation, not tuned.

## Before installing (agents: do this first)
Before installing either connector, explain to the user in plain words, and wait for an explicit yes:
- What it does: after the session is idle IDLE time, it sends the goal (first user message) and the last ~30k tokens of the conversation to jev (api.typesafe.ai, external service), and may type NUDGE into the session as a new turn on its own.
- What it costs: one jev call per idle period; each nudge is a full model turn on the user's quota.
- When it stops: jev judges the goal done, or a budget runs out (constants below), or the user turns it off.
- How to revert. Claude Code: `/autonudge` again (off for this session); `/plugin uninstall autonudge@claude-code-autonudge` (or remove the `--plugin-dir`). Codex: remove the `notify` line from `~/.codex/config.toml` (or put back the previous one); per-thread state lives in `~/.codex/autonudge/`.

## Stop criteria and budget
Each idle check, before calling jev, the budget: BUDGET_NUDGES total nudges, BUDGET_MINUTES since `/autonudge` on, BUDGET_CONTEXT_TOKENS of context (`$.session.usage()`); any exceeded → off with a toast. Then jev answers two nouls in one call: `done` (≥ DONE_THRESHOLD → off, "goal done") and `stuck` (≥ THRESHOLD → nudge). MAX_NUDGES in a row pauses (not off) until the person types.

- `turn.complete` (main session only, `!e.agentId`) arms `$.clock.after(IDLE_MS)`; `prompt.submit` cancels it. A typed prompt resets the nudge count; a plugin prompt (`origin.kind === 'plugin'`) does not, so MAX_NUDGES caps a self-feeding loop.
- Goal = first non-meta user row in `~/.claude/projects/<root slug>/<session id>.jsonl` whose text does not start with `<` (skips command caveats/`/clear`).
- jev: one `noul` over `GOAL + tail of $.session.messages()` (last TAIL_CHARS chars, ~30k tokens). Key read via `bash -c 'source ~/.secrets.sh'`.
- Nudge sent with `$.prompt.submit` (framed as from the plugin, not `asUser`).

## Status
- Typechecks (also after stop/budget). The stop/budget path is not run yet. Headless test (`claude -p` stream-json, IDLE_MS 5 s): `/autonudge on` works; no nudge fired, but the test prompt told the agent to stop, so jev saying "not stuck" is plausible. Firing path (timer → jev → submit) not verified end to end yet.

## Codex connector (`codex/autonudge.py`)
- Codex `notify` → forks a detached `--watch` process; after IDLE_S, if the rollout mtime is unchanged, jev judges and `codex exec resume <thread-id> NUDGE` sends it (headless; not visible live in an open TUI).
- Goal = first `response_item` user message not starting with `<` or `/` in `~/.codex/sessions/*/*/*/rollout-*<thread>.jsonl`. Nudge turns are dropped from the tail; a turn whose input contains NUDGE keeps the count, any other resets it.
- Stop/budget: state per thread in `~/.codex/autonudge/<thread>.json` (`row`, `total`, `since`, `off`). `done` from jev or BUDGET_NUDGES/BUDGET_MINUTES set `off` for good; to re-arm a thread, move its file away. No context-token budget on this side.
- Tested: `read_rollout` + `jev` on a real rollout (p=0.73, before the `done` question was added). The notify → resume path is not tested. Not wired into `~/.codex/config.toml` (it already has tts-notify).
