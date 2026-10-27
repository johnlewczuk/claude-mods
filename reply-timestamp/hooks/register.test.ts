import { expect, mock, test } from 'claude-code/testing'
import { formatDone } from './register'

const AT = new Date(2026, 9, 27, 12, 18, 19).getTime()
const DAY = 86_400_000

const durationRow = (uuid: string) => ({
  message: { type: 'system' as const, name: 'turn_duration', content: [{ type: 'text' as const, text: 'turn duration' }] },
  door: 'notice' as const,
  origin: { kind: 'engine' as const },
  uuid,
})

const line = (requestId: string, waitingFor?: { agents: { id: string; agentType: string }[]; workflows: number }) => ({
  plugin: 'reply-timestamp',
  surface: 'terminal' as const,
  component: 'TurnDuration' as const,
  requestId,
  props: { word: 'Baked', durationMs: 1000, ...(waitingFor ? { waitingFor } : {}) },
})

const AGENT = { id: 'a1', agentType: 'general-purpose' }

test('formats the time as the built-in line does', () => {
  expect(formatDone(AT, AT)).toBe('12:18 PM')
  expect(formatDone(AT - 12 * 3_600_000 - 18 * 60_000, AT)).toBe('12:00 AM')
  expect(formatDone(AT, AT + DAY)).toBe('Tuesday 12:18 PM')
  expect(formatDone(AT, AT + 8 * DAY)).toBe('Tuesday, Oct 27, 12:18 PM')
})

test('adds the reply time to a line waiting on background agents', async ($, on) => {
  mock.clock(on, { now: AT })
  mock.session(on)
  await $.session.append(durationRow('row-1'))
  const ui = await $.ui.mount(line('row-1', { agents: [AGENT, { ...AGENT, id: 'a2' }], workflows: 0 }))
  expect((await ui.find({ type: 'Text', text: /to finish/ }))?.text).toBe(
    'Waiting for 2 background agents to finish · done 12:18 PM',
  )
})

test('names agents and workflows together', async ($, on) => {
  mock.clock(on, { now: AT })
  mock.session(on)
  await $.session.append(durationRow('row-1'))
  const ui = await $.ui.mount(line('row-1', { agents: [AGENT], workflows: 1 }))
  expect((await ui.find({ type: 'Text', text: /to finish/ }))?.text).toBe(
    'Waiting for 1 background agent and 1 dynamic workflow to finish · done 12:18 PM',
  )
})

test('leaves the built-in line alone when it already has its time', async ($, on) => {
  mock.clock(on, { now: AT })
  mock.session(on)
  on('ui.render', { component: 'TurnDuration' }, () => ({ type: 'engine', ref: 0 }))
  await $.session.append(durationRow('row-1'))
  const ui = await $.ui.mount(line('row-1'))
  expect(await ui.drawn()).toEqual({ type: 'engine', ref: 0 })
})

test('leaves a waiting line alone when its row time is unknown', async ($, on) => {
  mock.clock(on, { now: AT })
  on('ui.render', { component: 'TurnDuration' }, () => ({ type: 'engine', ref: 0 }))
  const ui = await $.ui.mount(line('resumed-row', { agents: [AGENT], workflows: 0 }))
  expect(await ui.drawn()).toEqual({ type: 'engine', ref: 0 })
})
