import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { DatabaseSync } from 'node:sqlite';
import {
  seedVocabFromEntries,
  validateVocabEntry,
} from '../src/routes/words';
import { todayStr, createDb } from '../src/db';

let db: DatabaseSync;
let testUserId: number;

function countWords(database: DatabaseSync): number {
  const row = database
    .prepare("SELECT COUNT(*) AS c FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'local')")
    .get() as { c: number };
  return row.c;
}

function countSrs(database: DatabaseSync): number {
  const row = database
    .prepare("SELECT COUNT(*) AS c FROM srs_state WHERE word_id IN (SELECT id FROM words WHERE user_id = (SELECT id FROM users WHERE username = 'local'))")
    .get() as { c: number };
  return row.c;
}

beforeEach(() => {
  db = createDb(':memory:');
  testUserId = (db.prepare("SELECT id FROM users WHERE username = 'local'").get() as { id: number }).id;
});


afterEach(() => {
  db.close();
});

describe('seedVocabFromEntries 词库播种第二轮纵深测试', () => {
  it('合成 2000 条大数据量幂等：首次全导入，二次零新增', () => {
    const entries: unknown[] = [];
    for (let i = 0; i < 2000; i += 1) {
      entries.push({
        word: `syn-word-${i}`,
        meanings_zh: ['释义一', '释义二'],
      });
    }
    const files = [{ file: 'syn-2000.json', entries }];

    const first = seedVocabFromEntries(db, files, testUserId);
    expect(first.imported).toBe(2000);

    expect(first.skippedExisting).toBe(0);
    expect(first.skippedInvalid).toBe(0);
    expect(first.errors).toEqual([]);
    expect(countWords(db)).toBe(2000);
    expect(countSrs(db)).toBe(2000);

    const second = seedVocabFromEntries(db, files, testUserId);
    expect(second.imported).toBe(0);

    expect(second.skippedExisting).toBe(2000);
    expect(second.skippedInvalid).toBe(0);
    expect(countWords(db)).toBe(2000);
  });

  it('非法条目跳过记数精确：imported=2, skippedInvalid=7, errors 下标对齐', () => {
    const entries: unknown[] = [
      { word: 'ok-one', meanings_zh: ['好'] },
      null,
      'not-an-object',
      { word: '', meanings_zh: ['x'] },
      { word: 'no-meanings' },
      { word: 'empty-meanings', meanings_zh: [] },
      { word: 'blank-meaning', meanings_zh: [''] },
      { word: 'bad-opt', meanings_zh: ['x'], phonetic: 123 },
      { word: 'ok-two', meanings_zh: ['好', '很好'] },
    ];

    const result = seedVocabFromEntries(db, [
      { file: 'mix.json', entries },
    ], testUserId);


    expect(result.imported).toBe(2);
    expect(result.skippedExisting).toBe(0);
    expect(result.skippedInvalid).toBe(7);
    expect(result.errors.length).toBe(7);
    expect(result.errors[0]).toEqual({
      file: 'mix.json',
      index: 1,
      message: 'mix.json #1: 条目必须为对象',
    });

    const expectedIndices = [1, 2, 3, 4, 5, 6, 7];
    for (let i = 0; i < result.errors.length; i += 1) {
      expect(result.errors[i].file).toBe('mix.json');
      expect(result.errors[i].index).toBe(expectedIndices[i]);
    }

    expect(countWords(db)).toBe(2);
  });

  it('空文件列表与空条目数组：全零返回且不抛错', () => {
    const emptyFiles = seedVocabFromEntries(db, [], testUserId);

    expect(emptyFiles.imported).toBe(0);
    expect(emptyFiles.skippedExisting).toBe(0);
    expect(emptyFiles.skippedInvalid).toBe(0);
    expect(emptyFiles.errors).toEqual([]);

    const missingFile = seedVocabFromEntries(db, [
      { file: 'missing.json', entries: [] },
    ], testUserId);

    expect(missingFile.imported).toBe(0);
    expect(missingFile.skippedExisting).toBe(0);
    expect(missingFile.skippedInvalid).toBe(0);
    expect(missingFile.errors).toEqual([]);

    expect(countWords(db)).toBe(0);
  });

  it('错误详情格式精确：word 空白报错文案与下标一致', () => {
    const result = seedVocabFromEntries(db, [
      { file: 'f.json', entries: [{ word: '  ', meanings_zh: ['x'] }] },
    ], testUserId);


    expect(result.errors.length).toBe(1);
    expect(result.errors[0]).toEqual({
      file: 'f.json',
      index: 0,
      message: 'f.json #0: word 必须为非空字符串',
    });
    expect(result.skippedInvalid).toBe(1);
    expect(result.imported).toBe(0);
  });

  it('大数据量落库字段正确：meaning/source/srs 精确校验', () => {
    const entries: unknown[] = [
      {
        word: 'field-one',
        meanings_zh: ['意思一', '意思二'],
        pos: 'n.',
        example_en: 'This is one.',
        example_zh: '这是一个。',
        memory_tip: '记忆一',
      },
      {
        word: 'field-two',
        meanings_zh: ['含义二'],
        pos: 'v.',
        example_en: 'This is two.',
        example_zh: '这是两个。',
        memory_tip: '记忆二',
      },
      {
        word: 'field-three',
        meanings_zh: ['含义三', '含义四'],
        pos: 'adj.',
        example_en: 'This is three.',
        example_zh: '这是三个。',
        memory_tip: '记忆三',
      },
    ];

    const result = seedVocabFromEntries(db, [
      { file: 'fields.json', entries },
    ], testUserId);
    expect(result.imported).toBe(3);


    const wordRow = db
      .prepare(
        "SELECT id, meaning, source FROM words WHERE word = ? AND user_id = (SELECT id FROM users WHERE username = 'local')",
      )
      .get('field-one') as

      | { id: number; meaning: string; source: string }
      | undefined;
    expect(wordRow).toBeDefined();
    expect(wordRow!.meaning).toBe('n. 意思一；意思二');
    expect(wordRow!.source).toBe('core500');

    const srsRow = db
      .prepare(
        'SELECT ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?',
      )
      .get(wordRow!.id) as
      | {
          ease: number;
          interval_days: number;
          repetitions: number;
          due_date: string;
        }
      | undefined;
    expect(srsRow).toBeDefined();
    expect(srsRow!.ease).toBeCloseTo(2.5, 10);
    expect(srsRow!.repetitions).toBe(0);
    expect(srsRow!.interval_days).toBe(0);
    expect(srsRow!.due_date).toBe(todayStr());

    expect(validateVocabEntry(entries[0], 0, 'fields.json')).toBeNull();
  });
});