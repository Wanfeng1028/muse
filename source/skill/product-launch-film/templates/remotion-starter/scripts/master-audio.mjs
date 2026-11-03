// Loudness master (no dynamic AGC, no pumping):
//   1. measure integrated loudness (EBU R128 via ffmpeg loudnorm analysis)
//   2. apply ONE static gain to reach TARGET_I
//   3. transparent look-ahead peak limiter (5 ms look-ahead, 120 ms release) so peaks stay under the ceiling
//   4. re-measure, trim the gain (up to 3 passes), mux: picture stream-copied, audio AAC 256k 48 kHz.
// Targets: I = -16 LUFS, true peak <= -1.5 dBTP. If the limiter works on more than ~10% of samples, fix the mix.
// Usage: node scripts/master-audio.mjs in.mp4 out.mp4
// Uses Remotion's bundled ffmpeg (`npx remotion ffmpeg`) unless FFMPEG=/path/to/ffmpeg is set.
import {spawnSync} from 'node:child_process';
import {copyFileSync, readFileSync, writeFileSync, rmSync} from 'node:fs';

const [IN, OUT] = process.argv.slice(2);
if (!IN || !OUT) {
	console.error('usage: node scripts/master-audio.mjs in.mp4 out.mp4');
	process.exit(2);
}
const TARGET_I = -16; // LUFS
const CEILING_DB = -2.3; // sample-peak ceiling; leaves room for inter-sample + AAC overshoot
const SR = 48000;
const TMP_IN = 'out/.master-in.wav';
const TMP_OUT = 'out/.master-out.wav';

// Minimal 16-bit stereo WAV I/O (the bundled ffmpeg only ships the pcm_s16le encoder; no raw muxer).
const readWav16 = (path) => {
	const b = readFileSync(path);
	let o = 12;
	while (o < b.length - 8) {
		const id = b.toString('ascii', o, o + 4);
		const size = b.readUInt32LE(o + 4);
		if (id === 'data') {
			const n = Math.floor(Math.min(size, b.length - o - 8) / 4) * 2;
			const f = new Float32Array(n);
			for (let i = 0; i < n; i++) f[i] = b.readInt16LE(o + 8 + 2 * i) / 32768;
			return f;
		}
		o += 8 + size + (size & 1);
	}
	throw new Error(`no data chunk in ${path}`);
};
const writeWav16 = (path, data) => {
	const bytes = data.length * 2;
	const out = Buffer.alloc(44 + bytes);
	out.write('RIFF', 0); out.writeUInt32LE(36 + bytes, 4); out.write('WAVE', 8);
	out.write('fmt ', 12); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(2, 22);
	out.writeUInt32LE(SR, 24); out.writeUInt32LE(SR * 4, 28); out.writeUInt16LE(4, 32); out.writeUInt16LE(16, 34);
	out.write('data', 36); out.writeUInt32LE(bytes, 40);
	for (let i = 0; i < data.length; i++) {
		const d = (Math.random() - Math.random()) / 32768; // TPDF dither
		out.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round((data[i] + d) * 32767))), 44 + 2 * i);
	}
	writeFileSync(path, out);
};

// `npx remotion ffmpeg` is the ffmpeg bundled with Remotion; its log can arrive on stdout or stderr.
const ff = (args) => {
	const r = process.env.FFMPEG
		? spawnSync(process.env.FFMPEG, ['-hide_banner', ...args], {encoding: 'utf8', maxBuffer: 64 << 20})
		: spawnSync('npx', ['remotion', 'ffmpeg', '-hide_banner', ...args], {encoding: 'utf8', maxBuffer: 64 << 20});
	const log = `${r.stdout ?? ''}\n${r.stderr ?? ''}`;
	if (r.status !== 0) throw new Error(log.slice(-2000));
	return log;
};
const measure = (inputArgs) => {
	const log = ff([...inputArgs, '-vn', '-af', 'loudnorm=print_format=json', '-f', 'null', '-']);
	const j = JSON.parse(log.slice(log.lastIndexOf('{'), log.lastIndexOf('}') + 1));
	return {I: Number(j.input_i), TP: Number(j.input_tp), LRA: Number(j.input_lra)};
};

const limit = (src, gainDb) => {
	const n = src.length / 2;
	const g = 10 ** (gainDb / 20);
	const ceil = 10 ** (CEILING_DB / 20);
	const W = Math.round(0.005 * SR); // look-ahead half-window
	const rel = 1 - Math.exp(-1 / (0.12 * SR));
	const req = new Float32Array(n);
	for (let i = 0; i < n; i++) {
		const p = Math.max(Math.abs(src[2 * i]), Math.abs(src[2 * i + 1])) * g;
		req[i] = p > ceil ? ceil / p : 1;
	}
	// running min over [i-W, i+W] (monotonic deque)
	const mn = new Float32Array(n);
	const dq = new Int32Array(n);
	let h = 0, t = 0;
	for (let j = 0; j < n + W; j++) {
		if (j < n) {
			while (t > h && req[dq[t - 1]] >= req[j]) t--;
			dq[t++] = j;
		}
		const i = j - W;
		if (i >= 0) {
			while (dq[h] < i - W) h++;
			mn[i] = req[dq[h]];
		}
	}
	// box-average over [i-W/2, i+W/2]: smooth attack that still never exceeds req[i]
	const half = W >> 1;
	const pre = new Float64Array(n + 1);
	for (let i = 0; i < n; i++) pre[i + 1] = pre[i] + mn[i];
	const out = new Float32Array(src.length);
	let env = 1, reduced = 0, maxRed = 1;
	for (let i = 0; i < n; i++) {
		const a = Math.max(0, i - half), b = Math.min(n, i + half + 1);
		const target = (pre[b] - pre[a]) / (b - a);
		env = Math.min(target, env + (1 - env) * rel);
		if (env < 0.999) reduced++;
		maxRed = Math.min(maxRed, env);
		out[2 * i] = src[2 * i] * g * env;
		out[2 * i + 1] = src[2 * i + 1] * g * env;
	}
	return {out, reducedPct: (100 * reduced) / n, maxRedDb: 20 * Math.log10(maxRed)};
};

ff(['-y', '-i', IN, '-vn', '-c:a', 'pcm_s16le', '-ar', String(SR), '-ac', '2', TMP_IN]);
const src = readWav16(TMP_IN);
const m0 = measure(['-i', IN]);
console.log(`raw mix:   I=${m0.I} LUFS  TP=${m0.TP} dBTP  LRA=${m0.LRA}`);
if (!Number.isFinite(m0.I) || m0.I < -70) {
	// silent film (no VO/music yet): nothing to master
	copyFileSync(IN, OUT);
	rmSync(TMP_IN);
	console.log(`silent mix, copied unchanged -> ${OUT}`);
	process.exit(0);
}

let gain = TARGET_I - m0.I;
let res, m;
for (let pass = 0; pass < 3; pass++) {
	res = limit(src, gain);
	writeWav16(TMP_OUT, res.out);
	m = measure(['-i', TMP_OUT]);
	if (Math.abs(m.I - TARGET_I) < 0.15) break;
	gain += TARGET_I - m.I;
}
console.log(`gain ${gain.toFixed(2)} dB; limiter active ${res.reducedPct.toFixed(2)}% of samples, max ${res.maxRedDb.toFixed(2)} dB`);

ff(['-y', '-i', IN, '-i', TMP_OUT, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
	'-c:a', 'aac', '-b:a', '256k', '-ar', String(SR), '-shortest', '-movflags', '+faststart', OUT]);
rmSync(TMP_IN);
rmSync(TMP_OUT);
const f = measure(['-i', OUT]);
console.log(`mastered:  I=${f.I} LUFS  TP=${f.TP} dBTP  LRA=${f.LRA}  -> ${OUT}`);
