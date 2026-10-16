import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { buildApp } from '../src/app'

describe('words import', () => {
  let app: Awaited<ReturnType<typeof buildApp>>

  beforeAll(async () => {
    app = buildApp({ dbPath: ':memory:' })
    await app.ready()
  })

  afterAll(async () => {
    await app.close()
  })

  it('导入 3 个词：200 且 imported=3，source=core500，meaning/example 拼接正确', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [
          {
            word: 't1abandon',
            phonetic: '/əˈbændən/',
            pos: 'v.',
            meanings_zh: ['抛弃', '放弃'],
            example_en: 'He abandoned his car.',
            example_zh: '他抛弃了他的车。',
          },
          {
            word: 't1ability',
            phonetic: '/əˈbɪləti/',
            pos: 'n.',
            meanings_zh: ['能力'],
            example_en: 'She has ability.',
            example_zh: '她有这个能力。',
          },
          {
            word: 't1absolute',
            pos: 'adj.',
            meanings_zh: ['绝对的'],
          },
        ],
      },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(3)
    expect(body.skippedExisting).toBe(0)
    expect(body.skippedInvalid).toBe(0)

    const listRes = await app.inject({ method: 'GET', url: '/api/words' })
    expect(listRes.statusCode).toBe(200)
    const list = listRes.json() as Array<{
      word: string
      meaning: string
      example: string
      source: string
    }>
    const w = list.find((x) => x.word === 't1abandon')
    expect(w).toBeTruthy()
    expect(w!.source).toBe('core500')
    expect(w!.meaning).toBe('v. 抛弃；放弃')
    expect(w!.example).toBe('He abandoned his car. ｜ 他抛弃了他的车。')
  })

  it('幂等：同一 payload 再 POST：imported=0，skippedExisting=3，总数不变', async () => {
    const before = (
      await app.inject({ method: 'GET', url: '/api/words' })
    ).json() as unknown[]
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [
          { word: 't1abandon', pos: 'v.', meanings_zh: ['抛弃', '放弃'] },
          { word: 't1ability', pos: 'n.', meanings_zh: ['能力'] },
          { word: 't1absolute', pos: 'adj.', meanings_zh: ['绝对的'] },
        ],
      },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(0)
    expect(body.skippedExisting).toBe(3)
    const after = (
      await app.inject({ method: 'GET', url: '/api/words' })
    ).json() as unknown[]
    expect(after.length).toBe(before.length)
  })

  it('批次内重复：imported=1，skippedExisting=1', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [
          { word: 't3dup', pos: 'n.', meanings_zh: ['重复'] },
          { word: 't3dup', pos: 'n.', meanings_zh: ['重复'] },
        ],
      },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(1)
    expect(body.skippedExisting).toBe(1)
  })

  it('无效项：word 空 + meanings_zh 空数组：skippedInvalid=2，errors 长度 2', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [
          { word: '   ', meanings_zh: ['有效'] },
          { word: 't4valid', meanings_zh: [] },
        ],
      },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.skippedInvalid).toBe(2)
    expect(body.errors.length).toBe(2)
    for (const e of body.errors) {
      expect(typeof e.index).toBe('number')
      expect(typeof e.message).toBe('string')
    }
  })

  it('非法请求体：words 缺失 / 字符串 / 空数组 均 400', async () => {
    const r1 = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {},
    })
    expect(r1.statusCode).toBe(400)

    const r2 = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: { words: 'not-array' },
    })
    expect(r2.statusCode).toBe(400)

    const r3 = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: { words: [] },
    })
    expect(r3.statusCode).toBe(400)
  })

  it('非法 source：400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        source: 'nope',
        words: [{ word: 't6x', meanings_zh: ['x'] }],
      },
    })
    expect(res.statusCode).toBe(400)
  })

  it('SRS 初始化：导入后 GET /api/words/due 包含新词，dueDate 为今天', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        words: [{ word: 't7due', pos: 'n.', meanings_zh: ['到期'] }],
      },
    })
    expect(res.statusCode).toBe(200)

    const dueRes = await app.inject({ method: 'GET', url: '/api/words/due' })
    expect(dueRes.statusCode).toBe(200)
    const due = dueRes.json() as Array<{
      word: string
      state: { dueDate: string }
    }>
    const found = due.find((x) => x.word === 't7due')
    expect(found).toBeTruthy()
    const d = new Date()
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const today = `${y}-${m}-${day}`
    expect(found!.state.dueDate).toBe(today)
  })

  it('指定 source=csv：查得 source=csv', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: {
        source: 'csv',
        words: [{ word: 't8csv', pos: 'n.', meanings_zh: ['导入'] }],
      },
    })
    expect(res.statusCode).toBe(200)
    const list = (
      await app.inject({ method: 'GET', url: '/api/words' })
    ).json() as Array<{ word: string; source: string }>
    const w = list.find((x) => x.word === 't8csv')
    expect(w).toBeTruthy()
    expect(w!.source).toBe('csv')
  })

  it('不影响已有词：内置词 abandon 仍在且 source=builtin', async () => {
    const list = (
      await app.inject({ method: 'GET', url: '/api/words' })
    ).json() as Array<{ word: string; source: string }>
    const builtin = list.filter((x) => x.source === 'builtin')
    expect(builtin.length).toBe(24)
    const abandon = list.find((x) => x.word === 'abandon')
    expect(abandon).toBeTruthy()
    expect(abandon!.source).toBe('builtin')
  })

  it('上限：words 数组长度 2001：400', async () => {
    const arr = Array.from({ length: 2001 }, (_, i) => ({
      word: `t10w${i}`,
      meanings_zh: ['x'],
    }))
    const res = await app.inject({
      method: 'POST',
      url: '/api/words/import',
      payload: { words: arr },
    })
    expect(res.statusCode).toBe(400)
  })
})
