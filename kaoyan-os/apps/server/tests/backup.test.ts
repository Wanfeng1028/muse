import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { buildApp } from '../src/app';
import { registerAndLogin } from './test-utils';
import type { FastifyInstance } from 'fastify';

let app: FastifyInstance;

  let authCookie = '';
beforeAll(async () => {
  app = await buildApp({ dbPath: ':memory:' });
  await app.ready();

  authCookie = await registerAndLogin(app, 'backuptest');});

afterAll(async () => {
  await app.close();
});

const SEVEN_TABLES = [
  'plans',
  'focus_sessions',
  'mistakes',
  'words',
  'srs_state',
  'exam_records',
  'settings',
];

describe('backup export', () => {
  it('returns format/version/tables with 7 tables', async () => {
    const res = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/backup/export' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.format).toBe('kaoyan-backup');
    expect(body.version).toBe(1);
    const keys = Object.keys(body.tables);
    for (const t of SEVEN_TABLES) {
      expect(keys).toContain(t);
    }
  });
});

describe('backup import replace roundtrip', () => {
  it('imports modified payload and updates word meaning', async () => {
    const create = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/words',
      payload: { word: 'zztestword1', meaning: 'zz原含义' },
    });
    expect([200, 201]).toContain(create.statusCode);

    const exp = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/backup/export' });
    expect(exp.statusCode).toBe(200);
    const payload = exp.json();

    const target = payload.tables.words.find(
      (w: any) => w.word === 'zztestword1'
    );
    expect(target).toBeTruthy();
    target.meaning = 'zz改后含义';

    const imp = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: payload },
    });
    expect(imp.statusCode).toBe(200);
    const impBody = imp.json();
    expect(impBody.imported.words).toBeGreaterThanOrEqual(1);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    expect(list.statusCode).toBe(200);
    const listBody = list.json();
    const words = Array.isArray(listBody) ? listBody : listBody.words ?? listBody.data ?? [];
    const found = words.find((w: any) => w.word === 'zztestword1');
    expect(found).toBeTruthy();
    expect(found.meaning).toBe('zz改后含义');
  });
});

describe('backup import validation', () => {
  it('rejects invalid format and does not write', async () => {
    const before = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    const beforeBody = before.json();
    const beforeWords = Array.isArray(beforeBody)
      ? beforeBody
      : beforeBody.words ?? beforeBody.data ?? [];
    expect(beforeWords.find((w: any) => w.word === 'zztestword1')).toBeTruthy();

    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: { format: 'nope', version: 1, tables: {} } },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBeTruthy();

    const after = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    const afterBody = after.json();
    const afterWords = Array.isArray(afterBody)
      ? afterBody
      : afterBody.words ?? afterBody.data ?? [];
    expect(afterWords.find((w: any) => w.word === 'zztestword1')).toBeTruthy();
  });

  it('rejects version !== 1', async () => {
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: { format: 'kaoyan-backup', version: 2, tables: {} } },
    });
    expect(res.statusCode).toBe(400);
  });

  it('rejects invalid row with table name in error', async () => {
    const exp = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/backup/export' });
    const payload = exp.json();
    payload.tables.mistakes.push({ subject: 'nonsense', title: 'x' });
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: payload },
    });
    expect(res.statusCode).toBe(400);
    expect(String(res.json().error)).toContain('mistakes');
  });
});

describe('backup import merge', () => {
  it('skips existing words and imports new ones with autoincrement id', async () => {
    const exp = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/backup/export' });
    const payload = exp.json();

    const merge1 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: payload, mode: 'merge' },
    });
    expect(merge1.statusCode).toBe(200);
    const m1 = merge1.json();
    expect(m1.skipped.words).toBeGreaterThan(0);
    expect(m1.imported.words).toBe(0);

    payload.tables.words.push({
      id: 99999,
      word: 'zzmergenew',
      meaning: 'zzmerge含义',
    });

    const merge2 = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/backup/import',
      payload: { data: payload, mode: 'merge' },
    });
    expect(merge2.statusCode).toBe(200);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    const listBody = list.json();
    const words = Array.isArray(listBody)
      ? listBody
      : listBody.words ?? listBody.data ?? [];
    const found = words.find((w: any) => w.word === 'zzmergenew');
    expect(found).toBeTruthy();
    expect(found.meaning).toBe('zzmerge含义');
  });
});

describe('POST /api/import/words', () => {
  it('imports valid CSV with quoted commas', async () => {
    const csv =
      'word,phonetic,meaning,example\nzzcsv1,,csv含义一,\nzzcsv2,/x/,csv含义二,"带,逗号的例句"';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/words',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(2);

    const list = await app.inject({ headers: { cookie: authCookie }, method: 'GET', url: '/api/words' });
    const listBody = list.json();
    const words = Array.isArray(listBody)
      ? listBody
      : listBody.words ?? listBody.data ?? [];
    const w1 = words.find((w: any) => w.word === 'zzcsv1');
    const w2 = words.find((w: any) => w.word === 'zzcsv2');
    expect(w1).toBeTruthy();
    expect(w2).toBeTruthy();
    expect(String(w2.example)).toContain(',');
  });

  it('handles duplicates, empty rows and empty meaning', async () => {
    const csv = 'word,phonetic,meaning,example\nzzcsv1,,dup,\n,,空词,\nzzcsv3,,,';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/words',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.skippedExisting).toBe(1);
    expect(body.skippedEmpty).toBe(1);
    expect(body.errorRows).toBe(1);
    expect(body.errors.length).toBeGreaterThanOrEqual(1);
    expect(String(body.errors[0].message)).toContain('meaning');
  });

  it('rejects CSV missing required columns', async () => {
    const csv = 'word,phonetic\nzzx,,';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/words',
      payload: { csv },
    });
    expect(res.statusCode).toBe(400);
  });

  it('handles BOM prefix', async () => {
    const csv = '\uFEFFword,phonetic,meaning,example\nzzbom,,bom含义,';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/words',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);
  });
});

describe('POST /api/import/mistakes', () => {
  it('imports valid mistake CSV', async () => {
    const csv = 'subject,title,content,analysis\nmath,zz错题一,题干,解析';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1);

    const list = await app.inject({ headers: { cookie: authCookie },
      method: 'GET',
      url: '/api/mistakes?q=' + encodeURIComponent('zz错题一'),
    });
    expect(list.statusCode).toBe(200);
    const lb = list.json();
    const arr = Array.isArray(lb) ? lb : lb.mistakes ?? lb.data ?? [];
    expect(arr.find((m: any) => m.title === 'zz错题一')).toBeTruthy();
  });

  it('rejects invalid subject as error row', async () => {
    const csv = 'subject,title\nnonsense,zz坏行';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(0);
    expect(body.errorRows).toBe(1);
  });

  it('rejects empty title as error row', async () => {
    const csv = 'subject,title\nmath,';
    const res = await app.inject({ headers: { cookie: authCookie },
      method: 'POST',
      url: '/api/import/mistakes',
      payload: { csv },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.errorRows).toBe(1);
  });
});
