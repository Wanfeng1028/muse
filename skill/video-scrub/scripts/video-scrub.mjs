#!/usr/bin/env node
// video-scrub — 把一条视频重建成「只有画面和声音」的干净文件，源片的元数据一概不搬。
// 零 npm 依赖。需要 node >= 18、ffmpeg/ffprobe。

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { basename } from 'node:path';
import { fileURLToPath } from 'node:url';

/* ------------------------------------------------------------------ */
/* 原理                                                                */
/* ------------------------------------------------------------------ */
/*
 * 清元数据有两种思路，这里只用后一种：
 *
 *   黑名单——列出要删的字段逐个删。**删不完你不知道的东西**：厂商私有的 udta、
 *            GoPro 的遥测轨、码流里的 SEI，漏一个就漏了。
 *   白名单——不说删什么，只说带什么过去：**画面一条流、声音一条流，别的一律不要**。
 *            源片的元数据没有任何通道能进来。隐私保证来自结构，不来自枚举。
 *
 * 但 ffmpeg 默认会背叛这个结构两次，必须摁住：
 *
 *   1. 它默认把源片的容器 tag 搬到输出   → -map_metadata -1
 *   2. 它默认自动挑流，会把 GoPro 的 gpmd 遥测轨一起带走 → -map 0:v:0 -map 0:a:0?
 *
 * 摁住之后文件是「无名」的，profile 决定往回写什么（见 PROFILES）。
 *
 * 然后 ffmpeg 会把**自己的**身份写进五个地方，ffprobe 只看得见第一处，
 * 全部堵法见 references/residue-map.md。
 */

export const MODES = {
  // copy 模式下**画面逐字节照搬**（实测：抽出的 H.264 码流与源片 cmp 一致），
  // 但音频必须重编一遍——ffmpeg 的 AAC 把自己的版本号写在 DSE 里，那是码流内部，
  // 不重编就抹不掉。音频重编很便宜，几十秒的片子不到一秒。
  copy: '画面逐字节照搬、只重编音频：画质零损失、快几十倍，元数据一样清干净',
  encode: '完整重编码：像素重算，连码流域的东西也一并没了，代价是有损 + 慢',
};

/**
 * profile：擦白之后往回写的那一层。
 *
 * 有一件事 ffmpeg 不让做：容器的 `encoder` 字段由 muxer 自己占着，
 * `-metadata encoder=Lavf60.16.100` 盖不过去，置空也清不掉（实测）。
 * 只有 `-fflags +bitexact` 能让它整个消失。所以 obs 档不伪造版本号——
 * 它就让 ffmpeg 写自己的真版本号，反正 OBS 产出的本来也是 ffmpeg 封装的文件，
 * 两者同类。其余档一律 bitexact，连这个字段都不留。
 */
export const PROFILES = {
  obs: {
    label: 'OBS Studio 录制',
    containerBitexact: false,        // 留着 ffmpeg 自己的 Lavf 版本号
    expectEncoder: /^Lavf\d+\./,
    videoHandler: 'VideoHandler',
    audioHandler: 'SoundHandler',
    setCreationTime: true,
  },
  quicktime: {
    label: 'macOS QuickTime 录屏',
    containerBitexact: true,
    expectEncoder: null,
    videoHandler: 'Core Media Video',
    audioHandler: 'Core Media Audio',
    setCreationTime: true,
  },
  screencapture: {
    label: 'macOS ScreenCaptureKit 录屏',
    containerBitexact: true,
    expectEncoder: null,
    videoHandler: 'Core Media Video',
    audioHandler: 'Core Media Audio',
    setCreationTime: true,
  },
  bare: {
    label: '无名——什么都不写',
    // 隐私强度最高：不写任何可被证伪的声明。handler 用单空格，置空会退回 ffmpeg 默认值。
    containerBitexact: true,
    expectEncoder: null,
    videoHandler: ' ',
    audioHandler: ' ',
    setCreationTime: false,
  },
};

export const DEFAULT_PARAMS = {
  mode: 'copy',
  profile: 'obs',
  crf: 18,               // 只在 encode 模式用
  minNeedleBytes: 5,     // 针短于它就不扫：压缩数据里会随机撞出假阳性
  durationTolerance: 0.5,
};

/**
 * 结构性 tag：描述容器怎么组装的，不是隐私，也不当「针」。
 * major_brand 这种值输出里必然还会出现，拿它当针会自己扎自己。
 */
export const STRUCTURAL_TAGS = new Set([
  'major_brand', 'minor_version', 'compatible_brands', 'language',
]);

/**
 * 通用串：**这一类工具产出的每个文件里都有**，识别不出任何人、任何设备、任何账号。
 *
 * 它们既不当针，也不算 tag 层残留——否则 obs 档写回 `VideoHandler` 会被自己的门拦下，
 * 而那个字符串的信息量是零。分界线：能不能把范围缩小到某个人、某台设备、某次导出。
 * `Lavf58.45.100` 能（它钉死了一个版本），`VideoHandler` 不能（满世界都是）。
 */
export const GENERIC_STRINGS = new Set([
  'VideoHandler', 'SoundHandler', 'DataHandler',
  'Core Media Video', 'Core Media Audio', 'Core Media Data',
  'handler_name', 'encoder', 'language', 'und', 'eng',
]);

/** 这个键值对能不能把范围缩小到某个人／设备／某次导出。 */
export function isIdentifying(key, value) {
  const k = String(key ?? '').toLowerCase();
  if (STRUCTURAL_TAGS.has(k)) return false;
  const v = String(value ?? '').trim();
  if (!v) return false;
  return !GENERIC_STRINGS.has(v);
}

/** 已知的工具身份串。码流层查到这些 = 有编码器把自己的名字写进去了。 */
export const TOOL_MARKS = [
  'x264 - core', 'x265', 'Lavc', 'Lavf', 'libavcodec', 'libavformat',
  'HandBrake', 'Xvid', 'DivX',
];

/** 位置类字段：一个都不许有。 */
export const LOCATION_KEYS = [
  'location', 'location-eng', 'com.apple.quicktime.location.iso6109',
  'com.apple.quicktime.location.iso6709', 'gps', 'gpslatitude', 'gpslongitude',
  'gpscoordinates', 'xyz', '©xyz',
];

/** 设备与软件类字段：泄露你用什么拍的、什么账号导的。 */
export const DEVICE_KEYS = [
  'make', 'model', 'software', 'com.apple.quicktime.make',
  'com.apple.quicktime.model', 'com.apple.quicktime.software',
  'com.android.version', 'device', 'artist', 'author', 'copyright',
  'comment', 'description', 'title', 'album', 'composer', 'performer',
  'encoded_by', 'creation_time', 'date',
];

const r2 = (n) => Math.round(n * 100) / 100;

/* ------------------------------------------------------------------ */
/* 探测                                                                */
/* ------------------------------------------------------------------ */

/** ffprobe 全量：format / streams / chapters，一次拿全。 */
export function probe(file) {
  const out = execFileSync('ffprobe', [
    '-v', 'error', '-print_format', 'json',
    '-show_format', '-show_streams', '-show_chapters',
    file,
  ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const j = JSON.parse(out);
  const streams = j.streams ?? [];
  const video = streams.find((s) => s.codec_type === 'video') ?? null;
  return {
    file,
    durationSeconds: r2(Number(j.format?.duration ?? 0)),
    sizeBytes: Number(j.format?.size ?? 0),
    formatTags: j.format?.tags ?? {},
    chapters: j.chapters ?? [],
    streams: streams.map((s) => ({
      index: s.index,
      type: s.codec_type,
      codec: s.codec_name ?? null,
      tags: s.tags ?? {},
      sideData: s.side_data_list ?? [],
    })),
    hasAudio: streams.some((s) => s.codec_type === 'audio'),
    video: video ? {
      width: video.width ?? 0,
      height: video.height ?? 0,
      pixFmt: video.pix_fmt ?? null,
      colorSpace: video.color_space ?? null,
      colorTransfer: video.color_transfer ?? null,
      colorPrimaries: video.color_primaries ?? null,
    } : null,
  };
}

/**
 * 源片是不是 HDR。**删 SEI 之前必须问这一句**：HDR 的静态元数据
 * （mastering display / content light level）就住在 SEI 里，一刀切会让片子掉色。
 */
export function isHdr(p) {
  const v = p.video;
  if (!v) return false;
  const hdrTransfers = ['smpte2084', 'arib-std-b67', 'smpte428', 'bt2020-10', 'bt2020-12'];
  const hdrPrimaries = ['bt2020'];
  return hdrTransfers.includes(String(v.colorTransfer))
    || hdrPrimaries.includes(String(v.colorPrimaries))
    || /10le|12le|p010|p210/.test(String(v.pixFmt));
}

/**
 * 从源片挖出所有「针」：tag 的键和值、handler 名、章节标题。
 * 这些字符串**一个都不该出现在输出里**——验收时拿它们去扫输出的字节。
 */
export function needlesOf(p, params = DEFAULT_PARAMS) {
  const min = params.minNeedleBytes ?? DEFAULT_PARAMS.minNeedleBytes;
  const raw = new Set();
  const push = (k, v) => {
    if (!isIdentifying(k, v)) return;
    if (k && !GENERIC_STRINGS.has(String(k))) raw.add(String(k));
    raw.add(String(v));
  };
  for (const [k, v] of Object.entries(p.formatTags)) push(k, v);
  for (const s of p.streams) for (const [k, v] of Object.entries(s.tags)) push(k, v);
  for (const c of p.chapters) {
    if (c?.tags?.title) raw.add(String(c.tags.title));
  }
  const needles = [];
  const skipped = [];
  for (const s of raw) {
    (Buffer.byteLength(s, 'utf8') >= min ? needles : skipped).push(s);
  }
  return { needles: needles.sort(), skipped: skipped.sort() };
}

/**
 * 字节级扫描：把针一根根在文件里找。
 *
 * **这是整套东西的骨气所在**——前面全是「我调了正确的参数」，属于声称；
 * 这一步是「我扫了，真没了」，属于证明。
 */
export function scanBytes(file, needles) {
  const buf = readFileSync(file);
  const hits = [];
  for (const n of needles) {
    const pat = Buffer.from(n, 'utf8');
    if (pat.length === 0) continue;
    let from = 0;
    let count = 0;
    let first = -1;
    for (;;) {
      const i = buf.indexOf(pat, from);
      if (i === -1) break;
      if (first === -1) first = i;
      count += 1;
      from = i + 1;
      if (count > 64) break;
    }
    if (count) hits.push({ needle: n, count, offset: first });
  }
  return hits;
}

/** 扫码流里的工具身份串（SEI / DSE / compressorname 都在这一层）。 */
export function scanToolMarks(file) {
  const buf = readFileSync(file);
  const hits = [];
  for (const m of TOOL_MARKS) {
    const pat = Buffer.from(m, 'utf8');
    let from = 0;
    let count = 0;
    let first = -1;
    for (;;) {
      const i = buf.indexOf(pat, from);
      if (i === -1) break;
      if (first === -1) first = i;
      count += 1;
      from = i + 1;
      if (count > 64) break;
    }
    if (count) hits.push({ mark: m, count, offset: first });
  }
  return hits;
}

/**
 * 要不要动 SEI 这把刀。
 *
 * ffmpeg 只给得起 NAL 级的粒度（`filter_units` 按 NAL 类型删，
 * `h264_metadata` 也没有「只删某个 SEI payload」的选项），所以 remove_types=6
 * 是**全部 SEI 一起删**。SEI 里除了 x264 那串垃圾，还住着 HDR 元数据和
 * CEA-608/708 内嵌字幕——所以只在**真查到身份串**时才动刀，HDR 源片一律不动。
 */
export function seiPlan(p, toolMarks) {
  const identity = toolMarks.filter((h) => h.mark === 'x264 - core' || h.mark === 'x265');
  if (isHdr(p)) {
    return {
      remove: false,
      reason: 'HDR 源片：SEI 里住着 mastering display / content light level，删了会掉色',
      warn: identity.length > 0
        ? `码流里有 ${identity.map((h) => h.mark).join('、')}，但 HDR 优先，没动它`
        : null,
    };
  }
  if (!identity.length) {
    return { remove: false, reason: '码流里没查到编码器身份串，不必动刀', warn: null };
  }
  return {
    remove: true,
    reason: `码流里有 ${identity.map((h) => `${h.mark}（${h.count} 处）`).join('、')}`,
    warn: null,
  };
}

/* ------------------------------------------------------------------ */
/* 构造 ffmpeg 参数                                                     */
/* ------------------------------------------------------------------ */

/**
 * 纯函数：只拼参数，不跑 ffmpeg。自测靠它，不花时间不碰真文件。
 *
 * 五个藏身处对应的堵法都在这里，少一条就不算清干净：
 *   1. 容器 tag 的 Lavf   → -fflags +bitexact（profile 要写 encoder 的话再显式写回）
 *   2. avc1 的 compressorname → -metadata:s:v:0 encoder=
 *   3. AAC 码流的 DSE      → -flags:a +bitexact
 *   4. H.264 的 SEI        → -bsf:v filter_units=remove_types=6
 *   5. handler_name        → 显式写值，置空会退回 ffmpeg 默认的 VideoHandler
 */
export function scrubArgs(opts) {
  const {
    input, output,
    mode = DEFAULT_PARAMS.mode,
    profile = DEFAULT_PARAMS.profile,
    crf = DEFAULT_PARAMS.crf,
    encoder = 'libx264',
    hasAudio = true,
    removeSei = false,
    date = null,
  } = opts;

  const prof = PROFILES[profile];
  if (!prof) throw new Error(`没有 ${profile} 这个 profile（有 ${Object.keys(PROFILES).join(' / ')}）`);
  if (!MODES[mode]) throw new Error(`没有 ${mode} 这个模式（有 ${Object.keys(MODES).join(' / ')}）`);

  const a = ['-v', 'error', '-y', '-i', input];

  // ① 白名单选流：只要画面和声音，data / timecode / 附件 / 章节一律不带
  a.push('-map', '0:v:0');
  if (hasAudio) a.push('-map', '0:a:0?');
  a.push('-map_metadata', '-1', '-map_chapters', '-1');

  // ② 编解码
  if (mode === 'copy') {
    a.push('-c:v', 'copy');
  } else {
    a.push('-c:v', encoder);
    if (encoder === 'libx264' || encoder === 'libx265') a.push('-crf', String(crf));
    else a.push('-b:v', '0', '-q:v', '55');
    a.push('-pix_fmt', 'yuv420p');
  }
  // 音频**两种模式都重编**：AAC 的版本号写在 DSE 里，那是码流内部，
  // -c:a copy 抹不掉它。重编一遍很便宜，换来音轨里干干净净。
  if (hasAudio) a.push('-c:a', 'aac', '-b:a', '192k');

  // ③ 码流里的 SEI（藏身处 4）——只在查到身份串时才删，见 seiPlan。
  //    实测它在 -c:v copy 下照样工作，所以 copy 模式一样清得掉 x264 那串。
  if (removeSei) a.push('-bsf:v', 'filter_units=remove_types=6');

  // ④ 让 ffmpeg 闭嘴（藏身处 1、3）
  //    容器的 encoder 字段只有 bitexact 清得掉，但 obs 档要留着它，见 PROFILES 注释。
  //    显式写的 creation_time 不受 bitexact 影响，实测过。
  if (prof.containerBitexact) a.push('-fflags', '+bitexact');
  if (mode === 'encode') a.push('-flags:v', '+bitexact');
  if (hasAudio) a.push('-flags:a', '+bitexact');

  // ⑤ compressorname（藏身处 2）：mov muxer 从流的 encoder tag 取这个字段，置空即清
  a.push('-metadata:s:v:0', 'encoder=');
  if (hasAudio) a.push('-metadata:s:a:0', 'encoder=');

  // ⑥ profile 往回写的那一层（藏身处 5 也在这里）
  a.push('-metadata:s:v:0', `handler_name=${prof.videoHandler}`);
  if (hasAudio) a.push('-metadata:s:a:0', `handler_name=${prof.audioHandler}`);
  if (prof.setCreationTime) {
    a.push('-metadata', `creation_time=${date ?? new Date().toISOString()}`);
  }

  a.push('-movflags', '+faststart', output);
  return a;
}

/* ------------------------------------------------------------------ */
/* 门                                                                  */
/* ------------------------------------------------------------------ */

const GATE_LABELS = {
  residue: '字节级残留',
  tags: 'tag 层残留',
  gps: '位置信息',
  device: '设备与软件标识',
  creation: '源片时间戳',
  rotation: '旋转矩阵',
  streams: '流构成',
  chapters: '章节',
  bitstream: '码流身份串',
  profile: 'profile 相符',
  duration: '时长',
  decodable: '可解码',
};

const gate = (id, issues, skipped = null) => ({
  id,
  label: GATE_LABELS[id] ?? id,
  ok: skipped ? true : issues.length === 0,
  skipped,
  issues,
});

/**
 * 纯函数：吃探测结果，吐门的清单。不做 IO，自测可以直接喂假数据。
 */
export function verify(ctx) {
  const {
    src, out, residue = [], toolMarks = [],
    profile = DEFAULT_PARAMS.profile,
    mode = DEFAULT_PARAMS.mode,
    params = DEFAULT_PARAMS,
    skippedNeedles = [],
    decodeError = null,
  } = ctx;
  const prof = PROFILES[profile];
  const gates = [];
  const hints = [];

  /*
   * profile 自己写上去的值要豁免，否则会出现一种假阳性：
   * 源片也是 ffmpeg 封的、版本号还恰好相同，那输出的 encoder 会和源片一模一样——
   * 但它是 muxer 现写的，不是漏过来的。
   *
   * 这个豁免不会开口子：有 `-map_metadata -1` 在，源片的 encoder 字段
   * **结构上就到不了**输出，那一格永远由 muxer 自己填。
   */
  const profileOwned = new Set();
  if (prof?.expectEncoder) {
    const enc = String(out.formatTags.encoder ?? '');
    if (prof.expectEncoder.test(enc)) profileOwned.add(enc);
  }

  /* 1. 字节级残留：源片的元数据串一根都不许扎中 */
  {
    const real = residue.filter((h) => !profileOwned.has(h.needle));
    const bad = real.map((h) => `「${h.needle}」在输出里出现 ${h.count} 次（首现 @${h.offset}）`);
    gates.push(gate('residue', bad));
    const exempt = residue.length - real.length;
    if (exempt) hints.push(`有 ${exempt} 个串是 ${profile} 档自己写回去的（muxer 现写，非源片残留），已豁免`);
    if (skippedNeedles.length) {
      hints.push(`有 ${skippedNeedles.length} 个太短的串没扫（短于 ${params.minNeedleBytes} 字节会在压缩数据里撞出假阳性）：${skippedNeedles.join('、')}`);
    }
  }

  /* 2. tag 层：输出的键和值都不许来自源片 */
  {
    const srcVals = new Set();
    const collect = (tags) => {
      for (const [k, v] of Object.entries(tags)) {
        if (isIdentifying(k, v)) srcVals.add(String(v));
      }
    };
    collect(src.formatTags);
    for (const s of src.streams) collect(s.tags);

    const bad = [];
    const checkOut = (tags, where) => {
      for (const [k, v] of Object.entries(tags)) {
        if (!isIdentifying(k, v) || profileOwned.has(String(v))) continue;
        if (srcVals.has(String(v))) bad.push(`${where} 的 ${k} = ${v}（源片里就有这个值）`);
      }
    };
    checkOut(out.formatTags, 'format');
    for (const s of out.streams) checkOut(s.tags, `stream #${s.index}`);
    gates.push(gate('tags', bad));
  }

  /* 3. 位置：一个都不许有 */
  {
    const bad = [];
    const scan = (tags, where) => {
      for (const k of Object.keys(tags)) {
        const low = k.toLowerCase();
        if (LOCATION_KEYS.some((g) => low === g || low.includes('location') || low.includes('gps'))) {
          bad.push(`${where} 还留着 ${k}`);
        }
      }
    };
    scan(out.formatTags, 'format');
    for (const s of out.streams) scan(s.tags, `stream #${s.index}`);
    gates.push(gate('gps', bad));
  }

  /* 4. 设备与软件：profile 自己要写的除外 */
  {
    const allowed = new Set();
    if (prof?.expectEncoder) allowed.add('encoder');
    if (prof?.setCreationTime) allowed.add('creation_time');
    const bad = [];
    for (const k of Object.keys(out.formatTags)) {
      const low = k.toLowerCase();
      if (STRUCTURAL_TAGS.has(low) || allowed.has(low)) continue;
      if (DEVICE_KEYS.includes(low)) bad.push(`format 还留着 ${k} = ${out.formatTags[k]}`);
    }
    gates.push(gate('device', bad));
  }

  /* 5. 源片时间戳：输出的 creation_time 不许等于源片的 */
  {
    const srcTime = src.formatTags.creation_time
      ?? src.streams.map((s) => s.tags.creation_time).find(Boolean);
    const outTime = out.formatTags.creation_time
      ?? out.streams.map((s) => s.tags.creation_time).find(Boolean);
    const bad = [];
    if (srcTime && outTime && String(srcTime) === String(outTime)) {
      bad.push(`输出的 creation_time 和源片一模一样：${outTime}`);
    }
    gates.push(gate('creation', bad));
  }

  /* 6. 旋转矩阵。copy 模式下画面字节没动，矩阵必须留着，否则播出来是歪的 */
  {
    const rot = out.streams.flatMap((s) => s.sideData.filter((d) => /display ?matrix/i.test(String(d.side_data_type ?? ''))));
    if (mode === 'copy') {
      gates.push(gate('rotation', [], 'copy 模式：画面未重编，旋转矩阵必须原样留着'));
    } else {
      gates.push(gate('rotation', rot.length ? ['输出还带着 display matrix，说明旋转没烘进画面'] : []));
    }
  }

  /* 7. 流构成：只剩画面和声音。GoPro 的 GPS 轨就死在这一条 */
  {
    const bad = [];
    const byType = {};
    for (const s of out.streams) byType[s.type] = (byType[s.type] ?? 0) + 1;
    for (const [t, n] of Object.entries(byType)) {
      if (t !== 'video' && t !== 'audio') bad.push(`输出里还有 ${n} 条 ${t} 流`);
    }
    if ((byType.video ?? 0) !== 1) bad.push(`视频流应为 1 条，实际 ${byType.video ?? 0} 条`);
    if ((byType.audio ?? 0) > 1) bad.push(`音频流最多 1 条，实际 ${byType.audio} 条`);
    gates.push(gate('streams', bad));
  }

  /* 8. 章节 */
  gates.push(gate('chapters', out.chapters.length ? [`输出还有 ${out.chapters.length} 个章节`] : []));

  /* 9. 码流身份串：profile 明说要写的不算 */
  {
    // obs 档明说要留着 ffmpeg 自己的 Lavf 版本号，那一处不算违规。
    const declared = prof?.expectEncoder ? String(out.formatTags.encoder ?? '') : '';
    const bad = toolMarks
      .filter((h) => !(declared && declared.includes(h.mark)))
      .map((h) => `码流里有「${h.mark}」${h.count} 处（首现 @${h.offset}）`);
    gates.push(gate('bitstream', bad));
  }

  /* 10. 剩下的 tag 恰好等于 profile 声明的 */
  {
    const bad = [];
    const enc = String(out.formatTags.encoder ?? '');
    if (prof?.expectEncoder && !prof.expectEncoder.test(enc)) {
      bad.push(`profile 说 encoder 该长得像 ${prof.expectEncoder}，实际是「${enc || '（没有）'}」`);
    }
    if (prof && !prof.expectEncoder && enc) {
      bad.push(`profile 说不该有 encoder 字段，实际留着「${enc}」`);
    }
    const vh = out.streams.find((s) => s.type === 'video')?.tags?.handler_name ?? '';
    if (prof && String(vh).trim() !== String(prof.videoHandler).trim()) {
      bad.push(`视频 handler_name 该是「${prof.videoHandler.trim() || '（空）'}」，实际「${vh}」`);
    }
    gates.push(gate('profile', bad));
  }

  /* 11. 时长：没被偷偷截断 */
  {
    const d = Math.abs(out.durationSeconds - src.durationSeconds);
    const tol = params.durationTolerance ?? DEFAULT_PARAMS.durationTolerance;
    gates.push(gate('duration', d > tol
      ? [`输出 ${out.durationSeconds}s，源片 ${src.durationSeconds}s，差 ${r2(d)}s（容差 ${tol}s）`]
      : []));
  }

  /* 12. 能不能正常解码 */
  gates.push(gate('decodable', decodeError ? [`解码报错：${decodeError}`] : []));

  const failed = gates.filter((g) => !g.ok);
  return { gates, failed, hints, ok: failed.length === 0 };
}

/** 整条流水线跑完解码一遍，确认没产出坏文件。 */
export function decodeCheck(file) {
  try {
    execFileSync('ffmpeg', ['-v', 'error', '-i', file, '-f', 'null', '-'],
      { stdio: ['ignore', 'ignore', 'pipe'], encoding: 'utf8' });
    return null;
  } catch (err) {
    const msg = String(err.stderr ?? err.message).trim().split('\n')[0];
    return msg || '未知错误';
  }
}

/* ------------------------------------------------------------------ */
/* CLI                                                                 */
/* ------------------------------------------------------------------ */

const USAGE = `video-scrub.mjs — 重建一条视频，源片的元数据一概不搬

  inspect <video> [--json]
      先看源片带了什么：容器 tag、流 tag、side data、章节，
      以及 **ffprobe 看不见的那层**——码流里的 SEI / DSE 身份串。

  scrub <video> [-o out.mp4] [--mode copy|encode] [--profile obs|quicktime|screencapture|bare]
        [--crf 18] [--encoder libx264] [--date <ISO 时间>]
      清。默认 --mode copy（画质零损失、快几十倍）+ --profile obs。
      --mode encode 会重编码，多杀掉码流域的东西，代价是有损。

  verify <源> <输出> [--profile obs] [--mode copy] [--json]
      验收：把源片所有元数据串当针，在输出的字节里扫一遍，扎到一根就红。
      12 道门的清单。

  run <video> [-o out.mp4] [其余同 scrub]
      scrub + verify 一条龙。**日常就用这个。**

模式：
  copy    ${MODES.copy}
  encode  ${MODES.encode}

profile：
${Object.entries(PROFILES).map(([k, v]) => `  ${k.padEnd(14)}${v.label}`).join('\n')}
`;

function flag(rest, name, fallback = null) {
  const i = rest.indexOf(name);
  if (i === -1) return fallback;
  const v = rest[i + 1];
  return v == null || v.startsWith('--') ? true : v;
}

function has(rest, name) {
  return rest.includes(name);
}

function needInput(rest) {
  const file = rest.find((a) => !a.startsWith('-') && existsSync(a));
  if (!file) throw new Error('要给一个存在的视频文件');
  return file;
}

function optsOf(rest, input) {
  const mode = String(flag(rest, '--mode', DEFAULT_PARAMS.mode));
  const profile = String(flag(rest, '--profile', DEFAULT_PARAMS.profile));
  if (!MODES[mode]) throw new Error(`没有 ${mode} 这个模式（有 ${Object.keys(MODES).join(' / ')}）`);
  if (!PROFILES[profile]) throw new Error(`没有 ${profile} 这个 profile（有 ${Object.keys(PROFILES).join(' / ')}）`);
  const base = basename(input).replace(/\.[^.]+$/, '');
  return {
    mode,
    profile,
    crf: Number(flag(rest, '--crf', DEFAULT_PARAMS.crf)),
    encoder: String(flag(rest, '--encoder', 'libx264')),
    date: flag(rest, '--date', null),
    output: String(flag(rest, '-o', null) ?? flag(rest, '--out', null) ?? `${base}-scrubbed.mp4`),
  };
}

function cmdInspect(rest) {
  const file = needInput(rest);
  const p = probe(file);
  const marks = scanToolMarks(file);
  const { needles, skipped } = needlesOf(p);
  const report = {
    file, durationSeconds: p.durationSeconds, sizeBytes: p.sizeBytes,
    hdr: isHdr(p),
    formatTags: p.formatTags,
    streams: p.streams.map((s) => ({ index: s.index, type: s.type, codec: s.codec, tags: s.tags, sideData: s.sideData.map((d) => d.side_data_type) })),
    chapters: p.chapters.length,
    toolMarks: marks,
    needles, skippedNeedles: skipped,
  };
  if (has(rest, '--json')) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return report;
  }
  const L = (s) => process.stdout.write(`${s}\n`);
  L(`${file}　${p.durationSeconds}s　${(p.sizeBytes / 1e6).toFixed(1)}MB　${p.video?.width}x${p.video?.height}${isHdr(p) ? '　⚠ HDR' : ''}`);
  L('');
  L('容器 tag：');
  const ft = Object.entries(p.formatTags);
  if (!ft.length) L('  （空）');
  for (const [k, v] of ft) L(`  ${STRUCTURAL_TAGS.has(k.toLowerCase()) ? ' ' : '!'} ${k} = ${v}`);
  L('');
  L('流：');
  for (const s of p.streams) {
    L(`  #${s.index} ${s.type}/${s.codec}${s.type !== 'video' && s.type !== 'audio' ? '　← 这条不会被带过去' : ''}`);
    for (const [k, v] of Object.entries(s.tags)) L(`      ${k} = ${v}`);
    for (const d of s.sideData) L(`      side_data: ${d.side_data_type}`);
  }
  if (p.chapters.length) L(`\n章节：${p.chapters.length} 个`);
  L('');
  L('码流里的身份串（ffprobe 看不见这一层）：');
  if (!marks.length) L('  （干净）');
  for (const m of marks) L(`  ! 「${m.mark}」${m.count} 处，首现 @${m.offset}`);
  L('');
  L(`验收会拿 ${needles.length} 个串当针去扫输出${skipped.length ? `（另有 ${skipped.length} 个太短，不扫）` : ''}`);
  const plan = seiPlan(p, marks);
  L(`SEI：${plan.remove ? '会删' : '不动'}——${plan.reason}`);
  if (plan.warn) L(`  ⚠ ${plan.warn}`);
  return report;
}

function cmdScrub(rest) {
  const input = needInput(rest);
  const o = optsOf(rest, input);
  const p = probe(input);
  const marks = scanToolMarks(input);
  const plan = seiPlan(p, marks);

  const args = scrubArgs({
    input, output: o.output, mode: o.mode, profile: o.profile,
    crf: o.crf, encoder: o.encoder, hasAudio: p.hasAudio,
    removeSei: plan.remove, date: o.date,
  });

  process.stderr.write(`${o.mode} / ${o.profile}　${input} → ${o.output}\n`);
  process.stderr.write(`SEI：${plan.remove ? '删' : '不动'}——${plan.reason}\n`);
  if (plan.warn) process.stderr.write(`⚠ ${plan.warn}\n`);

  const t0 = Date.now();
  execFileSync('ffmpeg', args, { stdio: ['ignore', 'ignore', 'inherit'] });
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const outSize = statSync(o.output).size;
  process.stderr.write(`完成　${secs}s　${(outSize / 1e6).toFixed(1)}MB（源片 ${(p.sizeBytes / 1e6).toFixed(1)}MB）\n`);
  return o.output;
}

function cmdVerify(rest) {
  const files = rest.filter((a) => !a.startsWith('-') && existsSync(a));
  if (files.length < 2) throw new Error('要给两个文件：verify <源> <输出>');
  const [srcFile, outFile] = files;
  const mode = String(flag(rest, '--mode', DEFAULT_PARAMS.mode));
  const profile = String(flag(rest, '--profile', DEFAULT_PARAMS.profile));

  const src = probe(srcFile);
  const out = probe(outFile);
  const { needles, skipped } = needlesOf(src);
  const residue = scanBytes(outFile, needles);
  const toolMarks = scanToolMarks(outFile);
  const decodeError = decodeCheck(outFile);

  const v = verify({ src, out, residue, toolMarks, profile, mode, skippedNeedles: skipped, decodeError });

  if (has(rest, '--json')) {
    process.stdout.write(`${JSON.stringify({ ...v, residue, toolMarks }, null, 2)}\n`);
    return v;
  }
  const L = (s) => process.stdout.write(`${s}\n`);
  L(`${basename(srcFile)} → ${basename(outFile)}　${mode} / ${profile}`);
  L(`扫了 ${needles.length} 根针`);
  L('');
  for (const g of v.gates) {
    const mark = g.skipped ? '–' : g.ok ? '✓' : '✗';
    L(`  ${mark} ${g.label}${g.skipped ? `　（跳过：${g.skipped}）` : ''}`);
    for (const i of g.issues) L(`      ${i}`);
  }
  for (const h of v.hints) L(`\n  提示：${h}`);
  L('');
  L(v.ok ? `✅ ${v.gates.length} 道门全过——源片的元数据一个字节都没剩下` : `❌ ${v.failed.length} 道门红了`);
  if (!v.ok) process.exitCode = 1;
  return v;
}

function cmdRun(rest) {
  const input = needInput(rest);
  const o = optsOf(rest, input);
  cmdScrub(rest);
  process.stderr.write('\n');
  return cmdVerify([input, o.output, '--mode', o.mode, '--profile', o.profile, ...(has(rest, '--json') ? ['--json'] : [])]);
}

export function main(argv) {
  const [cmd, ...rest] = argv;
  switch (cmd) {
    case 'inspect': return cmdInspect(rest);
    case 'scrub': return cmdScrub(rest);
    case 'verify': return cmdVerify(rest);
    case 'run': return cmdRun(rest);
    default:
      process.stdout.write(USAGE);
      if (cmd && cmd !== '--help' && cmd !== '-h') process.exitCode = 1;
      return undefined;
  }
}

function isMainModule() {
  if (!process.argv[1]) return false;
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (isMainModule()) {
  process.stdout.on('error', (err) => { if (err.code === 'EPIPE') process.exit(0); });
  try {
    main(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`${err.message}\n`);
    process.exitCode = 1;
  }
}
