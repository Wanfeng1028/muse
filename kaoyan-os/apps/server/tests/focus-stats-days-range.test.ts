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
    authCookie = await registerAndLogin(app, 'focusstatsdaysrange')
  })

  afterAll(async () => {
    if (app) await app.close()
  })

  it('days=0 返回 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=0', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'days 参数无效' })
  })

  it('days=-1 返回 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=-1', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'days 参数无效' })
  })

  it('days=32 返回 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=32', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'days 参数无效' })
  })

  it('days=100 返回 400', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=100', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: 'days 参数无效' })
  })

  it('days=1 返回 200 且 days 长度为 1', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=1', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(200)
    expect(res.json().days).toHaveLength(1)
  })

  it('days=31 返回 200 且 days 长度为 31', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=31', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(200)
    expect(res.json().days).toHaveLength(31)
  })

  it('days=07 返回 200 且 days 长度为 7', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats?days=07', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(200)
    expect(res.json().days).toHaveLength(7)
  })

  it('不传 days 返回 200 且 days 长度为 7', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/focus/stats', headers: { cookie: authCookie } })
    expect(res.statusCode).toBe(200)
    expect(res.json().days).toHaveLength(7)
  })
})