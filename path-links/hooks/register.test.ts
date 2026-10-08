import { expect, mock, test } from 'claude-code/testing'

const FILES = new Set(['/repo/src/main.cpp', '/repo/README.md', '/home/me/notes.txt', '/repo/my file#1.png'])

const draw = async ($: Parameters<Parameters<typeof test>[1]>[0], on: Parameters<Parameters<typeof test>[1]>[1], text: string) => {
  mock.env(on, { HOME: '/home/me' })
  on('session.cwd', () => ({ value: '/repo' }))
  on('fs.exists', (_$, e) => ({ value: FILES.has(e.path) }))
  let drawn = ''
  on('ui.render', { component: 'AssistantMessage' }, (hook$, e) => {
    drawn = e.props.text
    return hook$.ui.resolve(e).Text({ children: drawn })
  })
  await $.ui.render({
    surface: 'terminal',
    component: 'AssistantMessage',
    requestId: 'msg-1',
    props: { text, isFirstOfReply: true },
  })
  return drawn
}

test('links existing relative, absolute and ~ paths', async ($, on) => {
  const drawn = await draw($, on, 'See src/main.cpp:42, /repo/README.md and ~/notes.txt.')
  expect(drawn).toBe(
    'See [src/main.cpp:42](file:///repo/src/main.cpp), [/repo/README.md](file:///repo/README.md) and [~/notes.txt](file:///home/me/notes.txt).',
  )
})

test('links a path in inline code, keeping the code span', async ($, on) => {
  const drawn = await draw($, on, 'Edit `src/main.cpp` now')
  expect(drawn).toBe('Edit [`src/main.cpp`](file:///repo/src/main.cpp) now')
})

test('leaves missing paths, fences, links and URLs alone', async ($, on) => {
  const text = [
    'Missing: src/nope.cpp, e.g. this.',
    '[README](README.md) and https://example.com/src/main.cpp',
    '```',
    'src/main.cpp',
    '```',
  ].join('\n')
  expect(await draw($, on, text)).toBe(text)
})

test('percent-encodes spaces and # in the href', async ($, on) => {
  const drawn = await draw($, on, 'Open `my file#1.png`')
  expect(drawn).toBe('Open [`my file#1.png`](file:///repo/my%20file%231.png)')
})
