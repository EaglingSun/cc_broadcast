export type CastItem = { seq: number; text: string; at: number }
export type CastConn = { state: 'off' | 'ok' | 'down'; address: string; error?: string }
export type CastCursor = { run: string; seq: number }

declare module 'claude-code' {
  interface PluginState {
    'prompt-cast-recv': { conn: CastConn; received: CastItem[]; pending: CastItem | null }
  }
}
