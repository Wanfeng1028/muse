# 로컬 WhisperX 전사

한국어 기본값은 Whisper large-v3 + WhisperX 한국어 정렬이다. ASR은 faster-whisper 백엔드를 사용한다. 이는 OpenAI Whisper를 활용하는 별도 오픈소스 프로젝트이며 모든 영상 분석 도구가 사용하는 표준이라고 단정하지 않는다.

## 실행 환경

Windows/NVIDIA용 별도 Python 3.11 환경을 사용한다. 준비된 공용 환경이나 현재 기기에서 접근 가능한 기존 환경을 먼저 재사용한다. 실행에는 `ffmpeg`, `ffprobe`가 PATH에 있어야 하며, `uv`는 새 환경 설치 시 필요하다. 기본 Python이나 다른 프로젝트의 패키지를 바꾸지 않는다. 가상환경·모델 캐시는 스킬 모음 밖의 공용 또는 프로젝트별 위치에 두고, 입력·전사 결과는 현재 작업 프로젝트에 둔다.

### 기존 환경 재사용

사용 가능한 가상환경의 Python, 모델 캐시, 설치한 스킬의 위치를 각각 지정한다. 공용 환경과 프로젝트별 환경 모두 같은 방식으로 사용할 수 있다. 개인 경로는 저장소 밖의 환경 설정이나 실행 명령에서 관리한다.

아래 PowerShell 예시의 `C:/path/to/...`는 모두 실제 경로로 바꾼다. 가상환경 디렉터리 이름을 가정하지 말고 실제 Python 실행 파일을 지정한다. 기존 환경을 재사용할 때는 설치 스크립트를 실행하지 않는다.

절대 경로를 지정하면 어느 작업 디렉터리에서도 실행할 수 있다. 매번 새로운 출력 폴더를 사용한다.

```powershell
$projectRoot = 'C:/path/to/project'
$speechPython = 'C:/path/to/venv/Scripts/python.exe'
$modelCache = 'C:/path/to/model-cache'
$skillRoot = 'C:/path/to/video-ad-analyzer'
$speechScript = Join-Path $skillRoot 'scripts/transcribe_video.py'
& $speechPython -X utf8 $speechScript "$projectRoot/input.mp4" --cache-dir $modelCache --output-dir "$projectRoot/analysis/speech/run01" --offline
```

`--offline`은 선택한 음성·정렬 모델과 NLTK 데이터가 모두 준비된 캐시에서 사용한다. 다른 언어·모델도 캐시되어 있다고 가정하지 않는다. 필요한 모델을 처음 다운로드할 때는 네트워크 사용이 가능한 환경에서 `--offline`을 생략한다.

### 새 환경 설치

새 기기에 스킬만 다운로드했다면 실행 환경·모델은 포함되지 않는다. 최초 설치와 모델 다운로드에는 네트워크와 수 GB 이상의 디스크 공간이 필요하며, 설치를 요청받았거나 이미 승인된 경우에 실행한다. 아래는 **현재 설치한 `video-ad-analyzer` 폴더에서** 실행하는 PowerShell 예시다. 프로젝트별 환경을 새로 만드는 경우이며 기존 공용 환경에서는 실행하지 않는다.

```powershell
$projectRoot = 'C:/path/to/project'
$runtimeRoot = Join-Path $projectRoot '.runtime'
$speechPython = Join-Path $runtimeRoot 'whisperx/Scripts/python.exe'
$modelCache = Join-Path $runtimeRoot 'models'
$speechScript = Join-Path (Get-Location).Path 'scripts/transcribe_video.py'
./scripts/setup_whisperx.ps1 -RuntimeRoot $runtimeRoot
& $speechPython -X utf8 $speechScript "$projectRoot/input.mp4" --cache-dir $modelCache --output-dir "$projectRoot/analysis/speech/run01"
```

설치 스크립트는 Windows/NVIDIA용 패키지 버전을 `requirements-whisperx.txt`로 고정하고 `<RuntimeRoot>/whisperx/Scripts/python.exe`에 가상환경을 만든다. `-RuntimeRoot` 생략 시 설치 위치는 사용자별 공용 위치인 `%LOCALAPPDATA%/video-skill/whisperx`(Windows 외에는 `$XDG_DATA_HOME` 또는 `~/.local/share` 아래 `video-skill/whisperx`)이고, 전사 스크립트의 `--cache-dir` 생략 시 모델 위치는 같은 루트의 `models`다. 두 기본값은 스킬 폴더 밖에 있으며, 기존 환경을 자동 탐색하지 않는다. 프로젝트별 환경이나 이미 준비된 다른 환경을 쓸 때는 `-RuntimeRoot`와 `--cache-dir`를 명시한다. 가상환경 자체를 다른 위치로 옮겨야 한다면 그 위치에서 다시 만든다. CUDA 라이브러리는 전용 PyTorch wheel을 사용하며 시스템 CUDA/PATH를 변경하지 않는다. Python 실행 중에만 PyTorch DLL 폴더를 추가한다.

## 실행 설정과 캐시

기본 설정은 `--language ko --model large-v3 --device cuda --compute-type int8_float16 --batch-size 1`. 메모리를 아끼기 위해 전사 모델을 해제한 뒤 정렬 모델을 올린다. WhisperX의 Silero 처리 로직에 공식 `silero-vad` 패키지의 내장 모델을 전달해 매번 Torch Hub/GitHub를 조회하지 않는다. 자동 화자 분리는 수행하지 않으므로 화자는 unknown이다. HF 토큰을 요구하는 화자 분리는 별도 구성이 필요할 때 추가한다.

캐시 준비 후에는 `--offline`으로 Hugging Face 네트워크 조회 없이 실행할 수 있다. NLTK `punkt_tab`도 모델 캐시의 `nltk/tokenizers` 아래에 준비되어 있어야 한다. `--align-model <local-dir-or-repo>`로 정렬 모델을 지정할 수도 있다. 스킬 복사본에는 모델이나 문장 분리 데이터가 포함되지 않는다. 기존 캐시 여부를 확인한 뒤 `--offline`을 사용한다.

Windows 환경에서는 pyannote의 선택적 TorchCodec 디코더 경고가 나올 수 있다. 이 스크립트는 FFmpeg로 디코딩한 메모리 오디오와 Silero를 사용하며 해당 디코더를 호출하지 않는다. pyannote 파일 디코딩/화자 분리를 추가할 때는 별도로 검증한다.

CUDA를 쓸 수 없는 환경에서는 명시적으로 `--device cpu --compute-type int8`를 선택할 수 있다. CPU 속도와 다른 GPU에서의 동작까지 검증된 것으로 표현하지 않는다. 입력은 첫 영상/음성 스트림이 있는 로컬 영상이며, 음성 스트림이 없으면 오류로 종료한다.

## 결과와 수정

- `audio.wav`: 첫 오디오 스트림을 mono 16kHz로 디코딩한 파일.
- `transcript.raw.json`: ASR 원문과 음성 기준 구간. 수정 전 파일을 보존한다.
- `transcript.aligned.json`: 정렬 원본. 시각은 추출 음성 시작 기준.
- `transcript.json`: 원본 영상 첫 프레임 기준으로 변환한 대사·단어 시각, 정렬 점수, 미정렬 단어 목록.
- `transcript.md`: 검토용 대사·시간 표.
- `job.json`: 실행 버전·설정·성공/실패 상태. 첫 실행 시간에는 다운로드가 포함될 수 있다.

기존 결과를 덮어쓰지 않도록 새 출력 폴더를 사용한다. 정렬 단계가 실패해도 원문은 보존되므로 재전사하지 않고 재정렬할 수 있다. `transcript.raw.json`을 별도 파일로 복사해 오인식한 text를 수정하고 다음처럼 실행한다.

```powershell
& $speechPython -X utf8 $speechScript "$projectRoot/input.mp4" --cache-dir $modelCache --transcript "$projectRoot/analysis/speech/corrected.raw.json" --output-dir "$projectRoot/analysis/speech/realigned01" --offline
```

이 재정렬 예제는 앞에서 준비한 Python·스크립트·캐시 변수와 이미 캐시된 정렬 모델을 사용한다. 필요한 모델이 없는 새 환경에서 다운로드를 허용해 실행할 때만 `--offline`을 생략한다. 수정 파일의 source_sha256, language, time_reference를 유지한다. start/end는 원본 영상 기준이 아니라 추출 음성 기준이다. 구간 밖의 발화를 끼워 넣지 않는다. 스크립트는 다른 영상의 원문을 잘못 적용하지 않도록 해시와 시간 기준을 검사한다.

## 분석 스킬에 연결

이 결과는 전사 초안이다. 음성 스트림/추출만 확인한 상태와 실제 모델 전사를 구분하되, ASR을 실행했다고 청취 검증까지 했다고 쓰지 않는다. `review_status=machine_draft`, `listening_verified=false`가 기본이다.

1. 원문 대사와 제품명·숫자·짧은 감탄사를 확인한다. 화면 자막은 비교 단서이며 정답 대본으로 복사하지 않는다.
2. 필요한 수정 후 정렬한다. 정렬 점수는 전사 문장의 정확도 확률이 아니다. `review_word_ids`는 점수 0.3 미만을 우선 검토하도록 남기는 휴리스틱이며 그 이상이라고 정확하다는 뜻이 아니다. 구간 양 끝, 빠른 대화, 겹친 발화, 영문·숫자, 음악이 큰 부분을 우선 검토한다.
3. 미정렬 단어와 0길이 단어는 null 시각으로 남긴다. 근처 단어의 시간을 자동 배분해 확정 시각처럼 사용하지 않는다. 출력의 문장 구간은 화자 턴이 아니며 한 구간에 여러 화자가 포함될 수 있다. 화자와 화면 안/밖 발화 방식은 별도 관찰로 결정한다.
4. `analysis.json`에 옮길 때는 `dialogue`의 ID·내용·시각을 활용하되 시각의 basis는 검증 전 estimated다. 오디오가 영상 앞/뒤로 벗어나는 구간을 숨기거나 무조건 잘라내지 말고 기존 영상 타임라인 규격과의 차이를 기록한다.
5. 원본 음성 PTS와 영상 첫 프레임 PTS의 차이는 이미 `transcript.json`에 반영되어 있다. 중복 가산하지 않는다. 발화 구간과 단어 시각을 이용해 [대사·화면 관계](semantic-direction.md)를 분석한다. 시간상 인접하다는 이유만으로 인과관계를 확정하지 않는다.

단어 단위 정렬 성공률만으로 전사 정확도를 평가하지 않는다. 음성 미검출도 무발화의 증거가 아니다. WhisperX는 대사와 시간을 제공하며 표정·카메라·연출 관계를 분석하지 않는다.

공식 근거: [WhisperX](https://github.com/m-bain/whisperX), [한국어 정렬 모델 목록](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py), [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
