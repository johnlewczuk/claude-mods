export type Segment =
  | { kind: 'prose'; text: string }
  | { kind: 'code'; source: string; language?: string }

// A fence opens at up to three spaces of indent with ``` or ~~~ (3+), and
// closes on a line of the same character at least as long. An unclosed fence
// (a reply still streaming) runs to the end of the text.
const OPEN = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/

export function split(text: string): Segment[] {
  const segments: Segment[] = []
  const lines = text.split('\n')
  let prose: string[] = []

  const flushProse = () => {
    const joined = prose.join('\n')
    if (joined.trim() !== '') {
      segments.push({ kind: 'prose', text: joined.replace(/^\n+|\n+$/g, '') })
    }
    prose = []
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i++] ?? ''
    const open = OPEN.exec(line)
    if (!open) {
      prose.push(line)
      continue
    }

    const fence = open[1] ?? '```'
    const close = new RegExp(`^ {0,3}${fence[0] === '`' ? '`' : '~'}{${fence.length},}\\s*$`)
    const body: string[] = []
    while (i < lines.length) {
      const inner = lines[i++] ?? ''
      if (close.test(inner)) break
      body.push(inner)
    }

    flushProse()
    segments.push({ kind: 'code', source: body.join('\n'), language: open[2] || undefined })
  }

  flushProse()
  return segments
}

// The block as a Markdown fence again, longer than any backtick run inside it.
export function fenced(code: Extract<Segment, { kind: 'code' }>): string {
  const longest = Math.max(2, ...(code.source.match(/`+/g) ?? []).map(run => run.length))
  const fence = '`'.repeat(longest + 1)

  return `${fence}${code.language ?? ''}\n${code.source}\n${fence}`
}
