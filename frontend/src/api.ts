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
  status: 'idle' | 'running' | 'done' | 'error'
  progress: number
  message: string
  error: string | null
}

export interface OutroLine {
  text: string
  y: number
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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  createProject: () => request<Project>('/projects', { method: 'POST' }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  upload: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Project>(`/projects/${id}/upload`, { method: 'POST', body: form })
  },
  transcribe: (id: string) => request<Transcript>(`/projects/${id}/transcribe`, { method: 'POST' }),
  saveTranscript: (id: string, transcript: Transcript) =>
    request<Transcript>(`/projects/${id}/transcript`, json('PUT', transcript)),
  saveStyle: (id: string, style: Style) => request<Project>(`/projects/${id}/style`, json('PUT', style)),
  saveCrop: (id: string, crop: CropWindow) => request<Project>(`/projects/${id}/crop`, json('PUT', crop)),
  render: (id: string) => request<RenderStatus>(`/projects/${id}/render`, { method: 'POST' }),
  renderStatus: (id: string) => request<RenderStatus>(`/projects/${id}/render-status`),
  church: () => request<ChurchInfo>('/church'),
  fonts: () => request<FontFamily[]>('/fonts'),
  outroConfig: () => request<OutroConfig>('/outro'),
  saveOutro: (config: OutroConfig) => request<OutroConfig>('/outro', json('PUT', config)),
  uploadOutroBackground: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ image: string }>('/outro/background', { method: 'POST', body: form })
  },
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
  job: RenderStatus | null
}

export const serviceApi = {
  create: () => request<Service>('/services', { method: 'POST' }),
  get: (id: string) => request<Service>(`/services/${id}`),
  upload: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Service>(`/services/${id}/upload`, { method: 'POST', body: form })
  },
  transcribe: (id: string) => request<Service>(`/services/${id}/transcribe`, { method: 'POST' }),
  analyze: (id: string) => request<Service>(`/services/${id}/analyze`, { method: 'POST' }),
  saveCandidates: (id: string, candidates: ClipCandidate[]) =>
    request<ClipCandidate[]>(`/services/${id}/candidates`, json('PUT', candidates)),
  processSelected: (id: string) => request<Service>(`/services/${id}/process-selected`, { method: 'POST' }),
  sourceUrl: (id: string) => `/services/${id}/source`,
}
