// Reading the path the crop walks when it follows the speaker. Mirror of the same lookup
// in backend/renderer.py: the preview has to show the frame where the render will put it.
import type { CropWindow, Track } from './api'

/**
 * Where the frame sits at `seconds`.
 *
 * The path is evenly spaced from the start of the clip, so the sample is found by dividing
 * rather than searching, and the two nearest are mixed. Before the first sample and after
 * the last it holds still, which is what the render does too: sendcmd keeps the last value
 * it was given.
 */
export function trackAt(track: Track, seconds: number): number | null {
  if (!track.x.length) return null
  const place = Math.max(0, seconds) * track.fps
  const first = Math.floor(place)
  if (first >= track.x.length - 1) return track.x[track.x.length - 1]
  // The frame jumped here rather than gliding; sliding into it would undo the cut.
  if (track.jumps.includes(first + 1)) return track.x[first]
  const part = place - first
  return track.x[first] + (track.x[first + 1] - track.x[first]) * part
}

/** The crop window at `seconds`: the user's height and zoom, on the path's x. */
export function cropAt(crop: CropWindow, track: Track | null, following: boolean, seconds: number): CropWindow {
  if (!following || !track) return crop
  const x = trackAt(track, seconds)
  return x === null ? crop : { ...crop, x }
}

/** How much of the clip the speaker was actually found in, as a percentage for the reader. */
export const foundShare = (track: Track | null): number => Math.round((track?.coverage ?? 0) * 100)
