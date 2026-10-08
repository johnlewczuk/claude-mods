import type { Register } from 'claude-code'

// One markdown token per match: a fence line, an inline code span, an existing
// link, a URL, or a word that may be a path (optionally with :line[:col]).
const TOKEN =
  /(^\s*(?:```|~~~).*$)|(`[^`\n]+`)|(\[[^\]\n]*\]\([^)\n]*\))|(\b[a-z][\w+.-]*:\/\/\S+)|((?<![\w/.~-])(?:~|\.{1,2})?\/?[\w.+@-]+(?:\/[\w.+@-]+)*\/?(?::\d+(?::\d+)?)?)/gim

const LOCATION = /^(.*?)(:\d+(?::\d+)?)?$/

// Paths seen to exist; a miss is checked again next draw, as the file may appear.
const seen = new Set<string>()

const looksLikePath = (word: string) =>
  word.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(word)

const toHref = (absolute: string) =>
  'file://' + encodeURI(absolute).replace(/#/g, '%23').replace(/\?/g, '%3F')

const resolve = (path: string, cwd: string, home: string) => {
  if (path === '~' || path.startsWith('~/')) return home + path.slice(1)
  if (path.startsWith('/')) return path
  return `${cwd}/${path}`
}

export const register: Register = on => {
  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    try {
      const cwd = await $.session.cwd()
      const home = (await $.env.get('HOME')) ?? ''

      // The href for a word naming an existing path; a :line suffix stays in the text only.
      const hrefFor = async (word: string) => {
        const [, path = word] = LOCATION.exec(word) ?? []
        const trimmed = path.replace(/[.,;:!?)]+$/, '')
        if (!looksLikePath(trimmed)) return undefined
        const absolute = resolve(trimmed, cwd, home)
        if (!seen.has(absolute)) {
          if (!(await $.fs.exists(absolute))) return undefined
          seen.add(absolute)
        }
        return toHref(absolute)
      }

      let isInFence = false
      let text = ''
      let last = 0
      for (const m of e.props.text.matchAll(TOKEN)) {
        const [whole, fence, code, , , word] = m
        text += e.props.text.slice(last, m.index)
        last = m.index + whole.length

        if (fence !== undefined) isInFence = !isInFence
        if (isInFence || fence !== undefined) {
          text += whole
          continue
        }

        if (code !== undefined) {
          const link = await hrefFor(code.slice(1, -1).trim())
          text += link ? `[${code}](${link})` : code
        } else if (word !== undefined) {
          const linkable = word.replace(/[.,;:!?)]+$/, '')
          const link = await hrefFor(linkable)
          text += link ? `[${linkable}](${link})${word.slice(linkable.length)}` : word
        } else {
          text += whole
        }
      }
      text += e.props.text.slice(last)

      return text === e.props.text ? next(e) : next({ ...e, props: { ...e.props, text } })
    } catch {
      return next(e)
    }
  })
}
