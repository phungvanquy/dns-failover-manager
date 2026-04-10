import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { useToast } from './Toast'
import type { Domain, HealthStatus } from '../types'

interface Props {
  domain: Domain
  health: HealthStatus[]
  onEdit: () => void
  onDelete: () => void
  onRefresh: () => void
}

export default function DomainRow({ domain, health, onEdit, onDelete, onRefresh }: Props) {
  const toast = useToast()
  const [switching, setSwitching] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [toggling, setToggling] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const activeHealth = health.find(h => h.ip === domain.active_ip)
  const isHealthy = activeHealth?.is_healthy ?? true
  const allIps = [domain.primary_ip, ...domain.backup_ips.map(b => b.ip)]

  const getIpDescription = (ip: string): string | undefined => {
    if (ip === domain.primary_ip) return domain.primary_ip_description || undefined
    return domain.backup_ips.find(b => b.ip === ip)?.description || undefined
  }

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showMenu])

  const handleSwitch = async (ip: string) => {
    setSwitching(true)
    try {
      await api.post(`/domains/${domain.id}/switch`, { target_ip: ip })
      toast.showSuccess(`Switched to ${ip}`)
      onRefresh()
    } catch (err: any) {
      toast.showError(err.message || 'Failed to switch IP')
    } finally {
      setSwitching(false)
      setShowMenu(false)
    }
  }

  const handleToggleMonitoring = async () => {
    setToggling(true)
    try {
      await api.post(`/domains/${domain.id}/monitoring`)
      toast.showSuccess(domain.monitoring_enabled ? 'Monitoring paused' : 'Monitoring resumed')
      onRefresh()
    } catch (err: any) {
      toast.showError(err.message || 'Failed to toggle monitoring')
    } finally {
      setToggling(false)
    }
  }

  return (
    <div className={`bg-white rounded-lg shadow p-4 sm:p-5 flex flex-col gap-3 ${!domain.monitoring_enabled ? 'opacity-60' : ''}`}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className={`w-3 h-3 rounded-full flex-shrink-0 ${isHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
          <h3 className="font-semibold text-lg truncate">{domain.name}</h3>
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
            {domain.check_type.toUpperCase()}
          </span>
          {!domain.monitoring_enabled && (
            <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded">PAUSED</span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
          <button
            onClick={handleToggleMonitoring}
            disabled={toggling}
            className={`text-sm px-3 py-1 border rounded ${domain.monitoring_enabled
              ? 'border-yellow-300 text-yellow-700 hover:bg-yellow-50'
              : 'border-green-300 text-green-700 hover:bg-green-50'}`}
          >
            {domain.monitoring_enabled ? '⏸ Pause' : '▶ Resume'}
          </button>
          <button onClick={onEdit} className="text-sm px-3 py-1 border rounded hover:bg-gray-50">Edit</button>
          <button onClick={onDelete} className="text-sm px-3 py-1 border border-red-200 text-red-600 rounded hover:bg-red-50">Delete</button>
        </div>
      </div>

      {/* IP Info */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div>
          <span className="text-gray-500 block text-xs">Active IP</span>
          <span className="font-mono font-medium cursor-default break-all" title={getIpDescription(domain.active_ip)}>{domain.active_ip}</span>
          {getIpDescription(domain.active_ip) && <span className="block text-xs text-gray-400 truncate">{getIpDescription(domain.active_ip)}</span>}
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Primary IP</span>
          <span className="font-mono cursor-default break-all" title={domain.primary_ip_description || undefined}>{domain.primary_ip}</span>
          {domain.primary_ip_description && <span className="block text-xs text-gray-400 truncate">{domain.primary_ip_description}</span>}
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Backup IPs</span>
          {domain.backup_ips.length > 0
            ? domain.backup_ips.map(b => (
                <div key={b.id}>
                  <span className="font-mono block cursor-default break-all" title={b.description || undefined}>{b.ip}</span>
                  {b.description && <span className="block text-xs text-gray-400 truncate">{b.description}</span>}
                </div>
              ))
            : <span className="text-gray-400">None</span>
          }
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Status</span>
          <span className={`font-medium ${isHealthy ? 'text-green-600' : 'text-red-600'}`}>
            {isHealthy ? '● UP' : '● DOWN'}
          </span>
        </div>
      </div>

      {/* Switch Button */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="text-sm px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 w-full md:w-auto"
        >
          ⚡ Force Switch IP
        </button>
        {showMenu && (
          <div className="absolute left-0 bottom-full sm:bottom-full mb-2 sm:mb-2 bg-white border rounded-lg shadow-xl p-2 z-50 min-w-[220px] max-w-[calc(100vw-2rem)]
            max-h-[60vh] overflow-y-auto">
            <div className="text-xs text-gray-500 px-2 py-1 mb-1 font-medium">Select target IP:</div>
            {allIps.map(ip => {
              const h = health.find(s => s.ip === ip)
              const ipHealthy = h?.is_healthy ?? true
              const isCurrent = ip === domain.active_ip
              const isPrimary = ip === domain.primary_ip
              return (
                <button
                  key={ip}
                  disabled={switching || isCurrent}
                  onClick={() => handleSwitch(ip)}
                  className={`flex flex-col w-full text-left px-3 py-2 text-sm rounded
                    ${isCurrent ? 'bg-purple-50 text-purple-700 cursor-default' : 'hover:bg-gray-100'}
                    disabled:opacity-60`}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="font-mono flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${ipHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                      {ip}
                    </span>
                    <span className="text-xs text-gray-400">
                      {isCurrent && '✓ active'}
                      {!isCurrent && isPrimary && 'primary'}
                      {!isCurrent && !isPrimary && `backup #${domain.backup_ips.findIndex(b => b.ip === ip) + 1}`}
                    </span>
                  </div>
                  {getIpDescription(ip) && <span className="text-xs text-gray-400 ml-4 truncate w-full">{getIpDescription(ip)}</span>}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
