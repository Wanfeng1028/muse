export type VoWord = {
  text: string
  start: number
  end: number
}

// Shape written by vo_build.py into src/data/vo-<variant>.generated.ts (times in seconds, relative to the file).
export type VoLine = {
  id: string
  text: string
  file: string
  duration: number
  words: VoWord[]
  estimated?: boolean
}

export type SceneSpan = {
  id: string
  start: number
  end: number
  background: string
}

export type TimeSpan = {
  start: number
  end: number
}

// A sound that belongs to the product (an app voice, a notification) and must sit inside a pause of the VO.
export type DiegeticCue = {
  id: string
  file: string
  at: number
  duration: number
}

// A source range of the track. Segments play back to back from MUSIC.at (mix.py joins them with an
// equal-power splice); cut on bars.
export type MusicSegment = {
  sourceStart: number
  sourceEnd: number
}
