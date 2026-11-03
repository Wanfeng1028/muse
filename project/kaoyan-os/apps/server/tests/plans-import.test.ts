import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import Fastify, { type FastifyInstance } from 'fastify'
import { createDb } from '../src/db'
import { applyAuthHook, registerAuthRoutes } from '../src/auth'
import { registerPlansRoutes } from '../src/routes/plans'
import { registerAndLogin } from './test-utils'

interface PlanRow {
  date: string
  subject: string
  title: string
  plannedMinutes: number
  done: boolean
}

describe('POST /api/import/plans', () => {
  let app: FastifyInstance
  let db: ReturnType<typeof createDb>
  let cookie: string

  beforeEach(async () => {
    db = createDb(':memory:')
    app = Fastify()
    applyAuthHook(app, db)
    registerAuthRoutes(app, db)
    registerPlansRoutes(app, db)
    await app.ready()
    cookie = await registerAndLogin(app, 'planscsv')
  })

  afterEach(async () => {
    await app.close()
    db.close()
  })

  const postImport = (csv: string) =>
    app.inject({
      method: 'POST',
      url: '/api/import/plans',
      headers: { cookie },
      payload: { csv },
    })

  it('空 csv 返回 400', async () => {
    const empty = await postImport('')
    expect(empty.statusCode).toBe(400)
    expect(empty.json()).toEqual({ error: 'csv 不能为空' })

    const blank = await postImport('   \n\t')
    expect(blank.statusCode).toBe(400)
    expect(blank.json()).toEqual({ error: 'csv 不能为空' })
  })

  it('缺少必需列返回 400', async () => {
    const res = await postImport('date,subject\n2026-02-01,math')
    expect(res.statusCode).toBe(400)
    expect(res.json()).toEqual({ error: '缺少必需列：date / subject / title' })
  })

  it('两行合法加一行非法日期：合法行入库、非法行记错', async () => {
    const csv = [
      'date,subject,title,planned_minutes',
      '2026-02-01,math,Solve algebra set,30',
      '2026-02-02,english,Read chapter 5,45',
      'not-a-date,math,Bad date row,30',
    ].join('\n')

    const res = await postImport(csv)
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(2)
    expect(body.errorRows).toBe(1)
    expect(body.errors).toHaveLength(1)
    expect(body.errors[0].row).toBe(4)
    expect(typeof body.errors[0].message).toBe('string')

    const list = await app.inject({ method: 'GET', url: '/api/plans', headers: { cookie } })
    expect(list.statusCode).toBe(200)
    const plans = list.json() as PlanRow[]
    expect(plans).toHaveLength(2)

    const algebra = plans.find((p) => p.title === 'Solve algebra set')
    const reading = plans.find((p) => p.title === 'Read chapter 5')
    expect(algebra?.date).toBe('2026-02-01')
    expect(algebra?.subject).toBe('math')
    expect(algebra?.plannedMinutes).toBe(30)
    expect(reading?.date).toBe('2026-02-02')
    expect(reading?.subject).toBe('english')
    expect(reading?.plannedMinutes).toBe(45)
  })

  it("done='1' 入库为 true，plannedMinutes 缺省为 60", async () => {
    const csv = ['date,subject,title,done', '2026-03-01,math,Finish problem set,1'].join('\n')

    const res = await postImport(csv)
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(1)
    expect(body.errorRows).toBe(0)
    expect(body.errors).toEqual([])

    const list = await app.inject({ method: 'GET', url: '/api/plans', headers: { cookie } })
    expect(list.statusCode).toBe(200)
    const plans = list.json() as PlanRow[]
    expect(plans).toHaveLength(1)
    expect(plans[0].done).toBe(true)
    expect(plans[0].plannedMinutes).toBe(60)
    expect(plans[0].title).toBe('Finish problem set')
  })

  it('非法 subject 记错且不入库', async () => {
    const csv = ['date,subject,title', '2026-04-01,,Blank subject'].join('\n')

    const res = await postImport(csv)
    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.imported).toBe(0)
    expect(body.errorRows).toBe(1)
    expect(body.errors).toHaveLength(1)
    expect(body.errors[0].row).toBe(2)
    expect(typeof body.errors[0].message).toBe('string')

    const list = await app.inject({ method: 'GET', url: '/api/plans', headers: { cookie } })
    expect(list.statusCode).toBe(200)
    const plans = list.json() as PlanRow[]
    expect(plans).toHaveLength(0)
  })

  it('未登录返回 401', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/import/plans',
      payload: { csv: 'date,subject,title\n2026-02-01,math,Algebra,30' },
    })
    expect(res.statusCode).toBe(401)
  })
})
