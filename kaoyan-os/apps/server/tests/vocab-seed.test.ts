import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { buildApp } from '../src/app';
import { validateVocabEntry } from '../src/routes/words';
import vocabA from '../src/data/vocab-500-a.json';
import vocabB from '../src/data/vocab-500-b.json';
import vocabC from '../src/data/vocab-500-c.json';
import vocabD from '../src/data/vocab-500-d.json';
import vocabE from '../src/data/words-05.json';
import vocabF from '../src/data/words-06.json';

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

describe('POST /api/words/seed-vocab', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    app = await buildApp({ dbPath: ':memory:' });
  });

  afterEach(async () => {
    await app.close();
  });

  it('首次导入 imported=1000', async () => {
    const res = await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(1000);
    expect(body.skippedExisting).toBe(0);
    expect(body.skippedInvalid).toBe(0);
    expect(body.errors).toEqual([]);
  });

  it('第二次调用 imported=0 且 skippedExisting=1000', async () => {
    await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    const res = await app.inject({ method: 'POST', url: '/api/words/seed-vocab' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.imported).toBe(0);
    expect(body.skippedExisting).toBe(1000);
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
    const entry = (files.flatMap((f) => f.data) as Record<string, unknown>[]).find(
      (e) => e.word === sample.word,
    );
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

  it('memory_tip 非空透出（仅 core500 词）', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words' });
    const words = res.json();
    const vocab = words.filter((w: { source: string }) => w.source === 'core500');
    expect(vocab.length).toBe(1000);
    for (const w of vocab) {
      expect(typeof w.memory_tip).toBe('string');
      expect((w.memory_tip as string).length > 0).toBe(true);
    }
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

  it('初始 total=1000 mastered=0 pending=1000', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/words/vocab-status' });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ total: 1000, mastered: 0, pending: 1000 });
  });

  it('复习 3 个词后 mastered=3 pending=997', async () => {
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
    expect(res.json()).toEqual({ total: 1000, mastered: 3, pending: 997 });
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
