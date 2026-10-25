import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { createDb } from '../src/db'
import { registerPlansRoutes } from '../src/routes/plans'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerAndLogin } from './test-utils'

describe('GET /api/plans/summary/by-subject', () => {
  let app: FastifyInstance
  let db: ReturnType<typeof createDb>

  beforeEach(async () => {
    db = createDb(':memory:')
    app = Fastify()
    applyAuthHook(app, db)
    registerAuthRoutes(app, db)
    registerPlansRoutes(app, db)
    await app.ready()
  })

  afterEach(async () => {
    await app.close()
  })

  it('returns empty subjects for empty db', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubject')
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject',
      headers: { cookie }
    })
    expect(res.statusCode).toBe(200)
    expect(res.json()).toEqual({ subjects: [] })
  })

  it('returns correct summary with exact values and order', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubject')

    const resA = await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'math', title: 'A', plannedMinutes: 60 },
      headers: { cookie }
    })
    expect(resA.statusCode).toBe(201)
    const planA = resA.json()

    const patchA = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${planA.id}`,
      payload: { done: true },
      headers: { cookie }
    })
    expect(patchA.statusCode).toBe(200)

    const resB = await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'math', title: 'B', plannedMinutes: 90 },
      headers: { cookie }
    })
    expect(resB.statusCode).toBe(201)

    const resC = await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'english', title: 'C', plannedMinutes: 30 },
      headers: { cookie }
    })
    expect(resC.statusCode).toBe(201)
    const planC = resC.json()

    const patchC = await app.inject({
      method: 'PATCH',
      url: `/api/plans/${planC.id}`,
      payload: { done: true },
      headers: { cookie }
    })
    expect(patchC.statusCode).toBe(200)

    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, plan_id) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, datetime('now'), ?)`
    ).run('plansbysubject', 'math', 25, planA.id)

    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, plan_id) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, datetime('now'), ?)`
    ).run('plansbysubject', 'math', 15, planA.id)

    db.prepare(
      `INSERT INTO focus_sessions (user_id, subject, minutes, started_at, plan_id) VALUES ((SELECT id FROM users WHERE username = ?), ?, ?, datetime('now'), ?)`
    ).run('plansbysubject', 'english', 10, planC.id)

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject',
      headers: { cookie }
    })

    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.subjects).toHaveLength(2)
    expect(body.subjects[0]).toEqual({
      subject: 'math',
      total: 2,
      done: 1,
      completionRate: 0.5,
      plannedMinutes: 150,
      actualMinutes: 40
    })
    expect(body.subjects[1]).toEqual({
      subject: 'english',
      total: 1,
      done: 1,
      completionRate: 1,
      plannedMinutes: 30,
      actualMinutes: 10
    })
  })

  it('omits subjects with zero plans', async () => {
    const cookie = await registerAndLogin(app, 'plansbysubject')

    const createRes = await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'math', title: 'M', plannedMinutes: 60 },
      headers: { cookie }
    })
    expect(createRes.statusCode).toBe(201)

    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject',
      headers: { cookie }
    })

    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.subjects).toHaveLength(1)
    expect(body.subjects.some((s: any) => s.subject === 'politics')).toBe(false)
    expect(body.subjects.some((s: any) => s.subject === 'major')).toBe(false)
  })

  it('isolates subjects between users', async () => {
    const cookie1 = await registerAndLogin(app, 'plansbysubject')
    const cookie2 = await registerAndLogin(app, 'plansbysubject2')

    await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'math', title: 'M', plannedMinutes: 60 },
      headers: { cookie: cookie1 }
    })
    await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'english', title: 'E', plannedMinutes: 30 },
      headers: { cookie: cookie1 }
    })

    await app.inject({
      method: 'POST',
      url: '/api/plans',
      payload: { date: '2024-01-01', subject: 'politics', title: 'P', plannedMinutes: 45 },
      headers: { cookie: cookie2 }
    })

    const res1 = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject',
      headers: { cookie: cookie1 }
    })
    expect(res1.statusCode).toBe(200)
    const body1 = res1.json()
    const names1 = body1.subjects.map((s: any) => s.subject)
    expect(names1).toHaveLength(2)
    expect(names1).toContain('math')
    expect(names1).toContain('english')
    expect(names1).not.toContain('politics')

    const res2 = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject',
      headers: { cookie: cookie2 }
    })
    expect(res2.statusCode).toBe(200)
    const body2 = res2.json()
    const names2 = body2.subjects.map((s: any) => s.subject)
    expect(names2).toHaveLength(1)
    expect(names2).toContain('politics')
  })

  it('returns 401 when not authenticated', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/api/plans/summary/by-subject'
    })
    expect(res.statusCode).toBe(401)
  })
})