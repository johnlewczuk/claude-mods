import { atom, memberOf, read, update } from 'claude-code'
import type { Register } from 'claude-code'

const DONE_AT = { plugin: 'reply-timestamp', key: 'doneAt' } as const
const doneAt = atom(DONE_AT, 0)

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many)

// As the built-in `done` time reads: "12:18 PM" today, "Monday 12:18 PM" this
// week, "Monday, Oct 20, 12:18 PM" before that.
export const formatDone = (ms: number, nowMs: number) => {
  const at = new Date(ms)
  const time = `${at.getHours() % 12 || 12}:${String(at.getMinutes()).padStart(2, '0')} ${at.getHours() < 12 ? 'AM' : 'PM'}`
  const midnight = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((midnight(new Date(nowMs)) - midnight(at)) / 86_400_000)
  if (days === 0) return time
  if (days > 0 && days < 7) return `${DAYS[at.getDay()]} ${time}`
  return `${DAYS[at.getDay()]}, ${MONTHS[at.getMonth()]} ${at.getDate()}, ${time}`
}

export const register: Register = on => {
  // A turn's duration row is stored as the turn ends; its id is the requestId it is drawn under.
  on('session.append', async ($, e, next) => {
    const stored = await next(e)
    if (e.agentId === undefined && e.message.type === 'system' && e.message.name === 'turn_duration') {
      const now = await $.clock.now()
      await update($, atom({ ...DONE_AT, id: stored.uuid }, 0), () => now)
    }
    return stored
  }).catch(($, e, next) => next(e))

  // While background work runs the built-in line reads "Waiting for … to finish"
  // and leaves its `done` time off: draw that line again with the time on it.
  on('ui.render', { component: 'TurnDuration' }, async ($, e, next) => {
    const waiting = e.props.waitingFor
    if (waiting === undefined) return next(e)
    const at = await read($, memberOf(doneAt, e))
    if (at === 0) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const agents = waiting.agents.length
    const workflows = waiting.workflows
    return (
      <Box flexDirection="column" width="100%">
        <Box flexDirection="row" marginTop={1} width="100%">
          <Box minWidth={2}>
            <Text dimColor>✻</Text>
          </Box>
          <Text dimColor>
            Waiting for
            {agents > 0 && (
              <Text dimColor>
                {' '}
                <Text bold dimColor>{agents}</Text>
                {` background ${plural(agents, 'agent', 'agents')}`}
              </Text>
            )}
            {agents > 0 && workflows > 0 && ' and'}
            {workflows > 0 && (
              <Text dimColor>
                {' '}
                <Text bold dimColor>{workflows}</Text>
                {` ${plural(workflows, 'dynamic workflow', 'dynamic workflows')}`}
              </Text>
            )}
            {` to finish · done ${formatDone(at, await $.clock.now())}`}
          </Text>
        </Box>
      </Box>
    )
  })
}
