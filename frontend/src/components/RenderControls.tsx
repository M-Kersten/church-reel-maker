import type { RenderStatus } from '../api'
import ProgressIndicator from './ProgressIndicator'

interface Props {
  canTranscribe: boolean
  transcribing: boolean
  canRender: boolean
  renderStatus: RenderStatus
  outputUrl: string | null
  onTranscribe: () => void
  onRender: () => void
}

export default function RenderControls(props: Props) {
  const rendering = props.renderStatus.status === 'running'
  return (
    <section className="panel">
      <h2>Actions</h2>
      <div className="render-actions">
        <button onClick={props.onTranscribe} disabled={!props.canTranscribe || props.transcribing || rendering}>
          {props.transcribing ? 'Transcribing…' : 'Transcribe'}
        </button>
        <button className="primary" onClick={props.onRender} disabled={!props.canRender || rendering || props.transcribing}>
          {rendering ? 'Rendering…' : 'Render video'}
        </button>
        {props.outputUrl && props.renderStatus.status === 'done' && (
          <a href={props.outputUrl} download>
            Download final.mp4
          </a>
        )}
      </div>
      <ProgressIndicator status={props.renderStatus} />
    </section>
  )
}
