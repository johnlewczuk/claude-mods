import { expect, test } from 'claude-code/testing'

import { fenced, split } from './split'

test('splits prose from fenced code, unclosed fence runs to the end', () => {
  const s = split('Run this:\n\n```bash\nls -la\ncd /tmp\n```\n\nThen:\n~~~\nmake\n')
  expect(s).toEqual([
    { kind: 'prose', text: 'Run this:' },
    { kind: 'code', source: 'ls -la\ncd /tmp', language: 'bash' },
    { kind: 'prose', text: 'Then:' },
    { kind: 'code', source: 'make\n', language: undefined },
  ])
})

const REPLY = {
  plugin: 'copy-code',
  component: 'AssistantMessage',
  surface: 'terminal',
  viewport: { columns: 100, rows: 40, isFullscreen: true },
} as const

test('a code block gets a copy button that copies its source', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  const copied: string[] = []
  on('ui.copy', (_, e) => {
    copied.push(e.text)
    return { value: { isCopied: true } }
  })
  on('ui.toast', () => ({ value: {} }))

  const ui = await $.ui.mount({
    ...REPLY,
    requestId: 'm1',
    props: { text: 'Run:\n```sh\necho hi\n```', isFirstOfReply: true },
  })
  expect((await ui.find({ type: 'Markdown', text: /echo hi/ }))?.text).toBe('```sh\necho hi\n```')
  expect((await ui.find({ type: 'Button', key: 'copy-1' }))?.text).toBe(' copy ')
  await ui.press({ key: 'copy-1' })
  expect(copied).toEqual(['echo hi'])
  await ui.unmount()
})

test('replies without code, or outside fullscreen, are left to the engine', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })

  for (const [text, isFullscreen] of [['No code here.', true], ['```sh\nls\n```', false]] as const) {
    const ui = await $.ui.mount({
      ...REPLY,
      viewport: { ...REPLY.viewport, isFullscreen },
      props: { text, isFirstOfReply: true },
    })
    expect((await ui.find({ type: 'Text', text: /engine/ }))?.text).toBe('engine')
    await ui.unmount()
  }
})

test('a block holding a fence is re-fenced longer', () => {
  expect(fenced({ kind: 'code', source: 'a\n```\nb', language: 'md' })).toBe('````md\na\n```\nb\n````')
})
