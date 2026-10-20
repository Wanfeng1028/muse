# 로컬 관찰

Python 표준 라이브러리와 PATH의 FFmpeg/ffprobe를 사용한다. 컨택트시트 라벨에 사용할 폰트가 필요하며 Windows Arial, Linux DejaVu Sans, macOS Arial을 순서대로 탐색한다. 해당 폰트가 없으면 `--font <실제 폰트 파일 경로>`를 지정한다. 보조 스크립트는 모델·외부 서비스·패키지·폰트를 설치하지 않는다. 직접 영상 관찰이 가능한 환경에서는 해당 기능을 사용해도 된다.

## 추출과 재관찰

아래 명령은 스킬 폴더 기준이며 출력 위치는 스킬 밖의 새 폴더로 바꾼다. 같은 폴더의 기존 파일을 덮어쓰지 않는다.

```text
python scripts/extract_evidence.py <video.mp4> --output-dir <work>/overview --fps 1
python scripts/extract_evidence.py <video.mp4> --output-dir <work>/review --start 2.0 --end 4.0 --fps 8
python scripts/extract_evidence.py <video.mp4> --output-dir <work>/boundary --start 3.0 --end 3.4 --all-frames
```

- `sheet_*.jpg`를 열어 실제로 관찰한다. 작은 글자나 손 접촉이 안 보이면 개별 `frame_*.jpg` 또는 더 큰 `--width`로 재확인한다. 추출만 해두고 읽지 않은 프레임은 관찰 근거가 아니다.
- `manifest.json`은 각 이미지의 원본 프레임 번호, 원본 PTS, 영상 기준 시각, 시트 위치를 연결한다. 시트 라벨도 같은 영상 기준 시각이다. 파일 순번/출력 fps로 원본 시각을 추정하지 않는다.
- `--fps`는 목표 샘플 격자다. 각 시각 이후 첫 원본 프레임을 선택하고 구간 양 끝의 원본 프레임을 추가한다. VFR에서도 평균 fps로 시각을 계산하지 않으며, 프레임 복제/보간을 하지 않는다. `--all-frames`는 지정 구간에서 시작하는 원본 프레임을 모두 추출한다.
- 고정 15프레임 제한은 없다. 긴 영상은 구간을 나누고 실제 관찰 범위를 기록한다. 마지막 프레임의 표시 길이를 추정한 경우 manifest의 `duration_basis`에 표시된다.
- 회전은 FFmpeg 기본 autorotate로 반영된다. 메타데이터와 실제 표시 방향·비율이 일치하는지 확인한다. anamorphic 등 비정방형 픽셀 소스는 별도의 표시 비율 보정이 필요할 수 있다.

샘플 사이에서 물체/손/배경의 위치 변화가 설명되지 않으면 주변을 고밀도로 다시 본다. 동일 구도 안의 점프컷, 짧은 삽입컷, 짧은 자막도 후보에 포함한다. 한 구간에 여러 변화가 보이면 각각을 확인하고, 컷이 매우 빠르면 그 구간의 원본 프레임까지 확인한다. 4–8fps는 탐색 밀도이지 컷 검출 보장이 아니다.

FFmpeg 장면 변화 검출을 추가로 사용할 수 있지만 후보 탐색으로만 취급한다. 팬·문 회전·가림 해소·플래시는 오탐이 될 수 있고, 유사 구도 점프컷은 놓칠 수 있다. 전환 이전/이후 근거를 비교하고 `observation.review_log`에 채택/기각 이유를 짧게 남긴다. 겹침 전환은 첫 혼합 프레임부터 새 장면만 남는 시각까지 기록한다.

## 오디오와 시간 기준

- 전체 오디오 추출이 필요하면 개요 추출 명령에 `--with-audio`를 추가한다. `audio.wav`는 첫 오디오 스트림 전체를 mono 16kHz로 추출한 관찰용 파일이며, 시각 재관찰 구간에 맞춰 잘리지 않는다.
- `audio.stream_present`, `extraction_status`, `content_status`를 구분한다. 추출 실패는 무음의 증거가 아니다. 스크립트는 청취·전사를 하지 않으므로 내용 상태를 미확인으로 기록한다.
- 오디오 첫 시각과 영상 첫 시각의 차이는 `offset_from_video_s`로 보존한다. 이후 전사 시각을 원본 영상에 맞출 때 이 차이와 클립 오프셋을 반영한다. 값이 null이면 원본 시각을 추가 확인한다.
- 이미 준비된 전사 도구는 사용할 수 있지만 전사 초안의 시간은 정렬·청취 검증 전까지 추정이다. 접근 불가능한 음성 도구를 사용할 수 있다고 가정하지 않으며, 대용량 모델 설치·유료 연결을 기본 분석 단계로 만들지 않는다.
- 로컬 WhisperX가 준비되어 있으면 [전사 절차](speech-transcription.md)를 따른다. 전사 스크립트는 영상에서 음성을 따로 추출하고 원본 시각 차이를 반영하므로, 출력 시각에 manifest의 오프셋을 다시 더하지 않는다.
- 영상·오디오·컨테이너 길이를 구분한다. 기본 시각 타임라인은 첫 영상 PTS를 0으로 한 영상 표시 구간이며, 오디오만 남는 꼬리 구간은 별도 한계로 기록한다.

## 검토

전체 길이에 걸친 샘플 관찰과 전체 프레임 관찰을 구분한다. FFmpeg 추출과 AI 해석도 구분하며, 추출이 로컬이라는 이유로 전체 분석이 로컬 실행이거나 무료라고 설명하지 않는다. 프레임 준비와 JSON 검증을 통과했어도 내용의 정확성은 실제 관찰로 확인해야 한다.

## 참고한 방식

- [ByteDance viral creative rewrite](https://github.com/bytedance/agentkit-samples/blob/main/skills/byted-bp-seedance-viral-creative-rewrite-skill/SKILL.md): 기본 1fps 뒤 필요한 구간의 밀도를 높이는 관찰 방식, 행동 전후의 변화와 결과 확인.
- [Novoads analyze-video](https://github.com/novoads/agent-skills/blob/main/skills/analyze-video/SKILL.md): 카메라·편집·행동·대사 관계와 재사용할 패턴의 분리.

참고 지침의 관찰 개념을 반영했다. 외부 구현 코드를 복사하지 않았으며, 5초 요약 창이나 생성 모델 제약을 원본 컷 타임라인에 적용하지 않는다.
