#!/usr/bin/env node
// video-scrub 自测：不碰 ffmpeg、不碰真文件、不花时间。
// 12 道门每一道都有**击穿用例**——证明它真的会拦，不是摆设。

import {
  MODES, PROFILES, DEFAULT_PARAMS, STRUCTURAL_TAGS, GENERIC_STRINGS,
  TOOL_MARKS, LOCATION_KEYS, DEVICE_KEYS,
  isIdentifying, isHdr, needlesOf, seiPlan, scrubArgs, verify,
} from './video-scrub.mjs';

let passed = 0;
const failures = [];

function ok(cond, label) {
  if (cond) passed += 1;
  else failures.push(label);
}
const eq = (got, want, label) =>
  ok(Object.is(got, want), `${label}（得到 ${JSON.stringify(got)}，应为 ${JSON.stringify(want)}）`);

/* ------------------------------------------------------------------ */
/* 夹具                                                                */
/* ------------------------------------------------------------------ */

/** 一份「已经清干净」的探测结果——所有门都该绿。改一处就该红一道。 */
const cleanOut = () => ({
  file: 'out.mp4',
  durationSeconds: 53.37,
  sizeBytes: 12_400_000,
  formatTags: {
    major_brand: 'isom', minor_version: '512',
    compatible_brands: 'isomiso2avc1mp41',
    encoder: 'Lavf62.12.102',
    creation_time: '2026-09-21T10:00:00.000000Z',
  },
  chapters: [],
  streams: [
    { index: 0, type: 'video', codec: 'h264', tags: { language: 'und', handler_name: 'VideoHandler' }, sideData: [] },
    { index: 1, type: 'audio', codec: 'aac', tags: { language: 'und', handler_name: 'SoundHandler' }, sideData: [] },
  ],
  hasAudio: true,
  video: { width: 1312, height: 736, pixFmt: 'yuv420p', colorSpace: null, colorTransfer: null, colorPrimaries: null },
});

/** 一份脏源片：GPS、邮箱、抖音 ID、设备名、章节、一条 data 轨。 */
const dirtySrc = () => ({
  file: 'src.mp4',
  durationSeconds: 53.37,
  sizeBytes: 12_000_000,
  formatTags: {
    major_brand: 'isom', minor_version: '512',
    compatible_brands: 'isomiso2avc1mp41',
    creation_time: '2025-03-14T08:22:11.000000Z',
    artist: 'wesley@yogatummee.com',
    album: 'iPhone 15 Pro',
    comment: 'vid:v1e00fgi0000da64usvog65t9bk1rqgg',
    location: '+31.2304+121.4737/',
    encoder: 'Lavf58.45.100',
  },
  chapters: [{ tags: { title: '在家拍的第一段' } }],
  streams: [
    { index: 0, type: 'video', codec: 'h264', tags: { language: 'und', handler_name: 'VideoHandler' }, sideData: [] },
    { index: 1, type: 'audio', codec: 'aac', tags: { language: 'und', handler_name: 'SoundHandler' }, sideData: [] },
    { index: 2, type: 'data', codec: 'bin_data', tags: { handler_name: 'SubtitleHandler' }, sideData: [] },
  ],
  hasAudio: true,
  video: { width: 1312, height: 736, pixFmt: 'yuv420p', colorSpace: null, colorTransfer: null, colorPrimaries: null },
});

const run = (over = {}) => verify({
  src: dirtySrc(), out: cleanOut(), residue: [], toolMarks: [],
  profile: 'obs', mode: 'copy', params: DEFAULT_PARAMS, ...over,
});
const gateOf = (v, id) => v.gates.find((g) => g.id === id);
const fails = (over, id, label) => {
  const g = gateOf(run(over), id);
  ok(g && !g.ok && !g.skipped, `${label} —— ${id} 门应该拦下`);
};
const holds = (over, id, label) => {
  const g = gateOf(run(over), id);
  ok(g && g.ok, `${label} —— ${id} 门不该拦（${g?.issues?.join('；')}）`);
};

/* ------------------------------------------------------------------ */
/* 基线：干净的输出必须全绿                                             */
/* ------------------------------------------------------------------ */
{
  const v = run();
  ok(v.ok, `基线该全绿，红的是：${v.failed.map((g) => g.id).join('、')}`);
  eq(v.gates.length, 12, '一共 12 道门');
  eq(v.gates.filter((g) => g.skipped).length, 1, 'copy 模式下旋转矩阵那道跳过');
}

/* ------------------------------------------------------------------ */
/* 12 道门的击穿用例                                                    */
/* ------------------------------------------------------------------ */

/* 1. 字节级残留 */
fails({ residue: [{ needle: 'wesley@yogatummee.com', count: 1, offset: 12031634 }] },
  'residue', '源片的邮箱出现在输出字节里');
fails({ residue: [{ needle: 'vid:v1e00fgi0000da64usvog65t9bk1rqgg', count: 1, offset: 999 }] },
  'residue', '抖音 ID 出现在输出字节里');

/* 豁免：obs 档自己写回去的 encoder 不算残留 */
{
  const v = run({ residue: [{ needle: 'Lavf62.12.102', count: 1, offset: 43011 }] });
  ok(gateOf(v, 'residue').ok, 'obs 档自己写的 Lavf 版本号该豁免，不算残留');
  ok(v.hints.some((h) => h.includes('豁免')), '豁免了要在提示里说清楚');
}
/* 但豁免不能开口子：版本号对不上 profile 就不豁免 */
{
  const out = cleanOut();
  out.formatTags.encoder = 'Lavf62.12.102';
  const v = verify({
    src: dirtySrc(), out, profile: 'obs', mode: 'copy',
    residue: [{ needle: 'Lavf58.45.100', count: 1, offset: 1 }], toolMarks: [],
  });
  ok(!gateOf(v, 'residue').ok, '源片的旧 Lavf 版本号漏过来了，不该被豁免');
}

/* 2. tag 层残留 */
{
  const out = cleanOut();
  out.formatTags.artist = 'wesley@yogatummee.com';
  fails({ out }, 'tags', '源片的 artist 值原样出现在输出 tag 里');
}
/* 通用串不算残留：obs 档写回 VideoHandler 天经地义 */
holds({}, 'tags', 'VideoHandler 是通用串，源片有输出也有，不该算残留');

/* 3. 位置 */
{
  const out = cleanOut();
  out.formatTags.location = '+31.2304+121.4737/';
  fails({ out }, 'gps', '输出还留着 location');
}
{
  const out = cleanOut();
  out.streams[0].tags['com.apple.quicktime.location.ISO6709'] = '+31.2+121.4/';
  fails({ out }, 'gps', '输出的流上还挂着苹果的位置字段');
}

/* 4. 设备与软件 */
{
  const out = cleanOut();
  out.formatTags.album = 'iPhone 15 Pro';
  fails({ out }, 'device', '输出还留着设备名');
}
{
  const out = cleanOut();
  out.formatTags.comment = 'vid:v1e00fgi0000da64usvog65t9bk1rqgg';
  fails({ out }, 'device', '输出还留着 comment 里的账号 ID');
}
/* profile 明说要写的不算违规 */
holds({}, 'device', 'obs 档的 encoder 和 creation_time 是自己写的，不算设备标识');

/* 5. 源片时间戳 */
{
  const out = cleanOut();
  out.formatTags.creation_time = '2025-03-14T08:22:11.000000Z';
  fails({ out }, 'creation', '输出的 creation_time 和源片一模一样');
}
{
  const out = cleanOut();
  delete out.formatTags.creation_time;
  out.streams[0].tags.creation_time = '2025-03-14T08:22:11.000000Z';
  fails({ out }, 'creation', '时间戳躲到流级去了，一样要拦');
}

/* 6. 旋转矩阵 */
{
  const out = cleanOut();
  out.streams[0].sideData = [{ side_data_type: 'Display Matrix' }];
  fails({ out, mode: 'encode' }, 'rotation', 'encode 模式下旋转该烘进画面，不该留矩阵');
  const g = gateOf(run({ out, mode: 'copy' }), 'rotation');
  ok(g.skipped, 'copy 模式下这道门跳过——删了矩阵画面就是歪的');
}

/* 7. 流构成 */
{
  const out = cleanOut();
  out.streams.push({ index: 2, type: 'data', codec: 'bin_data', tags: {}, sideData: [] });
  fails({ out }, 'streams', 'GoPro 的 gpmd 遥测轨跟过来了');
}
{
  const out = cleanOut();
  out.streams = out.streams.filter((s) => s.type !== 'video');
  fails({ out }, 'streams', '一条视频流都没有');
}
{
  const out = cleanOut();
  out.streams.push({ index: 2, type: 'audio', codec: 'aac', tags: {}, sideData: [] });
  fails({ out }, 'streams', '音频流多于一条');
}

/* 8. 章节 */
{
  const out = cleanOut();
  out.chapters = [{ tags: { title: '在家拍的第一段' } }];
  fails({ out }, 'chapters', '章节跟过来了');
}

/* 9. 码流身份串 */
fails({ toolMarks: [{ mark: 'x264 - core', count: 4, offset: 73 }] },
  'bitstream', 'x264 的 SEI 参数串还在码流里');
fails({ toolMarks: [{ mark: 'Lavc', count: 8, offset: 146686 }] },
  'bitstream', 'AAC 的 DSE 里还有 Lavc 版本号');
/* obs 档留着的那一处 Lavf 不算 */
holds({ toolMarks: [{ mark: 'Lavf', count: 1, offset: 43011 }] },
  'bitstream', 'obs 档 encoder 字段里的 Lavf 是自己写的，不算违规');

/* 10. profile 相符 */
{
  const out = cleanOut();
  delete out.formatTags.encoder;
  fails({ out }, 'profile', 'obs 档该有 Lavf 版本号，却没有');
}
{
  const out = cleanOut();
  fails({ out, profile: 'bare' }, 'profile', 'bare 档不该有 encoder 字段，却留着');
}
{
  const out = cleanOut();
  out.streams[0].tags.handler_name = 'VideoHandler';
  fails({ out, profile: 'quicktime' }, 'profile', 'quicktime 档的 handler 该是 Core Media Video');
}

/* 11. 时长 */
{
  const out = cleanOut();
  out.durationSeconds = 40;
  fails({ out }, 'duration', '输出被截短了 13 秒');
}
{
  const out = cleanOut();
  out.durationSeconds = 53.6;
  holds({ out }, 'duration', '差 0.23 秒在容差内，不该拦');
}

/* 12. 可解码 */
fails({ decodeError: 'moov atom not found' }, 'decodable', '产出了打不开的坏文件');

/* ------------------------------------------------------------------ */
/* 针的挑选                                                            */
/* ------------------------------------------------------------------ */
{
  const { needles, skipped } = needlesOf(dirtySrc());
  const has = (s) => needles.includes(s);
  ok(has('wesley@yogatummee.com'), '邮箱要当针');
  ok(has('vid:v1e00fgi0000da64usvog65t9bk1rqgg'), '抖音 ID 要当针');
  ok(has('iPhone 15 Pro'), '设备名要当针');
  ok(has('+31.2304+121.4737/'), 'GPS 坐标要当针');
  ok(has('在家拍的第一段'), '章节标题要当针');
  ok(has('Lavf58.45.100'), '源片的 ffmpeg 版本号要当针——它钉死了一个版本');
  ok(has('SubtitleHandler'), 'data 轨的 handler 名要当针');

  ok(!has('VideoHandler'), 'VideoHandler 满世界都是，不当针');
  ok(!has('SoundHandler'), 'SoundHandler 同理');
  ok(!has('isom'), '结构性 tag 不当针，否则自己扎自己');
  ok(!has('und'), 'und 不当针');
  ok(!has('encoder'), '通用键名不当针');
  ok(skipped.every((s) => Buffer.byteLength(s, 'utf8') < DEFAULT_PARAMS.minNeedleBytes),
    '被跳过的针都短于阈值');
}
{
  /* 太短的串会在压缩数据里撞出假阳性，必须跳过并说明 */
  const src = dirtySrc();
  src.formatTags.artist = 'abc';
  const { needles, skipped } = needlesOf(src);
  ok(!needles.includes('abc'), '3 字节的串不扫');
  ok(skipped.includes('abc'), '不扫的要记下来，验收时在提示里说明');
  const v = run({ skippedNeedles: ['abc'] });
  ok(v.hints.some((h) => h.includes('太短')), '跳过的针要在提示里交代');
}

/* isIdentifying 的分界线 */
{
  ok(isIdentifying('artist', 'wesley@yogatummee.com'), '邮箱能缩小到某个人');
  ok(isIdentifying('encoder', 'Lavf58.45.100'), '版本号钉死一个版本');
  ok(!isIdentifying('handler_name', 'VideoHandler'), 'VideoHandler 信息量为零');
  ok(!isIdentifying('major_brand', 'isom'), '结构性 tag 不算');
  ok(!isIdentifying('artist', ''), '空值不算');
  ok(!isIdentifying('artist', '   '), '全空白不算');
}

/* ------------------------------------------------------------------ */
/* SEI 这把刀什么时候不许动                                             */
/* ------------------------------------------------------------------ */
{
  const marks = [{ mark: 'x264 - core', count: 4, offset: 73 }];
  const sdr = dirtySrc();
  eq(seiPlan(sdr, marks).remove, true, '查到 x264 身份串就删 SEI');
  eq(seiPlan(sdr, []).remove, false, '没查到身份串就不动刀');

  /* HDR 的静态元数据住在 SEI 里，一刀切会掉色 */
  const hdr = dirtySrc();
  hdr.video = { ...hdr.video, colorTransfer: 'smpte2084', pixFmt: 'yuv420p10le' };
  ok(isHdr(hdr), 'smpte2084 = HDR');
  const plan = seiPlan(hdr, marks);
  eq(plan.remove, false, 'HDR 源片一律不删 SEI');
  ok(plan.warn, 'HDR 又确实有身份串时，要明说没动它');

  const hlg = dirtySrc();
  hlg.video = { ...hlg.video, colorTransfer: 'arib-std-b67' };
  ok(isHdr(hlg), 'HLG 也是 HDR');
  const p10 = dirtySrc();
  p10.video = { ...p10.video, pixFmt: 'p010le' };
  ok(isHdr(p10), '10bit 像素格式按 HDR 算');
  ok(!isHdr(dirtySrc()), 'yuv420p + color 全 unknown 不是 HDR');
}

/* ------------------------------------------------------------------ */
/* ffmpeg 参数：五个藏身处一个都不许漏                                   */
/* ------------------------------------------------------------------ */
{
  const joined = (o) => scrubArgs({ input: 'i.mp4', output: 'o.mp4', ...o }).join(' ');

  const copyObs = joined({ mode: 'copy', profile: 'obs', removeSei: true });
  ok(copyObs.includes('-map 0:v:0'), '只挑视频流');
  ok(copyObs.includes('-map 0:a:0?'), '只挑音频流');
  ok(copyObs.includes('-map_metadata -1'), '不搬源片的容器 tag');
  ok(copyObs.includes('-map_chapters -1'), '不搬章节');
  ok(copyObs.includes('-c:v copy'), 'copy 模式画面不重编');
  ok(copyObs.includes('-c:a aac'), 'copy 模式音频照样重编——DSE 藏在音频码流里');
  ok(copyObs.includes('-bsf:v filter_units=remove_types=6'), '删 SEI（藏身处 4）');
  ok(copyObs.includes('-flags:a +bitexact'), '堵 AAC 的 DSE（藏身处 3）');
  ok(copyObs.includes('-metadata:s:v:0 encoder='), '清 compressorname（藏身处 2）');
  ok(copyObs.includes('-metadata:s:v:0 handler_name=VideoHandler'), '显式写 handler（藏身处 5）');
  ok(!copyObs.includes('-fflags +bitexact'), 'obs 档要留着 Lavf 版本号，不加容器 bitexact');
  ok(copyObs.includes('-metadata creation_time='), 'obs 档写创建时间');

  const copyBare = joined({ mode: 'copy', profile: 'bare', removeSei: true });
  ok(copyBare.includes('-fflags +bitexact'), 'bare 档要清掉容器的 encoder（藏身处 1）');
  ok(copyBare.includes('-metadata:s:v:0 handler_name= '), 'bare 档 handler 用单空格');
  ok(!copyBare.includes('-metadata creation_time='), 'bare 档什么都不写，包括时间');

  const enc = joined({ mode: 'encode', profile: 'bare', crf: 18 });
  ok(enc.includes('-c:v libx264'), 'encode 模式重编画面');
  ok(enc.includes('-crf 18'), 'crf 传进去了');
  ok(enc.includes('-flags:v +bitexact'), 'encode 模式要堵视频编码器的自报家门');
  ok(!enc.includes('filter_units'), '没查到身份串就不该带 SEI 过滤器');

  const noAudio = joined({ mode: 'copy', profile: 'obs', hasAudio: false });
  ok(!noAudio.includes('-c:a aac'), '没音频就别配音频编码器');
  ok(!noAudio.includes('-map 0:a:0?'), '没音频就别挑音频流');
  ok(!noAudio.includes('-metadata:s:a:0'), '没音频就别写音频 tag');

  const dated = joined({ mode: 'copy', profile: 'obs', date: '2026-01-01T00:00:00Z' });
  ok(dated.includes('-metadata creation_time=2026-01-01T00:00:00Z'), '--date 传得进去');

  /* 输入输出要在参数里，且输出在最后 */
  const a = scrubArgs({ input: 'in.mp4', output: 'out.mp4', mode: 'copy', profile: 'obs' });
  eq(a[a.length - 1], 'out.mp4', '输出文件在参数末尾');
  ok(a.includes('in.mp4'), '输入文件在参数里');
}

/* 乱传参数要当场报错，别让它默默跑出个错东西 */
{
  const boom = (o, label) => {
    try { scrubArgs({ input: 'i', output: 'o', ...o }); failures.push(`${label} —— 该报错却没报`); }
    catch { passed += 1; }
  };
  boom({ profile: '不存在' }, '没有的 profile');
  boom({ mode: '不存在' }, '没有的模式');
}

/* ------------------------------------------------------------------ */
/* 常量自洽                                                            */
/* ------------------------------------------------------------------ */
{
  eq(Object.keys(MODES).length, 2, '两种模式');
  eq(Object.keys(PROFILES).length, 4, '四个 profile');
  for (const [name, p] of Object.entries(PROFILES)) {
    ok(typeof p.label === 'string' && p.label.length > 0, `${name} 要有中文说明`);
    ok(typeof p.videoHandler === 'string' && p.videoHandler.length > 0, `${name} 的 videoHandler 不能为空串——置空会退回 ffmpeg 默认值`);
    ok(typeof p.audioHandler === 'string' && p.audioHandler.length > 0, `${name} 的 audioHandler 同理`);
    ok(p.expectEncoder === null || p.expectEncoder instanceof RegExp, `${name} 的 expectEncoder 要么是 null 要么是正则`);
  }
  ok(PROFILES.obs.containerBitexact === false, 'obs 档靠不加 bitexact 来保住 Lavf 版本号');
  ok(PROFILES.bare.containerBitexact === true, 'bare 档必须清掉容器 encoder');
  ok(TOOL_MARKS.includes('x264 - core'), '工具指纹表里要有 x264');
  ok(TOOL_MARKS.includes('Lavc'), '工具指纹表里要有 Lavc');
  ok(STRUCTURAL_TAGS.has('major_brand'), 'major_brand 是结构性 tag');
  ok(GENERIC_STRINGS.has('VideoHandler'), 'VideoHandler 是通用串');
  ok(LOCATION_KEYS.length > 0 && DEVICE_KEYS.includes('comment'), 'comment 算设备／账号标识——抖音 ID 就写在那儿');
  eq(DEFAULT_PARAMS.mode, 'copy', '默认 copy 模式');
  eq(DEFAULT_PARAMS.profile, 'obs', '默认 obs 档');
  ok(DEFAULT_PARAMS.minNeedleBytes >= 4, '针的最短长度要挡住压缩数据里的随机碰撞');
}

/* ------------------------------------------------------------------ */

if (failures.length) {
  process.stderr.write(`\n${failures.length} 项没过：\n`);
  for (const f of failures) process.stderr.write(`  ✗ ${f}\n`);
  process.stderr.write(`\n通过 ${passed}／${passed + failures.length}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`✅ ${passed} 项断言全部通过（12 道门每道都有击穿用例）\n`);
}
