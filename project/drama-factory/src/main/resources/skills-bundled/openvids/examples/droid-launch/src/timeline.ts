/**
 * Single source of truth for timing. Shared by the video (Film.tsx) and the
 * audio engine (audio/build.py reads public/timeline.json, generated from this).
 * All values in frames @ 30fps. Scene-local cue frames are relative to scene start.
 */
export const SCENES = [
  { id: "S1", name: "Cursor → Rotor", from: 0, dur: 180 },
  { id: "S2", name: "Same models", from: 180, dur: 300 },
  { id: "S3", name: "Different harness", from: 480, dur: 300 },
  { id: "S4", name: "Droid at work", from: 780, dur: 360 },
  { id: "S5", name: "Plans + limits", from: 1140, dur: 300 },
  { id: "S6", name: "Droid Core", from: 1440, dur: 360 },
  { id: "S7", name: "The thesis", from: 1800, dur: 240 },
  { id: "S8", name: "Receipt", from: 2040, dur: 210 },
] as const;

export const TOTAL_FRAMES = 2250;

/**
 * Audio cues (scene-local frames). Scene authors MUST animate the matching
 * visual event exactly on these frames so picture and sound lock.
 */
export const CUES = {
  S1: {
    keystrokes: [30, 36, 41, 48, 54], // d r o i d
    enter: 66,
    rotorForm: 78, // cursor pixels assemble into rotor
    rotorSpin: 132, // rotor spin-up begins; blades sweep frame to dark by 172
  },
  S2: {
    chipLand: [40, 52, 64, 76, 88], // five model chips land (ascending pentatonic)
    lanes: 130, // harness lanes draw in
    headline: 20, // "Same models." settles
  },
  S3: {
    headline: 10, // "Different harness."
    raceStart: 60,
    raceWin: 170, // Droid bar passes the rest; counter locks at 58.75%
    growToTerminal: 250,
  },
  S4: {
    keystrokes: [20, 25, 29, 34, 38, 43, 47, 52, 56, 61, 65, 70],
    specOk: 100,
    fanOut: 150, // subagent branches split
    checks: [210, 222, 234, 246, 258], // each subagent ✓ (glass ping, chord forms)
    merge: 300, // branches collapse into one line
  },
  S5: {
    cards: [20, 32, 44], // $20 / $100 / $200 cards land
    meterFill: 120, // usage meter + rings start
    meterFull: 228, // 100% — silence for ~12 frames
    pageFlip: 252, // cream page turn
  },
  S6: {
    coreRise: 24, // Droid Core meter rises (warm sub swell)
    modelsPour: [70, 82, 94, 106, 118, 130, 142, 154], // open-model wordmarks drop in
    caption: 200, // "Usage ran out. Work didn't."
    merge: 318, // meters rotate into ⊕
  },
  S7: {
    line1: 10,
    line2: 70,
    fallaway: [110, 122, 134], // competitor cards grey + fall
    zoom: 196, // surviving card zooms to fill
  },
  S8: {
    printStart: 20,
    printLines: [34, 46, 58, 70, 82, 94],
    stamp: 130,
    tear: 176,
  },
} as const;
