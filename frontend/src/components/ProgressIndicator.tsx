import type { RenderStatus } from '../api'

export default function ProgressIndicator({ status }: { status: RenderStatus }) {
  if (status.status === 'idle') return null
  if (status.status === 'cancelled') return <p className="hint">Gestopt. Je kunt het opnieuw proberen.</p>
  const percent = Math.round((status.status === 'done' ? 1 : status.progress) * 100)
  return (
    <div className={`progress ${status.status === 'error' ? 'error' : ''}`}>
      <div className="bar">
        <div style={{ width: `${status.status === 'error' ? 100 : percent}%` }} />
      </div>
      <div className="label">
        <span>{status.status === 'error' ? `Het maken is mislukt: ${status.error}` : status.message}</span>
        <span>{status.status === 'error' ? '' : `${percent}%`}</span>
      </div>
    </div>
  )
}
