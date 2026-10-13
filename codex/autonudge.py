#!/usr/bin/env python3
# Codex connector for autonudge (reference implementation).
# Set as Codex `notify`; on agent-turn-complete it forks a watcher that waits IDLE_S,
# checks the rollout did not change, asks jev if the agent stopped short of the goal
# (first user message), and if so sends NUDGE with `codex exec resume <thread>`.
# Stops itself for the thread when jev judges the goal done or a budget runs out.
import glob, json, os, subprocess, sys, time, urllib.request

IDLE_S = 60
TAIL_CHARS = 100_000  # ~30k tokens
THRESHOLD = 0.7
DONE_THRESHOLD = 0.8
MAX_NUDGES = 3  # in a row; reset by any turn that is not a nudge
BUDGET_NUDGES = 10  # total per thread
BUDGET_MINUTES = 120  # since the first watch of the thread
NUDGE = "Keep going toward the original goal. If you are blocked, say exactly what you need from me."
QUESTION = ("The agent went idle. Did it stop before reaching the goal, while it could still make progress "
            "on its own (not waiting on a real decision or input from the user, and not done)?")
DONE_Q = "Is the goal fully achieved, with nothing left for the agent to do?"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
STATE_DIR = os.path.expanduser("~/.codex/autonudge")


def texts(content):
    return "\n".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def read_rollout(path):
    goal, lines = "", []
    for l in open(path):
        p = json.loads(l).get("payload") or {}
        if p.get("type") == "message" and p.get("role") in ("user", "assistant"):
            t = texts(p.get("content"))
            if p["role"] == "user" and NUDGE in t:
                continue
            if not goal and p["role"] == "user" and t and not t.lstrip().startswith(("<", "/")):
                goal = t
            lines.append(f"{p['role']}: {t}")
        elif p.get("type") in ("function_call", "custom_tool_call"):
            lines.append(f"[{p.get('name')}] {str(p.get('arguments') or p.get('input'))[:300]}")
        elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
            lines.append(f"-> {str(p.get('output'))[:300]}")
    return goal, "\n".join(lines)[-TAIL_CHARS:]


def jev(state):
    key = subprocess.run(["bash", "-c", 'source ~/.secrets.sh && printf %s "$TYPESAFE_API_KEY"'],
                         capture_output=True, text=True).stdout
    body = {"state": state, "model": "jev-latest", "questions": {
        "done": {"type": "noul", "instructions": DONE_Q}, "stuck": {"type": "noul", "instructions": QUESTION}}}
    req = urllib.request.Request(JEV_URL, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    a = json.load(urllib.request.urlopen(req, timeout=30))["answers"]
    return a["done"]["noul"], a["stuck"]["noul"]


def watch(thread, cwd, from_nudge):
    os.makedirs(STATE_DIR, exist_ok=True)
    state_file = f"{STATE_DIR}/{thread}.json"
    st = json.load(open(state_file)) if os.path.exists(state_file) else {"row": 0, "total": 0, "since": time.time()}
    save = lambda: json.dump(st, open(state_file, "w"))
    if not from_nudge:
        st["row"] = 0
    save()
    path = (glob.glob(os.path.expanduser(f"~/.codex/sessions/*/*/*/rollout-*{thread}.jsonl")) or [None])[0]
    if not path or st.get("off") or st["row"] >= MAX_NUDGES:
        return
    if st["total"] >= BUDGET_NUDGES or time.time() - st["since"] > BUDGET_MINUTES * 60:
        st["off"] = "budget"
        return save()
    mtime = os.path.getmtime(path)
    time.sleep(IDLE_S)
    if os.path.getmtime(path) != mtime:
        return  # a new turn started
    goal, tail = read_rollout(path)
    done, stuck = jev(f"GOAL:\n{goal[:4000]}\n\nRECENT TRANSCRIPT:\n{tail}")
    if done >= DONE_THRESHOLD:
        st["off"] = "goal done"
        return save()
    if stuck < THRESHOLD:
        return
    st["row"] += 1
    st["total"] += 1
    save()
    subprocess.run(["codex", "exec", "resume", thread, NUDGE], cwd=cwd or None,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--watch":
        return watch(sys.argv[2], sys.argv[3], sys.argv[4] == "1")
    ev = json.loads(sys.argv[-1])
    if ev.get("type") != "agent-turn-complete":
        return
    from_nudge = any(NUDGE in m for m in ev.get("input-messages") or [])
    subprocess.Popen([sys.executable, __file__, "--watch", ev["thread-id"], ev.get("cwd", ""), "1" if from_nudge else "0"],
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
