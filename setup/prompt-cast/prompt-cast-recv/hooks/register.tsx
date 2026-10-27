import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { CastConn, CastCursor, CastItem } from '../types'

// 수강생용: 강사 PC 중계 서버(cast_relay.py)의 /feed 를 2초마다 받아,
// 새 방송을 입력창에 초안으로 넣는다. 보내는 일(Enter)은 언제나 수강생 몫이다.
const PANE = 'cast'
const TITLE = '강사 프롬프트'
const POLL_MS = 2000
const KEEP = 30
const ADDRESS_RE = /^[A-Za-z0-9.-]+:\d{1,5}$/

// plugin · key 는 엔진이 소스에서 읽으므로 문자열 리터럴로 쓴다
const conn = atom({ plugin: 'prompt-cast-recv', key: 'conn' } as const, { state: 'off', address: '' })
const received = atom({ plugin: 'prompt-cast-recv', key: 'received' } as const, [])
const pending = atom({ plugin: 'prompt-cast-recv', key: 'pending' } as const, null)

type Feed = { run: string; seq: number; items: CastItem[] }

// 폴링이 겹치지 않게 — fetch 가 30초까지 걸릴 수 있다
let inFlight = false

const preview = (text: string) => {
  const first = text.split('\n')[0] ?? ''
  return first.length > 60 ? `${first.slice(0, 60)}…` : first
}

async function setConn($: EngineInterface, next: CastConn) {
  const prev = await read($, conn)
  await update($, conn, () => next)
  if (prev.state === next.state && prev.address === next.address && prev.error === next.error) return
  if (next.state === 'off') $.ui.status(undefined)
  else if (next.state === 'ok') $.ui.status(`📡 강사 연결됨 · ${next.address}`)
  else $.ui.status(`📡 강사 연결 안 됨 · ${next.address} — 강사 화면의 /cast-connect 주소 확인`)
}

async function fillDraft($: EngineInterface, item: CastItem, mode: 'replace' | 'append') {
  const text = mode === 'append' ? `\n${item.text}` : item.text
  const filled = await $.prompt.fill({ text, mode })
  if (filled.isFilled) await update($, pending, () => null)
  return filled.isFilled
}

async function deliver($: EngineInterface, item: CastItem) {
  const box = await $.prompt.read()
  if (box.text.trim() === '' && (await fillDraft($, item, 'replace'))) {
    $.ui.toast(`📣 강사 프롬프트 #${item.seq} — 입력창에 넣었습니다. 고친 뒤 Enter`)
    return
  }
  // 쓰던 글이 있거나 다이얼로그 중 — 덮지 않고 band 에 남긴다
  await update($, pending, () => item)
  $.ui.toast(`📣 강사 프롬프트 #${item.seq} 도착 — 입력창 위 [넣기]`)
}

async function pollOnce($: EngineInterface) {
  const address = (await $.store.get('address')) as string | undefined
  if (!address || inFlight) return
  inFlight = true
  try {
    const cursor = ((await $.store.get('cursor')) as CastCursor | undefined) ?? { run: '', seq: 0 }
    let feed: Feed
    try {
      const url = `http://${address}/feed?since=${cursor.seq}&run=${encodeURIComponent(cursor.run)}`
      const res = await $.http.fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      feed = JSON.parse(res.text) as Feed
    } catch (err) {
      await setConn($, { state: 'down', address, error: String(err).slice(0, 200) })
      return
    }
    await setConn($, { state: 'ok', address })
    await $.store.set('cursor', { run: feed.run, seq: feed.seq })
    if (feed.items.length === 0) return
    const list = await update($, received, l => [...l, ...feed.items].slice(-KEEP))
    await $.store.set('received', list)
    await deliver($, feed.items[feed.items.length - 1]!)
  } finally {
    inFlight = false
  }
}

async function connect($: EngineInterface, arg: string) {
  if (arg === '') {
    const c = await read($, conn)
    if (!c.address) return '연결된 강사 PC 가 없습니다. 강사 화면의 줄을 그대로 입력하세요: /cast-connect 10.10.111.97:8790'
    return c.state === 'ok'
      ? `강사 PC 에 연결되어 있습니다 (${c.address}).`
      : `강사 PC 에 연결 안 됨 (${c.address}): ${c.error ?? '확인 중'}`
  }
  if (arg === 'off') {
    await $.store.delete('address')
    await setConn($, { state: 'off', address: '' })
    return '강사 프롬프트 받기를 껐습니다.'
  }
  if (!ADDRESS_RE.test(arg)) return `주소 형식이 아닙니다: "${arg}" — 형식: 강사IP:포트 (예: 10.10.111.97:8790)`
  await $.store.set('address', arg)
  await pollOnce($)
  const c = await read($, conn)
  return c.state === 'ok'
    ? `강사 PC 에 연결했습니다 (${arg}). 방송이 오면 입력창에 초안으로 들어갑니다.`
    : `강사 PC 에 연결 안 됨 (${arg}): ${c.error ?? ''} — 강사 화면의 주소를 다시 확인하세요.`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const stored = await $.store.get('received')
    if (Array.isArray(stored)) await update($, received, () => stored as CastItem[])
    const address = (await $.store.get('address')) as string | undefined
    if (address) await update($, conn, (): CastConn => ({ state: 'down', address, error: '확인 중' }))
    await $.command.register({
      name: 'cast-connect',
      description: '강사 PC 연결 (/cast-connect 강사IP:포트 · off · 비우면 상태)',
      argumentHint: '[강사IP:포트 | off]',
    })
    await $.command.register({ name: 'cast', description: '강사 프롬프트 받은 목록 창 열기' })
    $.clock.every(POLL_MS, () => void pollOnce($))
    return next(e)
  })

  on('command.run', { command: 'cast-connect' }, async ($, e) => ({ text: await connect($, e.args.trim()) }))

  on('command.run', { command: 'cast' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE, focus: true })
    return { text: '강사 프롬프트 창을 열었습니다.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const item = await read($, pending)
    if (e.props.hasSurvey || item === null) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="row">
        <Text color="yellow">
          📣 강사 프롬프트 #{item.seq} 도착: {preview(item.text)}{' '}
        </Text>
        <Button key="fill" label="넣기" onPress={() => void fillDraft($, item, 'replace')} />
        <Button key="append" label="뒤에 붙이기" onPress={() => void fillDraft($, item, 'append')} />
        <Button key="dismiss" plain label="✕" onPress={() => update($, pending, () => null)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const c = await read($, conn)
    const list = await read($, received)
    const head =
      c.state === 'ok' ? `연결됨 · ${c.address}` : c.address ? `연결 안 됨 · ${c.address}` : '연결 없음 — /cast-connect 강사IP:포트'
    return (
      <Box flexDirection="column">
        <Text dimColor>{head} · 받은 {list.length}건</Text>
        {list.length === 0 && <Text dimColor>아직 받은 프롬프트가 없습니다.</Text>}
        {list
          .slice()
          .reverse()
          .map(item => (
            <Box key={`row-${item.seq}`} flexDirection="column">
              <Box flexDirection="row">
                <Text bold>#{item.seq} </Text>
                <Button key={`fill-${item.seq}`} label="넣기" onPress={() => void fillDraft($, item, 'replace')} />
              </Box>
              <Text>{item.text}</Text>
            </Box>
          ))}
      </Box>
    )
  })
}
