# 제작 폴더 (production/)

긴 제작은 중간에 끊기고, 대화가 요약되면 결정이 흐려진다. 결정과 진행 상황을 파일로 남겨, 새 세션이 이 폴더만 읽고도 이어서 작업할 수 있게 한다. 파일은 짧게 쓴다.

```
production/
  brief.md          목적, 대상, 플랫폼, 길이, 필수 문구, 금지 사항, 룩, 도구 점검 결과
  assets/           실제 재료와 assets.md(출처와 권리)
  treatment.md      컨셉 비교, 고른 컨셉, 로그라인, 비트 흐름
  styleframes/      스타일프레임과 비교 시트, 사용자가 고른 것
  shotlist.json     BPM, 장면별 프레임, 효과음 큐, 음악 편집
  review.md         감독 리뷰 기록(회차별 실패 항목과 조치)
  progress.md       지금 어디까지 했고 다음에 무엇을 하는지
  look-lock.md      납품 때 승인된 룩과 코드 위치(시리즈 다음 편용)
deliverables/       납품 파일과 delivery.md
```

## brief.md

```markdown
# Brief
- 대상: {제품·행사 이름, URL}
- 목적: {예: 사전 접수 유도 / 가입 유도 / 기능 소개}
- 보는 사람: {예: 초·중·고 학생과 학부모, 초등 교사}
- 플랫폼과 길이: {예: 릴스 9:16 30초 + 유튜브 16:9 30초}
- 꼭 들어갈 것: {문구, 날짜, 시간, 주소. 원문 그대로}
- 넣지 말 것: {예: 부스 위치, 개인 연락처, 캐릭터}
- 룩: 참고 {영상·이미지}, 좋았던 점 {}, 싫은 것 {}, 밝기 {}, 밀도 {}, 사람·캐릭터 {}, 속도 {}
- 음원: {사용자 제공 / Pixabay 곡 이름 / 합성}
- 도구 점검: {preflight 결과 한 줄}
- 예상 시간과 위험: {예: 60초 2비율, 렌더 약 12분 포함 3~4시간}
```

## treatment.md

```markdown
# Treatment
## 후보 (스타일프레임: styleframes/concepts_sheet.jpg)
| 컨셉 | 첫 1초 | 로그라인 | 룩 | 제작 위험 |
|---|---|---|---|---|
## 선택: {컨셉 이름} (사용자가 고름: {날짜, 한 말})
로그라인: {한 문장}
비트 ({BPM}, 1박 = {n}프레임):
1. 훅:
2. 전개:
3. 핵심:
4. 행동 유도:
룩: {look.md 질문의 답, 고른 스타일프레임}
이전 편과 같은 점, 다른 점: {시리즈일 때. 룩은 유지하고 구성을 바꾼다}
```

## shotlist.json

`scripts/beat_grid.py ... --shotlist production/shotlist.json`으로 뼈대를 만들고, 음악과 효과음을 채운다.

```json
{
  "fps": 30, "bpm": 120, "totalFrames": 1800,
  "music": { "src": "music/song.mp3", "edit": [[7.89, 23.89], [43.89, 55.89], [75.89, null]], "gain_db": -2.5, "fade_out": 1.2 },
  "scenes": [{ "name": "hook", "from": 0, "durationInFrames": 180, "content": "", "text": "", "transition": "", "source": "" }],
  "cues": [{ "id": "hook_hit", "frame": 0, "sfx": [["thump", -6, "onset", 0]] }]
}
```

코드는 이 파일의 `from`, `durationInFrames`, `cues`를 그대로 읽어 쓴다. 타이밍을 바꿀 때는 파일을 고치고 믹스와 렌더를 다시 한다.

## review.md

```markdown
# Review {회차}
증거: {시트 파일 이름}
기준 대비: {기준보다 다른 점}
실패 (심각한 순):
1. {항목} — {근거 프레임} — {조치}
고친 것:
남긴 것과 이유:
```

## progress.md

매 단계가 끝날 때 세 줄로 갱신한다: 끝낸 것, 지금 도는 작업(백그라운드 렌더 포함), 다음 할 일. 세션을 이어받으면 이 파일부터 읽는다.

## assets.md

재료마다 출처 URL, 받은 날, 권리 상태(사용자 소유 / 확인 필요 / 생성물)를 적는다. 납품 보고의 "권리 확인이 필요한 것"은 이 표에서 뽑는다.

