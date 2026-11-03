import { describe, it, expect, beforeEach, afterAll } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { DatabaseSync } from 'node:sqlite'
import { registerFocusRoutes } from '../src/routes/focus'
import { createDb as createRealDb } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerAndLogin } from './test-utils'

describe('专注记录查询 - limit/days 参数校验', () => {
  let app: FastifyInstance
  let db: DatabaseSync
  let authCookie: string

  beforeEach(async () => {
    db = createRealDb(':memory:')
    app = Fastify()
    registerFocusRoutes(app, db)
    applyAuthHook(app, db)
    registerAuthRoutes(app, db)
    await app.ready()
    authCookie = await registerAndLogin(app, 'focusparamvalidation')
  })

  afterAll(async () => {
    if (app) await app.close()
  })

  describe('GET /api/focus', () => {
    it('limit=abc 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus?limit=abc',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'limit 参数无效' })
    })

    it('limit=1.5 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus?limit=1.5',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'limit 参数无效' })
    })

    it('limit=1x 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus?limit=1x',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'limit 参数无效' })
    })

    it('limit=2 返回 200 且长度为 2', async () => {
      const username = 'focusparamvalidation'
      const now = new Date()
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, 'math', 30, now.toISOString())
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, 'english', 45, now.toISOString())
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, 'politics', 20, now.toISOString())

      const res = await app.inject({
        method: 'GET',
        url: '/api/focus?limit=2',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(200)
      expect(Array.isArray(res.json()) ? res.json() : res.json().sessions).toHaveLength(2)
    })
  })

  describe('GET /api/focus/stats', () => {
    it('days=abc 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/stats?days=abc',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'days 参数无效' })
    })

    it('days=1.5 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/stats?days=1.5',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'days 参数无效' })
    })

    it('days=7 返回 200 且 days 数组长度为 7', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/stats?days=7',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(200)
      expect(res.json().days).toHaveLength(7)
    })
  })

  describe('GET /api/focus/summary/by-subject', () => {
    it('days=abc 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/summary/by-subject?days=abc',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'days 参数无效' })
    })

    it('days=1.5 返回 400', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/summary/by-subject?days=1.5',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(400)
      expect(res.json()).toEqual({ error: 'days 参数无效' })
    })

    it('不传 days 返回 200 且 subjects 非空', async () => {
      const username = 'focusparamvalidation'
      db.prepare(
        "INSERT INTO focus_sessions (user_id, subject, minutes, started_at) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, ?)",
      ).run(username, 'math', 60, new Date().toISOString())

      const res = await app.inject({
        method: 'GET',
        url: '/api/focus/summary/by-subject',
        headers: { cookie: authCookie },
      })
      expect(res.statusCode).toBe(200)
      const body = res.json()
      const subjects = Array.isArray(body) ? body : body.subjects
      expect(subjects.length).toBeGreaterThan(0)
    })
  })
})
