import { useEffect, useState } from 'react'
import { api, type ChurchInfo } from './api'

/** Tells every part of the page that the active brand changed. */
export const announceBrandChange = () => window.dispatchEvent(new Event('brand-changed'))

/** Opens the brand menu from wherever you are, on the tab that holds what you need. */
export const openBrand = (tab?: 'church' | 'words' | 'outro') =>
  window.dispatchEvent(new CustomEvent('open-brand', { detail: tab }))

/** The church of the active brand, kept up to date when the brand is switched or edited. */
export function useChurch(): ChurchInfo | null {
  const [church, setChurch] = useState<ChurchInfo | null>(null)
  useEffect(() => {
    const load = () => api.church().then(setChurch).catch(() => setChurch(null))
    load()
    window.addEventListener('brand-changed', load)
    return () => window.removeEventListener('brand-changed', load)
  }, [])
  return church
}
