// When a turn-duration row was stored, in ms since the epoch.
export type DoneAt = number

declare module 'claude-code' {
  interface PluginState {
    // One per turn-duration row, by the row's id; 0 while unknown.
    'reply-timestamp': { doneAt: StateFamily<DoneAt> }
  }
}
