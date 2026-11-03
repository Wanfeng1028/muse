import test from 'node:test'
import assert from 'node:assert/strict'
import { createHttpClient } from '../http.ts'
import { createPortalApi } from '../portal.ts'

test('portal api maps dashboard and generator endpoints', async () => {
  const calls: Array<{ url: string; method: string; body?: string }> = []
  const fetcher = async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), method: init?.method ?? 'GET', body: init?.body as string | undefined })
    if (String(url).includes('/download')) {
      return new Response('zip-bytes', {
        status: 200,
        headers: { 'content-type': 'application/zip' },
      })
    }
    return new Response(JSON.stringify({ code: 200, message: 'success', data: { rows: [], total: 0 }, traceId: 't' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }
  const api = createPortalApi(createHttpClient({ baseUrl: '/api', tokenProvider: () => 'token', fetcher }))

  await api.health()
  await api.dashboard.summary()
  await api.generator.tables.list({ keyword: 'sys_user' })
  await api.generator.tables.importable({ keyword: 'sys_file' })
  await api.generator.tables.import({ tableNames: ['sys_file'] })
  await api.generator.tables.columns(3)
  await api.generator.tables.preview(3)
  await api.generator.tables.update(3, { tableComment: '用户表', synced: false })
  await api.generator.tables.generate(3)
  const zip = await api.generator.tables.download(3)

  assert.deepEqual(calls.map(call => `${call.method} ${call.url}`), [
    'GET /api/health',
    'GET /api/dashboard/summary',
    'GET /api/tool/generator/tables?keyword=sys_user',
    'GET /api/tool/generator/importable-tables?keyword=sys_file',
    'POST /api/tool/generator/import',
    'GET /api/tool/generator/tables/3/columns',
    'GET /api/tool/generator/tables/3/preview',
    'PUT /api/tool/generator/tables/3',
    'POST /api/tool/generator/tables/3/generate',
    'GET /api/tool/generator/tables/3/download',
  ])
  assert.equal(await zip.text(), 'zip-bytes')
  assert.deepEqual(JSON.parse(calls[4].body ?? '{}'), { tableNames: ['sys_file'] })
  assert.deepEqual(JSON.parse(calls[7].body ?? '{}'), { tableComment: '用户表', synced: false })
})
