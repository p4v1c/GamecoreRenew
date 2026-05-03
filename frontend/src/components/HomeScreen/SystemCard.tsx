import { hexToRgb, fmtTime, fmtDate } from '../ui'
import { SystemEntry, PlaytimeEntry } from '../../api'
import { SYSTEM_COLORS } from '../../lib/systemColors'

function getColor(system: SystemEntry): string {
  return system.color || SYSTEM_COLORS[system.id.toLowerCase()] || '#7c3aed'
}

interface Props {
  system: SystemEntry
  playtime?: PlaytimeEntry
  gameCount?: number
  focused: boolean
  onClick: () => void
}

export default function SystemCard({ system, playtime, gameCount, focused, onClick }: Props) {
  const color = getColor(system)
  const rgb = hexToRgb(color)

  return (
    <div
      onClick={onClick}
      tabIndex={0}
      onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onClick()}
      style={{
        padding: '20px 18px', borderRadius: 14, cursor: 'pointer',
        background: focused ? `rgba(${rgb}, 0.12)` : 'rgba(255,255,255,0.04)',
        border: focused ? `1px solid ${color}60` : '1px solid rgba(255,255,255,0.07)',
        transition: 'all 0.2s cubic-bezier(0.4,0,0.2,1)',
        transform: focused ? 'translateY(-3px) scale(1.02)' : 'translateY(0) scale(1)',
        boxShadow: focused ? `0 12px 32px rgba(${rgb}, 0.25)` : 'none',
        outline: 'none',
        userSelect: 'none',
      }}
    >
      {/* Header: icon + name */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 46, height: 46, borderRadius: 12, flexShrink: 0,
          background: focused ? color : `rgba(${rgb}, 0.2)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transition: 'background 0.2s', overflow: 'hidden',
        }}>
          {system.iconPath ? (
            <img
              src={`/assets/logos/${system.iconPath.split('/').pop()}`}
              alt={system.id}
              style={{ width: 28, height: 28, objectFit: 'contain', filter: focused ? 'brightness(0) invert(1)' : 'none', transition: 'filter 0.2s' }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ) : (
            <span style={{ fontSize: 20, color: focused ? '#fff' : color }}>{system.label?.[0] || system.id[0].toUpperCase()}</span>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#fff', lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {system.label || system.platform || system.id}
          </div>
          <div style={{ fontSize: 10, fontWeight: 600, color, letterSpacing: 2, marginTop: 3 }}>
            {system.id.toUpperCase()}
          </div>
        </div>
        {system.kind === 'app' && (
          <div style={{ marginLeft: 'auto', fontSize: 10, color: 'rgba(255,255,255,0.3)', background: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            APP
          </div>
        )}
      </div>

      {/* Footer: game count + playtime */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          {system.kind !== 'app' && (
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)' }}>
              {gameCount ?? 0} {gameCount === 1 ? 'game' : 'games'}
            </div>
          )}
          {playtime?.last_played && (
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.2)', marginTop: 2 }}>
              Last: {fmtDate(playtime.last_played)}
            </div>
          )}
        </div>
        {playtime && playtime.total_secs > 0 && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: focused ? color : 'rgba(255,255,255,0.5)' }}>
              {fmtTime(playtime.total_secs)}
            </div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', marginTop: 1 }}>played</div>
          </div>
        )}
      </div>
    </div>
  )
}
