import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { createDb, todayStr } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerExamsRoutes } from '../src/routes/exams'
import { registerAndLogin } from './test-utils'

let db: ReturnType<typeof createDb>
let app: FastifyInstance
let cookie: string

describe('POST /api/import/exams', () => {
  beforeEach(async () => {
    db = createDb(':memory:')
    app = Fastify()
    applyAuthHook(app, db)
    registerAuthRoutes(app, db)
    registerExamsRoutes(app, db)
    await app.ready()
    cookie = await registerAndLogin(app, 'examscsv')
  })

  afterEach(async () => {
    await app.close()
    db.close()
  })

  it('空 csv 返回 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      headers: { cookie },
      payload: { csv: '' },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'csv 不能为空' })
  })

  it('缺少必需列返回 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      headers: { cookie },
      payload: { csv: 'subject,paper\n数学,期中' },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: '缺少必需列：subject / paper / score / total_score' })
  })

  it('两行合法加一行 score 超 total_score：合法行入库，非法行记入 errors', async () => {
    const csv = [
      'subject,paper,score,total_score,taken_at',
      'math,期中,90,100,2026-01-10',
      'english,期末,85,100,2026-01-11',
      'major,月考,120,100,2026-01-12',
    ].join('\n')
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      headers: { cookie },
      payload: { csv },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json() as {
      imported: number
      errorRows: number
      errors: Array<{ row: number; message: string }>
    }
    expect(body.imported).toBe(2)
    expect(body.errorRows).toBe(1)
    expect(body.errors).toHaveLength(1)
    expect(body.errors[0].row).toBe(4)
    expect(typeof body.errors[0].message).toBe('string')
    expect(body.errors[0].message.length).toBeGreaterThan(0)

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: { cookie },
    })
    expect(listRes.statusCode).toBe(200)
    const list = listRes.json() as Array<{
      subject: string
      paper: string
      score: number
      totalScore: number
    }>
    expect(list).toHaveLength(2)
    const math = list.find((item) => item.subject === 'math')
    expect(math?.paper).toBe('期中')
    expect(math?.score).toBe(90)
    expect(math?.totalScore).toBe(100)
    const english = list.find((item) => item.subject === 'english')
    expect(english?.paper).toBe('期末')
    expect(english?.score).toBe(85)
    expect(english?.totalScore).toBe(100)
  })

  it('非法 subject 记入 errors 且不入库', async () => {
    const csv = 'subject,paper,score,total_score,taken_at\n,期末,85,100,2026-01-15'
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      headers: { cookie },
      payload: { csv },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json() as {
      imported: number
      errorRows: number
      errors: Array<{ row: number; message: string }>
    }
    expect(body.imported).toBe(0)
    expect(body.errorRows).toBe(1)
    expect(body.errors).toHaveLength(1)
    expect(body.errors[0].row).toBe(2)

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: { cookie },
    })
    expect(listRes.statusCode).toBe(200)
    expect(listRes.json()).toHaveLength(0)
  })

  it('taken_at 缺省为今天', async () => {
    const csv = 'subject,paper,score,total_score\nmath,月考,92,100'
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      headers: { cookie },
      payload: { csv },
    })
    expect(res.statusCode).toBe(200)
    const body = res.json() as { imported: number; errorRows: number }
    expect(body.imported).toBe(1)
    expect(body.errorRows).toBe(0)

    const listRes = await app.inject({
      method: 'GET',
      url: '/api/exams',
      headers: { cookie },
    })
    expect(listRes.statusCode).toBe(200)
    const list = listRes.json() as Array<{ subject: string; takenAt: string }>
    expect(list).toHaveLength(1)
    expect(list[0].subject).toBe('math')
    expect(list[0].takenAt).toBe(todayStr())
  })

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/exams',
      payload: { csv: 'subject,paper,score,total_score\nmath,期中,90,100' },
    })
    expect(res.statusCode).toBe(401)
  })
})
