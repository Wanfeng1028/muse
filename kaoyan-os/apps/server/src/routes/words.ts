import type { FastifyInstance } from 'fastify';
import type { DatabaseSync } from 'node:sqlite';
import type {
  CreateWordInput,
  ReviewGrade,
  SrsState,
  Word,
  WordWithState,
} from '@kaoyan/shared';
import { todayStr, addDays } from '../db';

// 数据库行类型
interface WordRow {
  id: number;
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
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

// 将 JOIN 行转换为 WordWithState
function toWordWithState(row: WordWithStateRow): WordWithState {
  const word: Word = {
    id: row.id,
    word: row.word,
    phonetic: row.phonetic,
    meaning: row.meaning,
    example: row.example,
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
function getWordWithState(db: DatabaseSync, id: number): WordWithState | null {
  const row = db
    .prepare(
      `SELECT w.id, w.word, w.phonetic, w.meaning, w.example,
              s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
       FROM words w
       LEFT JOIN srs_state s ON s.word_id = w.id
       WHERE w.id = ?`,
    )
    .get(id) as WordWithStateRow | undefined;
  if (!row) return null;
  return toWordWithState(row);
}

export function registerWordsRoutes(app: FastifyInstance, db: DatabaseSync): void {
  // GET /api/words：全部单词（含 SRS 状态），按 id 升序
  app.get('/api/words', async () => {
    const rows = db
      .prepare(
        `SELECT w.id, w.word, w.phonetic, w.meaning, w.example,
                s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
         FROM words w
         LEFT JOIN srs_state s ON s.word_id = w.id
         ORDER BY w.id ASC`,
      )
      .all() as unknown as WordWithStateRow[];
    return rows.map(toWordWithState);
  });

  // GET /api/words/due：今天到期的单词，按 due_date、id 升序
  app.get('/api/words/due', async () => {
    const today = todayStr();
    const rows = db
      .prepare(
        `SELECT w.id, w.word, w.phonetic, w.meaning, w.example,
                s.word_id AS word_id_srs, s.ease, s.interval_days, s.repetitions, s.due_date
         FROM words w
         JOIN srs_state s ON s.word_id = w.id
         WHERE s.due_date <= ?
         ORDER BY s.due_date ASC, w.id ASC`,
      )
      .all(today) as unknown as WordWithStateRow[];
    return rows.map(toWordWithState);
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
      .prepare('SELECT id FROM words WHERE word = ?')
      .get(word) as { id: number } | undefined;
    if (existing) {
      return reply.code(409).send({ error: '单词已存在' });
    }

    const today = todayStr();
    const insertWord = db.prepare(
      'INSERT INTO words (word, phonetic, meaning, example) VALUES (?, ?, ?, ?)',
    );
    const insertSrs = db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
    );

    const result = insertWord.run(word, phonetic, meaning, example);
    const newId = Number(result.lastInsertRowid);
    insertSrs.run(newId, 2.5, 0, 0, today);

    const created = getWordWithState(db, newId);
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
        .prepare('SELECT id FROM words WHERE id = ?')
        .get(id) as { id: number } | undefined;
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
        ease = ease + 0.05;
      }

      const dueDate = addDays(todayStr(), intervalDays);

      if (srs) {
        db.prepare(
          'UPDATE srs_state SET ease = ?, interval_days = ?, repetitions = ?, due_date = ? WHERE word_id = ?',
        ).run(ease, intervalDays, repetitions, dueDate, id);
      } else {
        db.prepare(
          'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)',
        ).run(id, ease, intervalDays, repetitions, dueDate);
      }

      const updated = getWordWithState(db, id);
      return reply.send(updated);
    },
  );

  // DELETE /api/words/:id：删除单词及其 SRS 状态
  app.delete<{ Params: { id: string } }>('/api/words/:id', async (request, reply) => {
    const id = Number(request.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({ error: 'id 无效' });
    }
    const existing = db
      .prepare('SELECT id FROM words WHERE id = ?')
      .get(id) as { id: number } | undefined;
    if (!existing) {
      return reply.code(404).send({ error: '单词不存在' });
    }
    db.prepare('DELETE FROM srs_state WHERE word_id = ?').run(id);
    db.prepare('DELETE FROM words WHERE id = ?').run(id);
    return reply.send({ ok: true });
  });
}
