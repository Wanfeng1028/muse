"""Local WhisperX transcription and alignment; output is an unreviewed draft.

Run with the dedicated WhisperX Python environment. No diarization is implied.
Keep original ASR segments so corrected text can be realigned without re-ASR.
"""
import argparse
from copy import deepcopy
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import time
import wave


def default_runtime_root():
    """Per-user runtime root shared with setup_whisperx.ps1, outside the skill library."""
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    base = Path(base) if base else Path.home() / '.local' / 'share'
    return base / 'video-skill' / 'whisperx'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def first_pts(source, selector):
    frames = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', selector,
        '-read_intervals', '%+#32', '-show_frames', '-show_entries',
        'frame=best_effort_timestamp_time', '-of', 'json', str(source)]))['frames']
    for frame in frames:
        if 'best_effort_timestamp_time' in frame:
            value = float(frame['best_effort_timestamp_time'])
            if math.isfinite(value):
                return value
    raise ValueError(f'Cannot establish first decoded timestamp for {selector}')


def source_info(source):
    metadata = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(source)]))
    if not any(s['codec_type'] == 'audio' for s in metadata['streams']):
        raise ValueError('No audio stream; transcription was not performed.')
    video_pts = first_pts(source, 'v:0')
    audio_pts = first_pts(source, 'a:0')
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(source), 'sha256': digest,
            'video_origin_pts_s': video_pts, 'audio_origin_pts_s': audio_pts,
            'audio_offset_from_video_s': audio_pts - video_pts}


def validate_segments(segments, duration):
    previous_start = -1
    for segment in segments:
        a, b = segment.get('start'), segment.get('end')
        if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (a, b)):
            raise ValueError('Transcript segments require finite audio-relative start/end values.')
        if not 0 <= a < b <= duration + 0.1 or a < previous_start:
            raise ValueError('Transcript segment outside audio or out of order.')
        if not isinstance(segment.get('text'), str) or not segment['text'].strip():
            raise ValueError('Transcript segment requires nonempty text.')
        previous_start = a


def normalize(aligned, offset):
    """Preserve missing/zero-length word timings; never invent their boundaries."""
    result = []
    for i, seg in enumerate(aligned['segments'], 1):
        words = []
        for j, word in enumerate(seg.get('words', []), 1):
            a, b = word.get('start'), word.get('end')
            timed = (isinstance(a, (int, float)) and isinstance(b, (int, float))
                     and math.isfinite(a) and math.isfinite(b) and a < b)
            words.append({'id': f'd{i}_w{j}', 'text': word['word'],
                          'start': round(a + offset, 6) if timed else None,
                          'end': round(b + offset, 6) if timed else None,
                          'alignment_score': word.get('score'),
                          'timing_status': 'aligned_unreviewed' if timed else 'unaligned'})
        result.append({'id': f'd{i}', 'start': round(seg['start'] + offset, 6),
                       'end': round(seg['end'] + offset, 6), 'text': seg['text'],
                       'speaker': 'unknown', 'delivery': 'unknown',
                       'timing': {'basis': 'estimated', 'uncertainty_s': None}, 'words': words})
    return result


def packaged_silero():
    """Reuse WhisperX VAD behavior with the official wheel's bundled model.

    Avoid torch.hub's network/branch lookup on every otherwise local run.
    """
    from whisperx.vads.silero import Silero
    from whisperx.vads.vad import Vad
    from silero_vad import load_silero_vad, get_speech_timestamps

    class PackagedSilero(Silero):
        def __init__(self):
            Vad.__init__(self, 0.5)
            self.vad_onset = 0.5
            self.chunk_size = 30
            self.vad_pipeline = load_silero_vad(onnx=False)
            self.get_speech_timestamps = get_speech_timestamps

    return PackagedSilero()


def transcribe(args):
    source = args.video.resolve(strict=True)
    skill = Path(__file__).resolve().parents[1]
    out, cache = args.output_dir.resolve(), args.cache_dir.resolve()
    for path in (out, cache):
        if path == skill or skill in path.parents:
            raise ValueError('Keep runtime caches and outputs outside the skill folder.')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new, empty output directory; earlier results are preserved.')
    info = source_info(source)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    os.environ['HF_HOME'] = str(cache / 'huggingface')
    os.environ['TORCH_HOME'] = str(cache / 'torch')
    os.environ['NLTK_DATA'] = str(cache / 'nltk')
    (cache / 'nltk').mkdir(exist_ok=True)
    os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
    # PyTorch CUDA wheels provide DLLs also needed by CTranslate2 on Windows.
    import torch
    dll_handle = None
    if os.name == 'nt':
        dll_dir = str(Path(torch.__file__).parent / 'lib')
        os.environ['PATH'] = dll_dir + os.pathsep + os.environ['PATH']
        dll_handle = os.add_dll_directory(dll_dir)
    import whisperx
    started = time.monotonic()
    job = {'status': 'running', 'source': info, 'settings': {
        'model': args.model, 'language': args.language, 'device': args.device,
        'compute_type': args.compute_type, 'batch_size': args.batch_size,
        'vad_method': 'silero_packaged', 'diarization': False, 'offline': args.offline,
        'alignment_model_override': args.align_model}, 'versions': {
            name: importlib.metadata.version(name) for name in
            ('whisperx', 'faster-whisper', 'ctranslate2', 'torch', 'transformers', 'silero-vad')},
        'realigned_from': str(args.transcript.resolve()) if args.transcript else None}
    save(out / 'job.json', job)
    try:
        if args.device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; inspect runtime or explicitly use --device cpu --compute-type int8.')
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-i', str(source),
             '-map', '0:a:0', '-vn', '-af', 'aresample=16000:async=1,asetpts=PTS-STARTPTS',
             '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(out / 'audio.wav')])
        with wave.open(str(out / 'audio.wav')) as wav:
            duration = wav.getnframes() / wav.getframerate()
        audio = whisperx.load_audio(str(out / 'audio.wav'))
        if args.transcript:
            raw = json.loads(args.transcript.read_text(encoding='utf-8-sig'))
            if raw.get('source_sha256') != info['sha256'] or raw.get('time_reference') != 'extracted_audio_start':
                raise ValueError('Corrected transcript must match source SHA256 and use audio-relative times.')
            if raw.get('language') != args.language:
                raise ValueError('Corrected transcript language differs from --language.')
        else:
            print('Loading ASR model...', flush=True)
            model = whisperx.load_model(args.model, args.device, compute_type=args.compute_type,
                language=args.language, vad_method='silero', download_root=str(cache / 'asr'),
                local_files_only=args.offline, vad_model=packaged_silero())
            raw = model.transcribe(audio, batch_size=args.batch_size, language=args.language)
            raw.update(source_sha256=info['sha256'], time_reference='extracted_audio_start')
            del model
            gc.collect()
            if args.device == 'cuda':
                torch.cuda.empty_cache()
        save(out / 'transcript.raw.json', raw)
        validate_segments(raw['segments'], duration)
        align_name = None
        if raw['segments']:
            print('Aligning transcript...', flush=True)
            align_model, align_meta = whisperx.load_align_model(language_code=args.language,
                device=args.device, model_dir=str(cache / 'alignment'), model_name=args.align_model)
            from whisperx.alignment import DEFAULT_ALIGN_MODELS_HF, DEFAULT_ALIGN_MODELS_TORCH
            align_name = args.align_model or DEFAULT_ALIGN_MODELS_HF.get(args.language) or DEFAULT_ALIGN_MODELS_TORCH.get(args.language)
            aligned = whisperx.align(deepcopy(raw['segments']), align_model, align_meta, audio,
                args.device, return_char_alignments=False, interpolate_method='ignore')
            before = ''.join(''.join(s['text'].split()) for s in raw['segments'])
            after = ''.join(''.join(s['text'].split()) for s in aligned['segments'])
            if before != after:
                save(out / 'alignment.partial.json', aligned)
                raise ValueError('Alignment omitted/changed transcript text. Raw ASR is preserved; review before retry.')
            del align_model
        else:
            aligned = {'segments': [], 'word_segments': []}
        save(out / 'transcript.aligned.json', {'time_reference': 'extracted_audio_start', **aligned})
        dialogue = normalize(aligned, info['audio_offset_from_video_s'])
        words = [w for d in dialogue for w in d['words']]
        unaligned = [w['id'] for w in words if w['timing_status'] == 'unaligned']
        weak = [w['id'] for w in words if w['alignment_score'] is not None and w['alignment_score'] < 0.3]
        result = {'schema_version': 'speech-1.0', 'source': info,
            'time_reference': 'first_video_frame', 'audio_duration_s': duration,
            'language': args.language, 'alignment_model': align_name,
            'transcription_origin': 'supplied_transcript' if args.transcript else 'asr',
            'review_status': 'machine_draft', 'dialogue': dialogue,
            'quality': {'word_count': len(words), 'unaligned_word_ids': unaligned,
                        'review_word_ids': weak, 'review_score_threshold': 0.3,
                        'listening_verified': False, 'speaker_identification': 'not_performed'},
            'limitations': ['ASR and alignment require listening review; alignment scores are not transcription confidence.',
                           'No detected segments does not prove no speech. Do not infer delivery or visual identity.',
                           'Sentence segments are not speaker turns; one segment can contain several speakers.',
                           'Times are video-relative; audio outside visual duration must be handled explicitly.']}
        save(out / 'transcript.json', result)
        lines = ['# 전사·정렬 초안', '', '자동 결과이며 청취 검증 전입니다. 시간은 원본 영상 첫 프레임 기준입니다.', '',
                 '| ID | 시작–종료(초) | 대사 |', '|---|---|---|']
        for d in dialogue:
            text = d['text'].replace('|', '\\|').replace('\n', ' ')
            lines.append(f"| {d['id']} | {d['start']:.3f}–{d['end']:.3f} | {text} |")
        lines += ['', f'정렬되지 않은 단어: {len(unaligned)} / {len(words)}',
                  f'낮은 정렬 점수로 우선 확인할 단어: {", ".join(weak) or "없음"} (0.3 미만; 정확도 판정 아님)',
                  '단어별 시각과 정렬 점수는 transcript.json을 확인하세요.']
        (out / 'transcript.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        job.update(status='completed', elapsed_s=round(time.monotonic() - started, 3),
                   segments=len(dialogue), words=len(words), unaligned_words=len(unaligned))
    except Exception as error:
        job.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save(out / 'job.json', job)
        if dll_handle:
            dll_handle.close()
    print(json.dumps(job, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, default=default_runtime_root() / 'models')
    parser.add_argument('--model', default='large-v3')
    parser.add_argument('--language', default='ko')
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--compute-type', default='int8_float16')
    parser.add_argument('--batch-size', type=int, default=1)
    parser.add_argument('--align-model', help='Optional local alignment model directory or HF repository')
    parser.add_argument('--offline', action='store_true', help='Use cached HF models; NLTK must also be pre-cached')
    parser.add_argument('--transcript', type=Path, help='Corrected transcript.raw.json to align without ASR')
    transcribe(parser.parse_args())
