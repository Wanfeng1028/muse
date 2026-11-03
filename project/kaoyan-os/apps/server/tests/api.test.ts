import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { buildApp } from '../src/app'
import { registerAndLogin } from './test-utils';

function todayStr(d: Date = new Date()): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

describe('api integration', () => {
  let app: Awaited<ReturnType<typeof buildApp>>

  let authCookie = '';
  beforeAll(async () => {
    app = buildApp({ dbPath: ':memory:' })
    await app.ready()

    authCookie = await registerAndLogin(app, 'apitest');  })

  afterAll(async () => {
    await app.close()
  })

  it('GET /api/health returns ok', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/health' })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.status).toBe('ok')
  })

  it('POST /api/plans creates a plan and GET /api/plans?date=today finds it', async () => {
    const today = todayStr()
    const createRes = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        date: today,
        subject: 'math',
        title: '测试计划',
        plannedMinutes: 60
      }
    })
    expect(createRes.statusCode).toBe(201)
    const created = createRes.json()
    expect(created).toBeTruthy()

    const listRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: `/api/plans?date=${today}`
    })
    expect(listRes.statusCode).toBe(200)
    const list = listRes.json()
    const arr = Array.isArray(list) ? list : list.items ?? list.plans ?? []
    const found = arr.some(
      (p: any) => p.title === '测试计划' && p.subject === 'math' && p.date === today
    )
    expect(found).toBe(true)
  })

  it('PATCH /api/plans/:id marks done and summary reflects it', async () => {
    const today = todayStr()
    const createRes = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        date: today,
        subject: 'math',
        title: '待完成计划',
        plannedMinutes: 30
      }
    })
    expect(createRes.statusCode).toBe(201)
    const created = createRes.json()
    const id = created.id ?? created.plan?.id
    expect(id).toBeTruthy()

    const patchRes = await app.inject({ headers: { cookie: authCookie },
      method: 'PATCH',
      url: `/api/plans/${id}`,
      payload: { done: true }
    })
    expect(patchRes.statusCode).toBe(200)

    const summaryRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: `/api/plans/summary?date=${today}`
    })
    expect(summaryRes.statusCode).toBe(200)
    const summary = summaryRes.json()
    const done =
      typeof summary.done === 'number'
        ? summary.done
        : typeof summary.doneCount === 'number'
        ? summary.doneCount
        : summary.completed ?? 0
    expect(done).toBeGreaterThanOrEqual(1)
  })

  it('POST /api/focus logs focus session and stats include it', async () => {
    const postRes = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/focus',
      payload: { subject: 'english', minutes: 25 }
    })
    expect(postRes.statusCode).toBe(201)

    const statsRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/focus/stats?days=7'
    })
    expect(statsRes.statusCode).toBe(200)
    const stats = statsRes.json()
    expect(stats.todayMinutes).toBeGreaterThanOrEqual(25)
    expect(Array.isArray(stats.days)).toBe(true)
    expect(stats.days.length).toBe(7)
  })

  it('GET /api/words/due returns a non-empty array', async () => {
    // 先给当前用户建一个词（新词 due_date 为今天）
    const created = await app.inject({ headers: { cookie: authCookie },
      method: 'POST', url: '/api/words', payload: { word: 'dueword1', meaning: '到期词' } })
    expect(created.statusCode).toBe(201)
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words/due' })
    expect(res.statusCode).toBe(200)
    const body = res.json()
    const arr = Array.isArray(body) ? body : body.items ?? body.words ?? []
    expect(Array.isArray(arr)).toBe(true)
    expect(arr.length).toBeGreaterThan(0)
  })

  it('POST /api/words/:id/review updates dueDate beyond today', async () => {
    const created = await app.inject({ headers: { cookie: authCookie },
      method: 'POST', url: '/api/words', payload: { word: 'dueword2', meaning: '到期词2' } })
    expect(created.statusCode).toBe(201)
    const dueRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words/due' })
    const dueBody = dueRes.json()
    const dueList = Array.isArray(dueBody) ? dueBody : dueBody.items ?? dueBody.words ?? []
    expect(dueList.length).toBeGreaterThan(0)
    const first = dueList[0]
    const id = first.id ?? first.wordId
    expect(id).toBeTruthy()

    const reviewRes = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: `/api/words/${id}/review`,
      payload: { grade: 2 }
    })
    expect(reviewRes.statusCode).toBe(200)
    const reviewed = reviewRes.json()
    const state = reviewed.state ?? reviewed
    expect(state.dueDate).toBeTruthy()

    const today = todayStr()
    const dueDate = String(state.dueDate).slice(0, 10)
    expect(dueDate > today).toBe(true)
  })

  it('POST /api/exams creates exam and GET /api/exams?subject=math reflects trend rate', async () => {
    const createRes = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/exams',
      payload: {
        subject: 'math',
        paper: '测试卷',
        score: 100,
        totalScore: 150,
        durationMinutes: 120
      }
    })
    expect(createRes.statusCode).toBe(201)

    const listRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/exams?subject=math'
    })
    expect(listRes.statusCode).toBe(200)
    const body = listRes.json()
    const arr = Array.isArray(body) ? body : body.items ?? body.exams ?? []
    const found = arr.some((e: any) => e.paper === '测试卷')
    expect(found).toBe(true)

    const trendRes = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/exams/trend?subject=math'
    })
    expect(trendRes.statusCode).toBe(200)
    const trend = trendRes.json()
    expect(Array.isArray(trend)).toBe(true)
    expect(trend.length).toBeGreaterThan(0)
    const last = trend[trend.length - 1]
    const rate = typeof last.rate === 'number' ? last.rate : last.score / last.totalScore
    expect(rate).toBeCloseTo(0.6667, 2)
  })

  it('GET /api/settings returns default examDate and PUT updates dailyGoalMinutes', async () => {
    const getRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/settings' })
    expect(getRes.statusCode).toBe(200)
    const settings = getRes.json()
    expect(settings.examDate).toBe('2026-12-19')

    const putRes = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { dailyGoalMinutes: 240 }
    })
    expect(putRes.statusCode).toBe(200)
    const updated = putRes.json()
    expect(updated.dailyGoalMinutes).toBe(240)

    const getRes2 = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/settings' })
    const settings2 = getRes2.json()
    expect(settings2.dailyGoalMinutes).toBe(240)
  })

  it('GET /api/settings returns default theme light', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/settings' })
    expect(res.statusCode).toBe(200)
    expect(res.json().theme).toBe('light')
  })

  it('PUT /api/settings { theme: "dark" } persists theme dark', async () => {
    const putRes = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'dark' }
    })
    expect(putRes.statusCode).toBe(200)
    expect(putRes.json().theme).toBe('dark')

    const getRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/settings' })
    expect(getRes.statusCode).toBe(200)
    expect(getRes.json().theme).toBe('dark')
  })

  it('PUT /api/settings { theme: "blue" } returns 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'blue' }
    })
    expect(res.statusCode).toBe(400)
  })

  it('PUT /api/settings { theme: 1 } returns 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 1 }
    })
    expect(res.statusCode).toBe(400)
  })

  it('PUT /api/settings { theme: "Dark" } returns 400', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'Dark' }
    })
    expect(res.statusCode).toBe(400)
  })

  it('PUT /api/settings { theme: "light" } switches back successfully', async () => {
    const putRes = await app.inject({ headers: { cookie: authCookie },
      method: 'PUT',
      url: '/api/settings',
      payload: { theme: 'light' }
    })
    expect(putRes.statusCode).toBe(200)
    expect(putRes.json().theme).toBe('light')

    const getRes = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/settings' })
    expect(getRes.statusCode).toBe(200)
    expect(getRes.json().theme).toBe('light')
  })

  it('POST /api/plans with invalid subject returns 400', async () => {
    const today = todayStr()
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/plans',
      payload: {
        date: today,
        subject: 'invalid-subject',
        title: '非法计划',
        plannedMinutes: 30
      }
    })
    expect(res.statusCode).toBe(400)
  })
})
