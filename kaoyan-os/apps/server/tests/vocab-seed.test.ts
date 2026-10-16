
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { DatabaseSync } from 'node:sqlite';
import { buildApp } from '../src/app';
import { createDb } from '../src/db';
import {
  validateVocabEntry,
  seedVocabFromEntries,
  getBundledVocabFiles,
} from '../src/routes/words';
import vocabA from '../src/data/vocab-500-a.json';
import vocabB from '../src/data/vocab-500-b.json';
import vocabC from '../src/data/vocab-500-c.json';
import vocabD from '../src/data/vocab-500-d.json';
import vocabE from '../src/data/words-05.json';
import vocabF from '../src/data/words-06.json';
import words500 from '../src/seed/words-500.json';

const files = [
  { name: 'vocab-500-a.json', data: vocabA as Record<string, unknown>[] },
  { name: 'vocab-500-b.json', data: vocabB as Record<string, unknown>[] },
  { name: 'vocab-500-c.json', data: vocabC as Record<string, unknown>[] },
  { name: 'vocab-500-d.json', data: vocabD as Record<string, unknown>[] },
  { name: 'words-05.json', data: vocabE as Record<string, unknown>[] },
  { name: 'words-06.json', data: vocabF as Record<string, unknown>[] },
];

describe('vocab 1000 词库数据文件', () => {
  it('每个文件条数符合 [125,125,125,125,250,250]', () => {
    const expected = [125, 125, 125, 125, 250, 250];
    for (let i = 0; i < files.length; i += 1) {
      const { data } = files[i];
      expect(Array.isArray(data)).toBe(true);
      expect(data.length).toBe(expected[i]);
    }
  });

  it('六文件合计 1000 条且 word 无重复', () => {
    const all = files.flatMap((f) => f.data);
    expect(all.length).toBe(1000);
    const words = all.map((e) => e.word);
    expect(new Set(words).size).toBe(1000);
  });

  it('每条字段齐全非空', () => {
    for (const { data } of files) {
      for (const e of data) {
        expect(typeof e.word === 'string' && (e.word as string).length > 0).toBe(true);
        expect(typeof e.phonetic === 'string' && (e.phonetic as string).length > 0).toBe(true);
        expect(typeof e.pos === 'string' && (e.pos as string).length > 0).toBe(true);
        expect(Array.isArray(e.meanings_zh)).toBe(true);
        expect((e.meanings_zh as unknown[]).length > 0).toBe(true);
        for (const m of e.meanings_zh as unknown[]) {
          expect(typeof m === 'string' && (m as string).length > 0).toBe(true);
        }
        expect(typeof e.example_en === 'string' && (e.example_en as string).length > 0).toBe(true);
        expect(typeof e.example_zh === 'string' && (e.example_zh as string).length > 0).toBe(true);
        expect(typeof e.memory_tip === 'string' && (e.memory_tip as string).length > 0).toBe(true);
      }
    }
  });

  it('全文件文本不含 <redacted>', () => {
    const text = JSON.stringify(files.map((f) => f.data));
    expect(text.includes('<redacted>')).toBe(false);
  });
});

describe('words-500.json 数据文件', () => {
  const data = words500 as Record<string, unknown>[];

  it('500 条且 word 无重复', () => {
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBe(500);
    const words = data.map((e) => e.word);
    expect(new Set(words).size).toBe(500);
  });

  it('每条 word/phonetic/pos 为非空字符串', () => {
    for (const e of data) {
      expect(typeof e.word === 'string' && (e.word as string).length > 0).toBe(true);
      expect(typeof e.phonetic === 'string' && (e.phonetic as string).length > 0).toBe(true);
      expect(typeof e.pos === 'string' && (e.pos as string).length > 0).toBe(true);
    }
  });

  it('每条 meanings_zh 为非空字符串数组', () => {
    for (const e of data) {
      expect(Array.isArray(e.meanings_zh)).toBe(true);
      expect((e.meanings_zh as unknown[]).length > 0).toBe(true);
      for (const m of e.meanings_zh as unknown[]) {
        expect(typeof m === 'string' && (m as string).length > 0).toBe(true);
      }
    }
  });

  it('每条 example_en/example_zh 为非空字符串', () => {
    for (const e of data) {
      expect(typeof e.example_en === 'string' && (e.example_en as string).length > 0).toBe(true);
      expect(typeof e.example_zh === 'string' && (e.example_zh as string).length > 0).toBe(true);
    }
  });

  it('全文件文本不含 <redacted>', () => {
    const text = JSON.stringify(data);
    expect(text.includes('<redacted>')).toBe(false);
  });
});

describe('POST /api/words/seed-vocab', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    app = await buildApp({ dbPath: ':memory:' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('首次导入 imported=1380 skippedExisting=120', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1380);
    expect(body.skippedExisting).toBe(120);
    expect(body.skippedInvalid).toBe(0);
    expect(body.errors).toEqual([]);
  });

  it('第二次调用 imported=0 且 skippedExisting=1500', async () => {
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    const res = await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(0);
    expect(body.skippedExisting).toBe(1500);
  });

  it('幂等：重复调用后总数不变', async () => {
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    const first = await app.inject({ method: 'GET', url: '/api/words' });
    const firstCount = first.json().length;
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    const second = await app.inject({ method: 'GET', url: '/api/words' });
    expect(second.json().length).toBe(firstCount);
  });
});

describe('导入后的单词字段', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    app = await buildApp({ dbPath: ':memory:' });
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('meaning 拼接为 pos + meanings_zh.join(；)', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words' });
    const words = res.json();
    const sample = words.find((w: { source: string }) => w.source === 'core500');
    expect(sample).toBeTruthy();
    const allEntries = [
      ...files.flatMap((f) => f.data),
      ...(words500 as Record<string, unknown>[]),
    ];
    const entry = allEntries.find((e) => e.word === sample.word);
    expect(entry).toBeTruthy();
    const pos = String(entry!.pos);
    const meanings = (entry!.meanings_zh as string[]).join('；');
    expect(sample.meaning).toBe(pos + ' ' + meanings);
  });

  it('example 含 ｜ 分隔且 source=core500', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words' });
    const words = res.json();
    const sample = words.find((w: { source: string }) => w.source === 'core500');
    expect(sample).toBeTruthy();
    expect(sample.example.includes(' ｜ ')).toBe(true);
    expect(sample.source).toBe('core500');
  });

  it('core500 共 1380 个词，其中 1000 个 memory_tip 非空、380 个为空串', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words' });
    const words = res.json();
    const vocab = words.filter((w: { source: string }) => w.source === 'core500');
    expect(vocab.length).toBe(1380);
    const nonEmpty = vocab.filter(
      (w: { memory_tip: string }) => typeof w.memory_tip === 'string' && w.memory_tip.length > 0,
    );
    const empty = vocab.filter(
      (w: { memory_tip: string }) => typeof w.memory_tip === 'string' && w.memory_tip.length === 0,
    );
    expect(nonEmpty.length).toBe(1000);
    expect(empty.length).toBe(380);
  });
});

describe('GET /api/words/vocab-status', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    app = await buildApp({ dbPath: ':memory:' });
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('初始 total=1380 mastered=0 pending=1380', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words/vocab-status' });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ total: 1380, mastered: 0, pending: 1380 });
  });

  it('复习 3 个词后 mastered=3 pending=1377', async () => {
    const list = await app.inject({ method: 'GET', url: '/api/words' });
    const words = list.json();
    const vocab = words.filter((w: { source: string }) => w.source === 'core500');
    expect(vocab.length).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < 3; i += 1) {
      const r = await app.inject({
        method: 'POST',
        url: `/api/words/${vocab[i].id}/review`,
        payload: { grade: 2 },
      });
      expect(r.statusCode).toBe(200);
    }
    const res = await app.inject({ method: 'GET', url: '/api/words/vocab-status' });
    expect(res.json()).toEqual({ total: 1380, mastered: 3, pending: 1377 });
  });
});

describe('seedVocabFromEntries', () => {
  let db: DatabaseSync;

  beforeEach(() => {
    db = createDb(':memory:');
  });

  afterEach(() => {
    db.close();
  });

  it('坏条目容错：非法条目跳过并记录 errors', () => {
    const result = seedVocabFromEntries(db, [
      {
        file: 'bad.json',
        entries: [
          null,
          { word: '', meanings_zh: ['x'] },
          { word: 'ok1', meanings_zh: ['好'] },
          { word: 'ok2' },
        ],
      },
    ]);
    expect(result.imported).toBe(1);
    expect(result.skippedInvalid).toBe(3);
    expect(result.errors.length).toBe(3);
    for (const err of result.errors) {
      expect(err.file).toBe('bad.json');
    }
    expect(result.errors.map((e) => e.index).sort()).toEqual([0, 1, 3]);
    for (const err of result.errors) {
      expect(typeof err.message).toBe('string');
      expect(err.message.length).toBeGreaterThan(0);
    }
  });

  it('幂等：同一 files 调两次，第二次 imported=0 且库中词数不变', () => {
    const input = [
      {
        file: 'idem.json',
        entries: [
          { word: 'alpha', meanings_zh: ['甲'] },
          { word: 'beta', meanings_zh: ['乙'] },
        ],
      },
    ];
    const first = seedVocabFromEntries(db, input);
    expect(first.imported).toBe(2);
    const countAfterFirst = (
      db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number }
    ).c;
    const second = seedVocabFromEntries(db, input);
    expect(second.imported).toBe(0);
    expect(second.skippedExisting).toBe(2);
    const countAfterSecond = (
      db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number }
    ).c;
    expect(countAfterSecond).toBe(countAfterFirst);
  });

  it('同一批内重复词：第二个走 skippedExisting', () => {
    const result = seedVocabFromEntries(db, [
      {
        file: 'dup.json',
        entries: [
          { word: 'dup', meanings_zh: ['重复'] },
          { word: 'dup', meanings_zh: ['重复'] },
        ],
      },
    ]);
    expect(result.imported).toBe(1);
    expect(result.skippedExisting).toBe(1);
    const count = (
      db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number }
    ).c;
    expect(count).toBe(1);
  });
});

describe('validateVocabEntry', () => {
  it('合法条目返回 null', () => {
    const result = validateVocabEntry(
      {
        word: 'apple',
        phonetic: '/ˈæpl/',
        pos: 'n.',
        meanings_zh: ['苹果'],
        example_en: 'An apple a day.',
        example_zh: '一天一个苹果。',
        memory_tip: '谐音记忆',
      },
      0,
      'test.json',
    );
    expect(result).toBeNull();
  });

  it('word 为空返回含 file 与 index 的错误', () => {
    const result = validateVocabEntry({ word: '', meanings_zh: ['苹果'] }, 5, 'a.json');
    expect(typeof result).toBe('string');
    expect(result).toContain('a.json');
    expect(result).toContain('5');
  });

  it('meanings_zh 缺失返回错误', () => {
    const result = validateVocabEntry({ word: 'apple' }, 2, 'b.json');
    expect(typeof result).toBe('string');
    expect(result).toContain('b.json');
    expect(result).toContain('2');
  });

  it('meanings_zh 空数组返回错误', () => {
    const result = validateVocabEntry({ word: 'apple', meanings_zh: [] }, 3, 'c.json');
    expect(typeof result).toBe('string');
    expect(result).toContain('c.json');
    expect(result).toContain('3');
  });

  it('meanings_zh 含空字符串返回错误', () => {
    const result = validateVocabEntry(
      { word: 'apple', meanings_zh: ['苹果', ''] },
      7,
      'd.json',
    );
    expect(typeof result).toBe('string');
    expect(result).toContain('d.json');
    expect(result).toContain('7');
  });

  it('条目非对象返回错误', () => {
    const result = validateVocabEntry(null, 9, 'e.json');
    expect(typeof result).toBe('string');
    expect(result).toContain('e.json');
    expect(result).toContain('9');
  });
});
