import type { Register } from 'claude-code'

import { fenced, split } from './split'

export const register: Register = on => {
  on('ui.render', { component: 'AssistantMessage' }, ($, e, next) => {
    // Hover and clicks reach the transcript only in the fullscreen terminal.
    if (e.surface !== 'terminal' || e.props.isSummary || !e.viewport?.isFullscreen) {
      return next(e)
    }

    const segments = split(e.props.text)
    if (!segments.some(s => s.kind === 'code')) {
      return next(e)
    }

    const { Box, Text, Button, Markdown } = $.ui.resolve(e)

    // Drawn as the engine draws a reply (bullet, two-column indent, fenced
    // code through the same Markdown highlighter), plus a copy button over
    // each code block's top-left corner, revealed while the block is hovered.
    return (
      <Box flexDirection="row">
        <Box width={2} flexShrink={0}>
          <Text>{e.props.isFirstOfReply ? '⏺' : ' '}</Text>
        </Box>
        <Box flexDirection="column" flexGrow={1} gap={1}>
          {segments.map((s, i) =>
            s.kind === 'prose' ? (
              <Markdown text={s.text} />
            ) : (
              <Box key={`code-${i}`} position="relative">
                <Markdown text={fenced(s)} />
                <Box
                  position="absolute"
                  top={0}
                  left={0}
                  backgroundColor="subtle"
                  display="none"
                  hover={{ display: 'flex' }}
                >
                  <Button
                    key={`copy-${i}`}
                    // Padded in the label, not the Box, so the pointer's
                    // inversion covers the whole grey background.
                    label=" copy "
                    plain
                    onPress={async press => {
                      const result = await $.ui.copy({ text: s.source, surface: press.surface })
                      $.ui.toast(result.isCopied ? 'Copied code block' : `Copy failed: ${result.reason}`)
                    }}
                  />
                </Box>
              </Box>
            ),
          )}
        </Box>
      </Box>
    )
  })
}
