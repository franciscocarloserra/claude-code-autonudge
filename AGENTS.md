# AGENTS.md

Everything is in `hooks/register.ts`, constants at the top. Reference implementation, not tuned.

- `turn.complete` (main session only, `!e.agentId`) arms `$.clock.after(IDLE_MS)`; `prompt.submit` cancels it. A typed prompt resets the nudge count; a plugin prompt (`origin.kind === 'plugin'`) does not, so MAX_NUDGES caps a self-feeding loop.
- Goal = first non-meta user row in `~/.claude/projects/<root slug>/<session id>.jsonl` whose text does not start with `<` (skips command caveats/`/clear`).
- jev: one `noul` over `GOAL + tail of $.session.messages()` (last TAIL_CHARS chars, ~30k tokens). Key read via `bash -c 'source ~/.secrets.sh'`.
- Nudge sent with `$.prompt.submit` (framed as from the plugin, not `asUser`).

## Status
- Typechecks. Headless test (`claude -p` stream-json, IDLE_MS 5 s): `/autonudge on` works; no nudge fired, but the test prompt told the agent to stop, so jev saying "not stuck" is plausible. Firing path (timer → jev → submit) not verified end to end yet.
