# 출력 규격

JSON 키는 영어, 설명 값은 기본 한국어로 작성한다. 시간은 원본 영상 시작을 0으로 하는 초 단위 숫자이며 구간은 [start, end)이다. 아래는 형식 설명용 가상 2초 영상으로 실제 분석 결과가 아니다.

이 JSON은 원본 관찰 전용이다. 대사와 화면의 관계 표는 분석 문서에 함께 제공하고, 새 대본·연출 계획·Seedance 프롬프트는 별도 산출물로 작성한다. [대사 기반 연출 가이드](semantic-direction.md)의 형식을 따른다. 새 대사의 예상 길이를 원본 `timeline`이나 `dialogue`에 덮어쓰지 않는다. 기존 검사 스크립트는 별도 연출 계획이나 프롬프트를 검증하지 않는다.

```json
{
  "schema_version": "1.1",
  "video": {
    "source": "example.mp4",
    "duration_s": 2.0,
    "duration_scope": "video_stream",
    "container_duration_s": 2.0,
    "aspect_ratio": "9:16",
    "audio_stream_present": true,
    "audio_status": "verified_present"
  },
  "observation": {
    "method": "영상 재생 및 음성 청취",
    "coverage": [{"start": 0.0, "end": 2.0}],
    "coverage_modality": "visual_playback",
    "audio_coverage": [{"start": 0.0, "end": 2.0}],
    "review_log": [],
    "limitations": []
  },
  "dialogue": [
    {
      "id": "d1",
      "start": 0.4,
      "end": 1.6,
      "text": "이거 한번 보세요.",
      "speaker": "인물 A",
      "delivery": "on_camera",
      "timing": {"basis": "estimated", "uncertainty_s": 0.2},
      "evidence": "원본 오디오 청취"
    }
  ],
  "timeline": [
    {
      "id": "s1",
      "shot_id": "shot1",
      "start": 0.0,
      "end": 2.0,
      "timing": {"basis": "measured", "uncertainty_s": 0.04},
      "camera": {
        "framing": "미디엄 클로즈업",
        "angle": "눈높이",
        "movement": "고정"
      },
      "action": "인물 A가 제품을 가슴 높이에서 렌즈 가까이 들어 올린다.",
      "dialogue_ids": ["d1"],
      "direction_observed": "발화 도중 제품이 화면 중앙으로 들어온다.",
      "editing": {"transition_in": "start", "speed": "정상 속도로 보임"},
      "postproduction": [],
      "role_inferred": "HOOK",
      "evidence": "0.0초와 1.0초 프레임 및 구간 재생",
      "uncertainties": []
    }
  ],
  "recreation_notes": {
    "preserve": ["첫 대사 중 제품을 렌즈 가까이 제시하는 타이밍"],
    "replace": ["제품", "인물", "대사 내용"]
  }
}
```

## 필드 규칙

- `duration_s`: 영상 첫 프레임을 0으로 한 영상 표시 종료 시각. `duration_scope`는 video_stream. 컨테이너 길이가 다르면 `container_duration_s`, 필요하면 `audio_duration_s`를 별도로 기록한다. 오디오 꼬리를 가상 컷으로 추가하지 않는다.
- `audio_stream_present`: true / false / null. 스트림 검사 결과이며 청취 여부와 무관하다. 추출 실패를 false로 바꾸지 않는다.
- `audio_status`: verified_present / verified_absent / unverified. 실제 소리가 확인되었는지 나타내며, verified_present만으로 발화가 있다는 뜻은 아니다. 스트림만 확인했거나 파일만 추출했다면 unverified. 무음 또는 스트림 부재를 확인했을 때만 verified_absent.
- `observation.coverage`는 실제 관찰한 영상 구간, `coverage_modality`는 visual_sampled / visual_all_frames / visual_playback 중 가장 적절한 값. 혼합 관찰은 method와 review_log에 기록한다. `audio_coverage`는 실제 청취/전사한 구간이며 미확인일 때 빈 배열. 시각 관찰을 음향 관찰로 확장하지 않는다.
- `observation.review_log`: 선택 필드. 재관찰한 경우 `[{start, end, reason, method, finding, evidence}]`로 후보 컷 채택/기각과 짧은 동작의 근거를 남긴다. 자동 검출 후보를 확정 컷으로 취급하지 않는다.
- `timing.basis`: measured / estimated / unknown. 전사 도구의 발화 시간은 정렬·청취 검증 전에는 estimated로 둔다. `uncertainty_s`는 근거 있는 오차 범위가 있을 때만 수치로, 모르면 null로 둔다. 소수 자릿수가 정확도를 의미하지 않는다.
- 한 행의 시작/종료 정밀도가 다르면 `boundary_timing: {start: {basis, uncertainty_s}, end: {basis, uncertainty_s}}`를 선택적으로 추가한다. 기존 `timing`은 두 경계 중 낮은 정밀도로 요약한다. 프레임 간격은 측정 해상도이며 판정의 정확성을 보장하지 않는다.
- `shot_id`: 동일 롱테이크의 하위 비트끼리 동일한 값. 실제 컷마다 새 값. 같은 숏의 후속 비트는 `transition_in`을 continuous로 쓴다.
- 겹침 전환은 새 숏을 첫 혼합 프레임부터 시작하는 규칙으로 표·JSON을 일치시키고, `editing.transition_window: {start, end, evidence}`에 첫 혼합 프레임부터 새 장면만 남은 시각까지 기록한다. 하드컷/점프컷은 새 숏 첫 프레임을 경계로 쓴다. 알 수 없는 경계는 추정으로 남긴다.
- `dialogue`: 발화가 확인되어 없으면 빈 배열. 확인하지 못했어도 빈 배열일 수 있으므로 observation.limitations에 명시한다. 대사 내용만 알면 start/end를 null로 둔다. speaker를 모르면 unknown, delivery는 on_camera / voiceover / offscreen / unknown 중 하나.
- `postproduction`: 화면 문구·그래픽·음악·효과음 중 재창작에 중요한 것만 기록한다. 필요하면 start/end와 관찰된 내용을 가진 객체 배열로 작성한다. 자막과 발화 내용이 같다고 추정하지 않는다.
- `role_inferred`: HOOK / DEMO / PROOF / CTA 등 관찰에서 추론한 역할. 맞지 않으면 다른 짧은 이름 또는 null을 쓴다.
- `action`에 세부 타이밍이 필요하면 선택 필드 `action_beats: [{start, end, action, timing}]`를 추가한다. 이 시간도 원본 기준이다.
- 관찰 범위가 부분적이면 누락 구간을 명시하고 전체 분석이라고 표현하지 않는다. 전체 분석의 timeline은 0부터 duration_s까지 빈틈과 겹침 없이 이어져야 한다. 경계가 추정이면 그 정밀도를 명시한다.
- 발화는 컷 경계를 넘어갈 수 있다. 겹치는 모든 컷에서 해당 dialogue ID를 참조한다. 다중 화자의 발화끼리 겹치는 것은 오류가 아니다.
- 모든 참조 ID의 존재, start < end, 영상 길이 안의 시각, 표와 JSON의 일치를 확인한다. 불명 값은 null로 표현한다. 출력에 설명용 가상 예시를 실제 관찰처럼 포함하지 않는다.
