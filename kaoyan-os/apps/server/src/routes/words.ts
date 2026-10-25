import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import type {
  CreateWordInput,
  ReviewGrade,
  SrsState,
  Word,
  WordSource,
  WordSourceSummary,
  WordsBySourceResponse,
  WordWithState,
} from '@kaoyan/shared';
import { WORD_SOURCES } from '@kaoyan/shared';
import { todayStr, addDays } from '../db';
import vocabG from '../seed/words-500.json';
import vocabA from '../data/vocab-500-a.json';
import vocabB from '../data/vocab-500-b.json';
import vocabC from '../data/vocab-500-c.json';
import vocabD from '../data/vocab-500-d.json';
import vocabE from '../data/words-05.json';
import vocabF from '../data/words-06.json';

// 词库 JSON 条目结构
interface VocabEntry {
  word: string;
  phonetic?: string;
  pos?: string;
  meanings_zh: string[];
  example_en?: string;
  example_zh?: string;
  memory_tip?: string;
}

// 逐条校验词库条目，合法返回 null，否则返回错误信息
export function validateVocabEntry(
  entry: unknown,
  index: number,
  file: string,
): string | null {
  if (entry === null || typeof entry !== 'object') {
    return `${file} #${index}: 条目必须为对象`;
  }
  const e = entry as Record<string, unknown>;
  const rawWord = e.word;
  if (typeof rawWord !== 'string' || !rawWord.trim()) {
    return `${file} #${index}: word 必须为非空字符串`;
  }
  const rawMeanings = e.meanings_zh;
  if (!Array.isArray(rawMeanings) || rawMeanings.length === 0) {
    return `${file} #${index}: meanings_zh 必须为非空数组`;
  }
  for (let i = 0; i < rawMeanings.length; i += 1) {
    const m = rawMeanings[i];
    if (typeof m !== 'string' || !m.trim()) {
      return `${file} #${index}: meanings_zh[${i}] 必须为非空字符串`;
    }
  }
  const optionalStrings: { key: string; value: unknown }[] = [
    { key: 'phonetic', value: e.phonetic },
    { key: 'pos', value: e.pos },
    { key: 'example_en', value: e.example_en },
    { key: 'example_zh', value: e.example_zh },
    { key: 'memory_tip', value: e.memory_tip },
  ];
  for (const { key, value } of optionalStrings) {
    if (value !== undefined && typeof value !== 'string') {
      return `${file} #${index}: ${key} 若提供必须为字符串`;
    }
  }
  return null;
}

// 数据库行类型
interface WordRow {
  id: number;
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
  source: string;
  memory_tip: string;
}

interface SrsRow {
  word_id: number;
  ease: number;
  interval_days: number;
  repetitions: number;
  due_date: string;
}

interface WordWithStateRow extends WordRow {
  word_id_srs: number | null;
  ease: number | null;
  interval_days: number | null;
  repetitions: number | null;
  due_date: string | null;
}

// 单词导入项
interface WordImportItem {
  word: string;
  phonetic?: string;
  pos?: string;
  meanings_zh: string[];
  example_en?: string;
  example_zh?: string;
}

// 将 JOIN 行转换为 WordWithState
function toWordWithState(row: WordWithStateRow): WordWithState {
  const word: Word = {
    id: row.id,
    word: row.word,
    phonetic: row.phonetic,
    meaning: row.meaning,
    example: row.example,
    source: row.source as WordSource,
    memory_tip: row.memory_tip,
  };
  const state: SrsState = {
    wordId: row.id,
    ease: row.ease ?? 2.5,
    intervalDays: row.interval_days ?? 0,
    repetitions: row.repetitions ?? 0,
    dueDate: row.due_date ?? todayStr(),
  };
  return { ...word, state };
}

// 读取单个词的 WordWithState
function getWordWithState(db: DatabaseSync, id: number, userId: number): WordWithState | null {
  const row = db
    .prepare(
      `SELECT w.id, w.word, w.phonetic, w.meaning, w.example, w.source, w.memory_tip,
              s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
       FROM words w
       LEFT JOIN srs_state s ON s.word_id = w.id
       WHERE w.id = ? AND w.user_id = ?`,
    )
    .get(id, userId) as WordWithStateRow | undefined;
  if (!row) return null;
  return toWordWithState(row);
}

export interface VocabFile {
  file: string;
  entries: unknown[];
}

export interface VocabSeedResult {
  imported: number;
  skippedExisting: number;
  skippedInvalid: number;
  errors: Array<{ file: string; index: number; message: string }>;
}

export function seedVocabFromEntries(
  db: DatabaseSync,
  files: VocabFile[],
  userId: number,
): VocabSeedResult {
  const errors: Array<{ file: string; index: number; message: string }> = [];
  const validEntries: Array<{ file: string; entry: VocabEntry }> = [];
  for (const { file, entries } of files) {
    for (let index = 0; index < entries.length; index += 1) {
      const message = validateVocabEntry(entries[index], index, file);
      if (message !== null) {
        errors.push({ file, index, message });
      } else {
        validEntries.push({ file, entry: entries[index] as VocabEntry });
      }
    }
  }

  const skippedInvalid = errors.length;

  let imported = 0;
  let skippedExisting = 0;

  const findWord = db.prepare('SELECT id FROM words WHERE user_id = ? AND word = ?');
  const insertWord = db.prepare(
    'INSERT INTO words (user_id, word, phonetic, meaning, example, source, memory_tip) VALUES (?, ?, ?, ?, ?, ?, ?)',
  );
  const insertSrs = db.prepare(
    'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
  );

  const today = todayStr();

  db.exec('BEGIN');
  try {
    for (const { entry } of validEntries) {
      const word = entry.word.trim();
      const existing = findWord.get(userId, word) as { id: number } | undefined;
      if (existing) {
        skippedExisting += 1;
        continue;
      }

      const pos = typeof entry.pos === 'string' ? entry.pos.trim() : '';
      const meanings = entry.meanings_zh.map((m) => m.trim());
      const meaning = (pos ? pos + ' ' : '') + meanings.join('；');

      const exampleEn =
        typeof entry.example_en === 'string' ? entry.example_en.trim() : '';
      const exampleZh =
        typeof entry.example_zh === 'string' ? entry.example_zh.trim() : '';
      let example = exampleEn;
      if (exampleZh) {
        example += ' ｜ ' + exampleZh;
      }

      const phonetic =
        typeof entry.phonetic === 'string' ? entry.phonetic.trim() : '';
      const memoryTip =
        typeof entry.memory_tip === 'string' ? entry.memory_tip.trim() : '';

      const info = insertWord.run(
        userId,
        word,
        phonetic,
        meaning,
        example,
        'core500',
        memoryTip,
      );
      const newId = Number(info.lastInsertRowid);
      insertSrs.run(newId, 2.5, 0, 0, today);
      imported += 1;
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }

  return { imported, skippedExisting, skippedInvalid, errors };
}

export function getBundledVocabFiles(): VocabFile[] {
  return [
    { file: 'vocab-500-a.json', entries: vocabA as unknown[] },
    { file: 'vocab-500-b.json', entries: vocabB as unknown[] },
    { file: 'vocab-500-c.json', entries: vocabC as unknown[] },
    { file: 'vocab-500-d.json', entries: vocabD as unknown[] },
    { file: 'words-05.json', entries: vocabE as unknown[] },
    { file: 'words-06.json', entries: vocabF as unknown[] },
    { file: 'words-500.json', entries: vocabG as unknown[] },
  ];
}

export function registerWordsRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // GET /api/words：全部单词（含 SRS 状态），按 id 升序
  app.get('/api/words', async (request) => {
    const userId = request.user!.id;
    const rows = db
      .prepare(
        `SELECT w.id, w.word, w.phonetic, w.meaning, w.example, w.source, w.memory_tip,
                s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
         FROM words w
         LEFT JOIN srs_state s ON s.word_id = w.id
         WHERE w.user_id = ?
         ORDER BY w.id ASC`,
      )
      .all(userId) as unknown as WordWithStateRow[];
    return rows.map(toWordWithState);
  });

  // GET /api/words/due：今天到期的单词，按 due_date、id 升序
  app.get('/api/words/due', async (request) => {
    const userId = request.user!.id;
    const today = todayStr();
    const rows = db
      .prepare(
        `SELECT w.id, w.word, w.phonetic, w.meaning, w.example, w.source, w.memory_tip,
                s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
         FROM words w
         JOIN srs_state s ON s.word_id = w.id
         WHERE w.user_id = ? AND s.due_date <= ?
         ORDER BY s.due_date ASC, w.id ASC`,
      )
      .all(userId, today) as unknown as WordWithStateRow[];
    return rows.map(toWordWithState);
  });

  // GET /api/words/summary/by-source：按来源汇总（总数/到期/未开始），仅返回有单词的来源，按 WORD_SOURCES 顺序排列
  app.get('/api/words/summary/by-source', async (request) => {
    const userId = request.user!.id;
    const today = todayStr();
    const rows = db
      .prepare(
        `SELECT w.source,
                COUNT(*) AS total,
                SUM(CASE WHEN s.word_id IS NOT NULL AND s.due_date <= ? THEN 1 ELSE 0 END) AS due,
                SUM(CASE WHEN s.word_id IS NULL THEN 1 ELSE 0 END) AS notStarted
         FROM words w
         LEFT JOIN srs_state s ON s.word_id = w.id
         WHERE w.user_id = ?
         GROUP BY w.source`,
      )
      .all(today, userId) as Array<{ source: string; total: number; due: number; notStarted: number }>;
    const rowMap = new Map(rows.map((r) => [r.source, r]));
    const sources: WordSourceSummary[] = [];
    for (const source of Object.keys(WORD_SOURCES) as WordSource[]) {
      const row = rowMap.get(source);
      if (row && row.total > 0) {
        sources.push({ source, total: row.total, due: row.due, notStarted: row.notStarted });
      }
    }
    const result: WordsBySourceResponse = { sources };
    return result;
  });

  // POST /api/words：创建单词并初始化 SRS 状态
  app.post<{ Body: CreateWordInput }>('/api/words', async (request, reply) => {
    const body = request.body ?? ({} as CreateWordInput);
    const word = typeof body.word === 'string' ? body.word.trim() : '';
    const meaning = typeof body.meaning === 'string' ? body.meaning.trim() : '';
    const phonetic = typeof body.phonetic === 'string' ? body.phonetic : '';
    const example = typeof body.example === 'string' ? body.example : '';

    if (!word) {
      return reply.code(400).send({ error: 'word 不能为空' });
    }
    if (!meaning) {
      return reply.code(400).send({ error: 'meaning 不能为空' });
    }

    // 检查重复
    const existing = db
      .prepare('SELECT id FROM words WHERE user_id = ? AND word = ?')
      .get(request.user!.id, word) as { id: number } | undefined;
    if (existing) {
      return reply.code(409).send({ error: '单词已存在' });
    }

    const today = todayStr();
    const insertWord = db.prepare(
      'INSERT INTO words (user_id, word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?, ?)',
    );
    const insertSrs = db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
    );

    const result = insertWord.run(request.user!.id, word, phonetic, meaning, example, 'manual');
    const newId = Number(result.lastInsertRowid);
    insertSrs.run(newId, 2.5, 0, 0, today);

    const created = getWordWithState(db, newId, request.user!.id);
    return reply.code(201).send(created);
  });

  // POST /api/words/:id/review：按 SM-2 简化规则更新 SRS
  app.post<{ Params: { id: string }; Body: { grade: ReviewGrade } }>(
    '/api/words/:id/review',
    async (request, reply) => {
      const id = Number(request.params.id);
      if (!Number.isInteger(id) || id <= 0) {
        return reply.code(400).send({ error: 'id 无效' });
      }
      const body = request.body ?? ({} as { grade: ReviewGrade });
      const grade = body.grade;
      if (grade !== 0 && grade !== 1 && grade !== 2) {
        return reply.code(400).send({ error: 'grade 必须为 0|1|2' });
      }

      const existing = db
        .prepare('SELECT id FROM words WHERE id = ? AND user_id = ?')
        .get(id, request.user!.id) as { id: number } | undefined;
      if (!existing) {
        return reply.code(404).send({ error: '单词不存在' });
      }

      // 获取当前 SRS 状态（若无则初始化默认）
      const srs = db
        .prepare(
          'SELECT word_id, ease, interval_days, repetitions, due_date FROM srs_state WHERE word_id = ?',
        )
        .get(id) as SrsRow | undefined;

      let ease = srs?.ease ?? 2.5;
      let intervalDays = srs?.interval_days ?? 0;
      let repetitions = srs?.repetitions ?? 0;

      if (grade === 0) {
        repetitions = 0;
        intervalDays = 1;
        ease = Math.max(1.3, ease - 0.2);
      } else if (grade === 1) {
        intervalDays = repetitions === 0 ? 1 : Math.max(1, Math.round(intervalDays * 1.2));
        repetitions += 1;
        ease = Math.max(1.3, ease - 0.05);
      } else {
        // grade === 2
        if (repetitions === 0) {
          intervalDays = 1;
        } else if (repetitions === 1) {
          intervalDays = 3;
        } else {
          intervalDays = Math.round(intervalDays * ease);
        }
        repetitions += 1;
        ease = Math.min(2.5, ease + 0.05);
      }

      const dueDate = addDays(todayStr(), intervalDays);

      if (srs) {
        db.prepare(
          `UPDATE srs_state SET ease = ?, interval_days = ?, repetitions = ?, due_date = ?
           WHERE word_id = ? AND EXISTS (SELECT 1 FROM words WHERE words.id = srs_state.word_id AND words.user_id = ?)`,
        ).run(ease, intervalDays, repetitions, dueDate, id, request.user!.id);
      } else {
        db.prepare(
          'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
        ).run(id, ease, intervalDays, repetitions, dueDate);
      }

      const updated = getWordWithState(db, id, request.user!.id);
      return reply.send(updated);
    },
  );

  // POST /api/words/import：批量导入词库
  app.post<{ Body: { words?: unknown; source?: unknown } }>(
    '/api/words/import',
    { bodyLimit: 5 * 1024 * 1024 },
    async (request, reply) => {
      const body = request.body;
      if (body === null || typeof body !== 'object') {
        return reply.code(400).send({ error: 'words 必须为 1..2000 的数组' });
      }
      const rawWords = (body as { words?: unknown }).words;
      if (!Array.isArray(rawWords) || rawWords.length < 1 || rawWords.length > 2000) {
        return reply.code(400).send({ error: 'words 必须为 1..2000 的数组' });
      }

      const rawSource = (body as { source?: unknown }).source;
      const source: string =
        rawSource === undefined || rawSource === null
          ? 'core500'
          : typeof rawSource === 'string'
            ? rawSource
            : '';
      if (!Object.keys(WORD_SOURCES).includes(source)) {
        return reply.code(400).send({ error: 'source 无效' });
      }

      let imported = 0;
      let skippedExisting = 0;
      let skippedInvalid = 0;
      const errors: { index: number; message: string }[] = [];

      const findWord = db.prepare('SELECT id FROM words WHERE user_id = ? AND word = ?');
      const insertWord = db.prepare(
        'INSERT INTO words (user_id, word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?, ?)',
      );
      const insertSrs = db.prepare(
        'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
      );

      const seen = new Set<string>();
      const today = todayStr();

      db.exec('BEGIN');
      try {
        for (let index = 0; index < rawWords.length; index += 1) {
          const item = rawWords[index] as WordImportItem;
          if (item === null || typeof item !== 'object') {
            skippedInvalid += 1;
            if (errors.length < 50) {
              errors.push({ index, message: '条目必须为对象' });
            }
            continue;
          }
          const rawWord = (item as { word?: unknown }).word;
          const word = typeof rawWord === 'string' ? rawWord.trim() : '';
          if (!word) {
            skippedInvalid += 1;
            if (errors.length < 50) {
              errors.push({ index, message: 'word 不能为空' });
            }
            continue;
          }
          const rawMeanings = (item as { meanings_zh?: unknown }).meanings_zh;
          if (!Array.isArray(rawMeanings) || rawMeanings.length === 0) {
            skippedInvalid += 1;
            if (errors.length < 50) {
              errors.push({ index, message: 'meanings_zh 必须为非空数组' });
            }
            continue;
          }
          const meanings = rawMeanings.map((m) =>
            typeof m === 'string' ? m.trim() : '',
          );
          if (meanings.some((m) => !m)) {
            skippedInvalid += 1;
            if (errors.length < 50) {
              errors.push({ index, message: 'meanings_zh 每项必须为非空字符串' });
            }
            continue;
          }

          if (seen.has(word)) {
            skippedExisting += 1;
            continue;
          }
          seen.add(word);

          const existing = findWord.get(request.user!.id, word) as { id: number } | undefined;
          if (existing) {
            skippedExisting += 1;
            continue;
          }

          const rawPos = (item as { pos?: unknown }).pos;
          const pos = typeof rawPos === 'string' ? rawPos.trim() : '';
          const meaning = (pos ? pos + ' ' : '') + meanings.join('；');

          const rawExampleEn = (item as { example_en?: unknown }).example_en;
          const exampleEn =
            typeof rawExampleEn === 'string' ? rawExampleEn.trim() : '';
          const rawExampleZh = (item as { example_zh?: unknown }).example_zh;
          const exampleZh =
            typeof rawExampleZh === 'string' ? rawExampleZh.trim() : '';
          let example = exampleEn;
          if (exampleZh) {
            example += ' ｜ ' + exampleZh;
          }

          const rawPhonetic = (item as { phonetic?: unknown }).phonetic;
          const phonetic =
            typeof rawPhonetic === 'string' ? rawPhonetic.trim() : '';

          const info = insertWord.run(request.user!.id, word, phonetic, meaning, example, source);
          const newId = Number(info.lastInsertRowid);
          insertSrs.run(newId, 2.5, 0, 0, today);
          imported += 1;
        }
        db.exec('COMMIT');
      } catch (err) {
        db.exec('ROLLBACK');
        throw err;
      }

      return reply.send({ imported, skippedExisting, skippedInvalid, errors });
    },
  );

  // POST /api/words/seed-vocab：播种内置词库（1000 旧库 + words-500）
  app.post('/api/words/seed-vocab', async (request, reply) => {
    const result = seedVocabFromEntries(db, getBundledVocabFiles(), request.user!.id);
    return reply.send(result);
  });

  // GET /api/words/vocab-status：内置 500 词库统计
  app.get('/api/words/vocab-status', async (request) => {
    const userId = request.user!.id;
    const totalRow = db
      .prepare("SELECT COUNT(*) AS c FROM words WHERE user_id = ? AND source = 'core500'")
      .get(userId) as { c: number };
    const masteredRow = db
      .prepare(
        `SELECT COUNT(*) AS c FROM words w
         JOIN srs_state s ON s.word_id = w.id
         WHERE w.user_id = ? AND w.source = 'core500' AND s.repetitions > 0`,
      )
      .get(userId) as { c: number };
    const total = totalRow.c;
    const mastered = masteredRow.c;
    return { total, mastered, pending: total - mastered };
  });

  // DELETE /api/words/:id：删除单词及其 SRS 状态
  app.delete<{ Params: { id: string } }>('/api/words/:id', async (request, reply) => {
    const id = Number(request.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 无效' });
    }
    const userId = request.user!.id;
    const existing = db
      .prepare('SELECT id FROM words WHERE id = ? AND user_id = ?')
      .get(id, userId) as { id: number } | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '单词不存在' });
    }
    db.prepare('DELETE FROM srs_state WHERE word_id = ?').run(id);
    db.prepare('DELETE FROM words WHERE id = ? AND user_id = ?').run(id, userId);
    return reply.send({ ok: true });
  });
}
