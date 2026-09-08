export type FontWeight = 'regular' | 'medium' | 'semibold' | 'bold' | 'extrabold'

export interface Style {
  font: string
  fontSize: number
  fontWeight: FontWeight
  color: string
  outline: number
  outlineColor: string
  background: boolean
}

export interface Output {
  width: number
  height: number
  fps: number
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  language: string
  segments: Segment[]
}

export interface VideoInfo {
  width: number
  height: number
  duration: number
  fps: number
  videoCodec: string | null
  hasAudio: boolean
  audioCodec: string | null
  audioSampleRate: number | null
  audioChannels: number | null
}

export interface ClipOrigin {
  serviceId: string
  candidateId: string | null
  start: number
  end: number
}

export interface CropWindow {
  /** Centre of the 9:16 frame as a fraction of the scaled source (0.5 = centred). */
  x: number
  y: number
  /** 1 fills the frame, smaller letterboxes, larger crops in further. */
  zoom: number
}

export interface Project {
  id: string
  createdAt: string
  title: string | null
  origin: ClipOrigin | null
  sourceVideo: string | null
  sourceInfo: VideoInfo | null
  transcript: string | null
  style: Style
  output: Output
  outro: string
  cropStrategy: 'static' | 'tracked'
  crop: CropWindow
  tracking: string | null
  transcriptData: Transcript | null
}

export interface RenderStatus {
  status: 'idle' | 'running' | 'done' | 'error' | 'cancelled'
  progress: number
  message: string
  error: string | null
  canStop?: boolean
}

export interface HealthCheck {
  name: string
  ok: boolean
  detail: string
}

export interface Health {
  ok: boolean
  checks: HealthCheck[]
}

/** What one analysis run would send to the model, and what it costs. */
export interface AnalysisEstimate {
  provider: string
  model: string
  windows: number
  tokens: number
  costUsd: number
}

export interface OutroLine {
  text: string
  y: number
  align: 'left' | 'center' | 'right'
  size: number
  weight: FontWeight
  color: string
  font: string
  spacing: number
  uppercase: boolean
  delay: number
}

export interface OutroConfig {
  generate: boolean
  duration: number
  font: string
  fade: number
  background: { type: 'solid' | 'gradient' | 'image'; color: string; colors: string[]; angle: number; image: string; darken: number }
  logo: { file: string; width: number; y: number }
  lines: OutroLine[]
}

export interface FontFamily {
  name: string
  /** File-name prefix in /templates/fonts; empty for the system font. */
  stem: string
  weights: FontWeight[]
}

export interface ChurchInfo {
  churchName: string
  serviceTimes: string[]
  instagram: string
}

/** An error from the API. `offline` means the app itself could not be reached. */
export class ApiError extends Error {
  offline: boolean
  constructor(message: string, offline = false) {
    super(message)
    this.offline = offline
  }
}

export const OFFLINE_MESSAGE = 'Geen verbinding met de app. Staat het zwarte venster nog open?'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new ApiError(OFFLINE_MESSAGE, true)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    if (res.status >= 500 && !detail) detail = 'De app kon dit niet verwerken. Kijk in het zwarte venster voor details.'
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

/** Upload with a progress callback; fetch cannot report how much has been sent. */
function upload<T>(url: string, file: File, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data: { detail?: string } = {}
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        reject(new ApiError(`Onverwacht antwoord van de app (${xhr.status}).`))
        return
      }
      if (xhr.status >= 400) reject(new ApiError(data.detail ?? `Uploaden mislukt (${xhr.status}).`))
      else resolve(data as T)
    }
    xhr.onerror = () => reject(new ApiError(OFFLINE_MESSAGE, true))
    xhr.ontimeout = () => reject(new ApiError('Het uploaden duurde te lang.', true))
    xhr.send(form)
  })
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  createProject: () => request<Project>('/projects', { method: 'POST' }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  upload: (id: string, file: File, onProgress?: (fraction: number) => void) =>
    upload<Project>(`/projects/${id}/upload`, file, onProgress),
  transcribe: (id: string) => request<Transcript>(`/projects/${id}/transcribe`, { method: 'POST' }),
  saveTranscript: (id: string, transcript: Transcript) =>
    request<Transcript>(`/projects/${id}/transcript`, json('PUT', transcript)),
  saveStyle: (id: string, style: Style) => request<Project>(`/projects/${id}/style`, json('PUT', style)),
  saveCrop: (id: string, crop: CropWindow) => request<Project>(`/projects/${id}/crop`, json('PUT', crop)),
  render: (id: string) => request<RenderStatus>(`/projects/${id}/render`, { method: 'POST' }),
  stopRender: (id: string) => request<RenderStatus>(`/projects/${id}/render/stop`, { method: 'POST' }),
  health: () => request<Health>('/health'),
  renderStatus: (id: string) => request<RenderStatus>(`/projects/${id}/render-status`),
  church: () => request<ChurchInfo>('/church'),
  fonts: () => request<FontFamily[]>('/fonts'),
  outroConfig: () => request<OutroConfig>('/outro'),
  saveOutro: (config: OutroConfig) => request<OutroConfig>('/outro', json('PUT', config)),
  uploadOutroBackground: (file: File) => upload<{ image: string }>('/outro/background', file),
  rebuildOutro: () => request<OutroConfig>('/outro/rebuild', { method: 'POST' }),
  sourceUrl: (id: string) => `/projects/${id}/source`,
  outputUrl: (id: string) => `/projects/${id}/output`,
  outroUrl: (version = 0) => `/templates/outro.mp4?v=${version}`,
}

// --- full-service clip discovery ---------------------------------------------

export type ServiceStatus =
  | 'created' | 'uploaded' | 'transcribing' | 'transcribed' | 'analyzing' | 'ready' | 'processing' | 'complete' | 'error'

export interface TimeRange {
  start: number
  end: number
}

export interface ClipCandidate {
  id: string
  start: number
  end: number
  title: string
  summary: string
  reason: string
  confidence: number
  selected: boolean
  score: number
  alternateBoundaries: TimeRange[]
}

export interface ProcessedClip {
  candidateId: string
  projectId: string
  title: string
  start: number
  end: number
  createdAt: string
}

export interface Service {
  id: string
  createdAt: string
  title: string
  sourceVideo: string | null
  sourceInfo: VideoInfo | null
  transcript: string | null
  status: ServiceStatus
  error: string | null
  candidates: ClipCandidate[]
  clips: ProcessedClip[]
  transcriptData: Transcript | null
  analysis: AnalysisEstimate | null
  job: RenderStatus | null
}

export const serviceApi = {
  create: () => request<Service>('/services', { method: 'POST' }),
  get: (id: string) => request<Service>(`/services/${id}`),
  upload: (id: string, file: File, onProgress?: (fraction: number) => void) =>
    upload<Service>(`/services/${id}/upload`, file, onProgress),
  transcribe: (id: string) => request<Service>(`/services/${id}/transcribe`, { method: 'POST' }),
  analyze: (id: string) => request<Service>(`/services/${id}/analyze`, { method: 'POST' }),
  saveCandidates: (id: string, candidates: ClipCandidate[]) =>
    request<ClipCandidate[]>(`/services/${id}/candidates`, json('PUT', candidates)),
  processSelected: (id: string) => request<Service>(`/services/${id}/process-selected`, { method: 'POST' }),
  stop: (id: string) => request<Service>(`/services/${id}/stop`, { method: 'POST' }),
  sourceUrl: (id: string) => `/services/${id}/source`,
}
