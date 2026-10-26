import { describe, it, expect, beforeEach, afterAll } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { DatabaseSync } from 'node:sqlite'
import { createDb } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerAndLogin } from './test-utils'
import { registerFocusRoutes } from '../src/routes/focus'

const CSV_HEADER = 'id,subject,subject_name,minutes,started_at,note,plan_id'

let app: FastifyInstance
let db: DatabaseSync
let cookie: string

function toLines(text: string): string[] {
  return text.replace(/^\uFEFF/, '').trimEnd().split(/\r?\n/)
}

function insertSession(
  username: string,
  subject: string,
  minutes: number,
  startedAt: string,
  note: string | null,
): number {
  const result = db
    .prepare(
      'INSERT INTO focus_sessions (user_id, subject, minutes, started_at, note, plan_id) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?, ?, NULL)',
    )
    .run(username, subject, minutes, startedAt, note)
  return Number(result.lastInsertRowid)
}

describe('GET /api/focus/export', () => {
  beforeEach(async () => {
    db = createDb(':memory:')
    app = Fastify()
    registerAuthRoutes(app, db)
    applyAuthHook(app, db)
    registerFocusRoutes(app, db)
    await app.ready()
    cookie = await registerAndLogin(app, 'focusexport')
  })

  afterAll(async () => {
    await app.close()
  })

  it('空库时返回 200，BOM 开头，text/csv，仅表头', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/export', headers: { cookie } })
    expect(res.statusCode).toBe(200)
    expect(res.headers['content-type']).toContain('text/csv')
    expect(res.body.startsWith('\uFEFF')).toBe(true)

    const lines = toLines(res.body)
    expect(lines).toHaveLength(1)
    expect(lines[0]).toBe(CSV_HEADER)
  })

  it('两条记录按 started_at 升序输出，subject_name 与 note 列正确', async () => {
    const later = insertSession('focusexport', 'math', 25, '2024-05-02T09:30:00.000Z', '复盘')
    const earlier = insertSession('focusexport', 'math', 40, '2024-05-01T08:00:00.000Z', '晨读')

    const res = await app.inject({ method: 'GET', url: '/api/focus/export', headers: { cookie } })
    expect(res.statusCode).toBe(200)

    const lines = toLines(res.body)
    expect(lines).toHaveLength(3)
    expect(lines[0]).toBe(CSV_HEADER)
    expect(lines[1]).toBe(`${earlier},math,数学,40,2024-05-01T08:00:00.000Z,晨读,`)
    expect(lines[2]).toBe(`${later},math,数学,25,2024-05-02T09:30:00.000Z,复盘,`)
  })

  it('note 含逗号与双引号时按 RFC4180 转义', async () => {
    insertSession('focusexport', 'math', 60, '2024-05-01T08:00:00.000Z', '冲刺, "重点"突破')

    const res = await app.inject({ method: 'GET', url: '/api/focus/export', headers: { cookie } })
    expect(res.statusCode).toBe(200)

    const lines = toLines(res.body)
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain('"冲刺, ""重点""突破"')
  })

  it('subject=math 只导出数学，非法 subject 返回 400', async () => {
    insertSession('focusexport', 'math', 30, '2024-05-01T08:00:00.000Z', '专注数学')
    insertSession('focusexport', 'english', 45, '2024-05-01T09:00:00.000Z', '听力训练')

    const res = await app.inject({ method: 'GET', url: '/api/focus/export?subject=math', headers: { cookie } })
    expect(res.statusCode).toBe(200)

    const lines = toLines(res.body)
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain(',math,')
    expect(lines[1]).toContain('数学')
    expect(lines[1]).not.toContain('english')

    const bad = await app.inject({ method: 'GET', url: '/api/focus/export?subject=bad', headers: { cookie } })
    expect(bad.statusCode).toBe(400)
  })

  it('只导出当前登录用户的记录', async () => {
    insertSession('focusexport', 'math', 30, '2024-05-01T08:00:00.000Z', '我的记录')
    const otherCookie = await registerAndLogin(app, 'focusexport2')
    insertSession('focusexport2', 'math', 50, '2024-05-02T10:00:00.000Z', '别人的记录')

    const res = await app.inject({ method: 'GET', url: '/api/focus/export', headers: { cookie } })
    expect(res.statusCode).toBe(200)

    const lines = toLines(res.body)
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain('我的记录')
    expect(res.body).not.toContain('别人的记录')

    const other = await app.inject({ method: 'GET', url: '/api/focus/export', headers: { cookie: otherCookie } })
    expect(other.statusCode).toBe(200)
    const otherLines = toLines(other.body)
    expect(otherLines).toHaveLength(2)
    expect(otherLines[1]).toContain('别人的记录')
  })

  it('未登录返回 401', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/export' })
    expect(res.statusCode).toBe(401)
  })
})
