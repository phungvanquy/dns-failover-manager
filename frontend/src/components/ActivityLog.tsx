import { useState, useEffect } from 'react'
import { api } from '../api'

interface EventItem {
  id: string
  domain_id: string
  domain_name: string
  old_ip: string | null
  new_ip: string
  reason: string
  created_at: string
}

const REASON_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  failover: { label: 'Failover', color: 'bg-red-100 text-red-700', icon: '🔴' },
  revert: { label: 'Reverted', color: 'bg-green-100 text-green-700', icon: '🟢' },
  manual: { label: 'Manual Switch', color: 'bg-purple-100 text-purple-700', icon: '⚡' },
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function ActivityLog() {
  const [events, setEvents] = useState<EventItem[]>([])
  const [expanded, setExpanded] = useState(true)

  const loadEvents = async () => {
    try {
      const data = await api.get<EventItem[]>('/events?limit=50')
      setEvents(data)
    } catch { /* ignore polling errors */ }
  }

  useEffect(() => {
    loadEvents()
    const interval = setInterval(loadEvents, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="bg-white rounded-lg shadow">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-50 rounded-t-lg"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">📋</span>
          <h2 className="font-semibold text-lg">Activity Log</h2>
          {events.length > 0 && (
            <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">{events.length}</span>
          )}
        </div>
        <span className="text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t max-h-[400px] overflow-y-auto">
          {events.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">No events yet</div>
          ) : (
            <div className="divide-y">
              {events.map(e => {
                const meta = REASON_LABELS[e.reason] || { label: e.reason, color: 'bg-gray-100 text-gray-700', icon: '⚪' }
                return (
                  <div key={e.id} className="px-4 py-3 flex items-start gap-3 hover:bg-gray-50">
                    <span className="text-lg mt-0.5">{meta.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm">{e.domain_name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${meta.color}`}>{meta.label}</span>
                      </div>
                      <div className="text-sm text-gray-500 mt-0.5 font-mono">
                        {e.old_ip && <span>{e.old_ip}</span>}
                        {e.old_ip && <span className="mx-1">→</span>}
                        <span className="font-medium text-gray-700">{e.new_ip}</span>
                      </div>
                    </div>
                    <span className="text-xs text-gray-400 whitespace-nowrap mt-1" title={new Date(e.created_at).toLocaleString()}>
                      {timeAgo(e.created_at)}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
