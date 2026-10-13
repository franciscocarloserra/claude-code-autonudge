import type { Register } from 'claude-code'

// Reference implementation. After the main session sits idle IDLE_MS, jev reads the goal
// (first user message in the transcript) plus the recent tail and judges whether the agent
// stopped short of it. If so, it sends NUDGE as a user turn, at most MAX_NUDGES in a row.
const IDLE_MS = 60_000
const TAIL_CHARS = 100_000 // ~30k tokens, jev's context minus goal and question
const THRESHOLD = 0.7
const MAX_NUDGES = 3
const NUDGE = 'Keep going toward the original goal. If you are blocked, say exactly what you need from me.'
const QUESTION = 'The agent went idle. Did it stop before reaching the goal, while it could still make progress on its own (not waiting on a real decision or input from the user, and not done)?'
const JEV_URL = 'https://api.typesafe.ai/v1/systemone'

let on_ = false
let nudges = 0
let timer: { cancel: () => void } | undefined

async function goal($: any): Promise<string> {
  const [id, root] = await Promise.all([$.session.id(), $.session.root()])
  const home = root.match(/^\/home\/[^/]+|^\/Users\/[^/]+/)?.[0] ?? '~'
  const path = `${home}/.claude/projects/${root.replace(/[^A-Za-z0-9]/g, '-')}/${id}.jsonl`
  const { stdout } = await $.process.run(['head', '-c', '2000000', path])
  for (const line of stdout.split('\n')) {
    try {
      const r = JSON.parse(line)
      if (r.type !== 'user' || r.isMeta) continue
      const c = r.message?.content
      const text = typeof c === 'string' ? c : Array.isArray(c) ? c.filter((b: any) => b.type === 'text').map((b: any) => b.text).join('\n') : ''
      if (text && !text.trimStart().startsWith('<')) return text
    } catch {}
  }
  return ''
}

async function check($: any) {
  timer = undefined
  if (!on_ || nudges >= MAX_NUDGES) return
  const rows = await $.session.messages()
  const tail = rows.map((m: any) => `${m.role}: ${m.text}` + m.toolUses.map((t: any) => `\n[${t.tool}] ${JSON.stringify(t.input).slice(0, 300)} -> ${String(t.text ?? '').slice(0, 300)}`).join('')).join('\n').slice(-TAIL_CHARS)
  const key = (await $.process.run(['bash', '-c', 'source ~/.secrets.sh && printf %s "$TYPESAFE_API_KEY"'])).stdout
  const res = await $.http.fetch(JEV_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ state: `GOAL:\n${(await goal($)).slice(0, 4000)}\n\nRECENT TRANSCRIPT:\n${tail}`, model: 'jev-latest', questions: { stuck: { type: 'noul', instructions: QUESTION } } }),
  })
  const p = JSON.parse(res.text)?.answers?.stuck?.noul
  if (typeof p !== 'number') return $.ui.toast(`autonudge: jev failed (${res.status})`)
  if (p < THRESHOLD) return
  nudges++
  await $.prompt.submit({ text: NUDGE })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'autonudge', description: 'Toggle: nudge the session when jev judges it stopped short of the goal' })
    return next(e)
  })

  on('command.run', { command: 'autonudge' }, async () => {
    on_ = !on_
    nudges = 0
    timer?.cancel()
    return { text: `autonudge ${on_ ? 'on' : 'off'}` }
  })

  on('prompt.submit', async ($, e, next) => {
    timer?.cancel()
    if (e.origin?.kind !== 'plugin') nudges = 0
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (on_ && !e.agentId) {
      timer?.cancel()
      timer = $.clock.after(IDLE_MS, () => void check($).catch(err => $.ui.toast(`autonudge: ${err}`)))
    }
    return next(e)
  })
}
