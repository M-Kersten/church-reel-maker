import { useEffect, useState } from 'react'
import { api, type FontFamily, type FontWeight } from './api'
import { cssWeight } from './subtitleLayout'

export const WEIGHT_LABELS: Record<FontWeight, string> = {
  regular: 'Normaal',
  medium: 'Medium',
  semibold: 'Halfvet',
  bold: 'Vet',
  extrabold: 'Extra vet',
}

const FILE_WEIGHT: Record<FontWeight, string> = {
  regular: 'Regular',
  medium: 'Medium',
  semibold: 'SemiBold',
  bold: 'Bold',
  extrabold: 'ExtraBold',
}

let pending: Promise<FontFamily[]> | null = null

/** Declare every font file the backend found, so the browser shows the same faces as the render. */
function declare(families: FontFamily[]): FontFamily[] {
  const rules = families
    .filter((f) => f.stem)
    .flatMap((f) =>
      f.weights.map(
        (w) =>
          `@font-face{font-family:'${f.name}';font-weight:${cssWeight(w)};font-style:normal;font-display:swap;` +
          `src:url('/templates/fonts/${f.stem}-${FILE_WEIGHT[w]}.ttf') format('truetype');}`,
      ),
    )
  const style = document.createElement('style')
  style.dataset.fonts = 'church-reel-maker'
  style.textContent = rules.join('\n')
  document.head.appendChild(style)
  return families
}

/** The font families the app can use. Loaded once and cached for the whole page. */
export function useFonts(): FontFamily[] {
  const [families, setFamilies] = useState<FontFamily[]>([])
  useEffect(() => {
    pending ??= api.fonts().then(declare)
    let alive = true
    pending.then((f) => alive && setFamilies(f)).catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return families
}

export function weightsOf(families: FontFamily[], name: string): FontWeight[] {
  return families.find((f) => f.name === name)?.weights ?? ['regular', 'bold']
}

/** Nearest weight the family actually has, mirroring backend/fonts.py. */
export function resolveWeight(families: FontFamily[], name: string, weight: FontWeight): FontWeight {
  const available = weightsOf(families, name)
  if (available.includes(weight)) return weight
  const order: FontWeight[] = ['regular', 'medium', 'semibold', 'bold', 'extrabold']
  const from = order.indexOf(weight)
  const search = [...order.slice(from), ...order.slice(0, from).reverse()]
  return search.find((w) => available.includes(w)) ?? 'regular'
}
