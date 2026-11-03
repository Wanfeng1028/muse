import { describe, it, expect, beforeEach, afterAll } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { DatabaseSync } from 'node:sqlite'
import { registerFocusRoutes } from '../src/routes/focus'
import { createDb as createRealDb } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerAndLogin } from './test-utils'

describe('专注记录查询 - limit 范围收紧', () => {
  let app: FastifyInstance
  let db: DatabaseSync
  let authCookie: string
  const username = 'focuslistlimitrange'

  beforeEach(async () => {
    db = createRealDb(':memory:')
    app = Fastify()
    registerFocusRoutes(app, db)
    applyAuthHook(app, db)
    registerAuthRoutes(app, db)
    await app.ready()
    authCookie = await registerAndLogin(app, username)
  })

  afterAll(async () => {
    if (app) await app.close()
  })

  function seed(count: number, day: string): void {
    for (let i = 0; i < count; i++) {
      const startedAt = day + 'T00:' + String(i).padStart(2, '0') + ':00.000Z'
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, 'math', 30, startedAt)
    }
  }

  it('limit=0 返回 400', async () => {
    seed(1, '2024-01-01')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=0',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'limit 参数无效' })
  })

  it('limit=-1 返回 400', async () => {
    seed(1, '2024-01-01')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=-1',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'limit 参数无效' })
  })

  it('limit=501 返回 400', async () => {
    seed(1, '2024-01-01')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=501',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'limit 参数无效' })
  })

  it('limit=1000 返回 400', async () => {
    seed(1, '2024-01-01')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=1000',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'limit 参数无效' })
  })

  it('limit=1 返回 200 且长度为 1', async () => {
    seed(3, '2024-01-02')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=1',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(200)
    expect((res.json() as unknown[]).length).toBe(1)
  })

  it('limit=500 返回 200 且长度为 5', async () => {
    seed(5, '2024-01-03')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus?limit=500',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(200)
    expect((res.json() as unknown[]).length).toBe(5)
  })

  it('不传 limit 返回 200 且长度为 50', async () => {
    seed(60, '2024-01-04')
    const res = await app.inject({
      method: 'GET',
      url: '/api/focus',
      headers: { cookie: authCookie },
    })
    expect(res.statusCode).toBe(200)
    expect((res.json() as unknown[]).length).toBe(50)
  })
})
