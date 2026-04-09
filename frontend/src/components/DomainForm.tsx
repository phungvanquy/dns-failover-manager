import { useState } from 'react'
import { api } from '../api'
import type { Domain } from '../types'

interface Props {
  domain: Domain | null
  onClose: () => void
  onSaved: () => void
}

export default function DomainForm({ domain, onClose, onSaved }: Props) {
  const [name, setName] = useState(domain?.name ?? '')
  const [zoneId, setZoneId] = useState(domain?.zone_id ?? '')
  const [recordId, setRecordId] = useState(domain?.record_id ?? '')
  const [primaryIp, setPrimaryIp] = useState(domain?.primary_ip ?? '')
  const [checkType, setCheckType] = useState(domain?.check_type ?? 'http')
  const [checkEndpoint, setCheckEndpoint] = useState(domain?.check_endpoint ?? '/')
  const [checkPort, setCheckPort] = useState(domain?.check_port ?? 80)
  const [checkInterval, setCheckInterval] = useState(domain?.check_interval ?? 30)
  const [expectedStatus, setExpectedStatus] = useState(domain?.expected_status ?? 200)
  const [ttl, setTtl] = useState(domain?.ttl ?? 60)
  const [autoRevert, setAutoRevert] = useState(domain?.auto_revert ?? true)
  const [backupIps, setBackupIps] = useState(
    domain?.backup_ips.map(b => b.ip) ?? ['']
  )

  const isHttp = checkType === 'http' || checkType === 'https'
  const isTcp = checkType === 'tcp'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = {
      name, zone_id: zoneId, record_id: recordId || null, primary_ip: primaryIp,
      check_type: checkType,
      check_endpoint: isHttp ? checkEndpoint : '/',
      check_port: isTcp ? checkPort : (checkType === 'https' ? 443 : 80),
      check_interval: checkInterval,
      expected_status: isHttp ? expectedStatus : 200,
      ttl, auto_revert: autoRevert,
      backup_ips: backupIps.filter(ip => ip.trim()).map((ip, i) => ({ ip: ip.trim(), priority: i + 1 })),
    }
    if (domain) {
      await api.put(`/domains/${domain.id}`, body)
    } else {
      await api.post('/domains', body)
    }
    onSaved()
  }

  const input = "border rounded px-3 py-2 w-full"

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-lg font-semibold mb-4">{domain ? 'Edit' : 'Add'} Domain</h2>
      <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
        <input className={input} placeholder="Domain name" value={name} onChange={e => setName(e.target.value)} required />
        <input className={input} placeholder="Zone ID" value={zoneId} onChange={e => setZoneId(e.target.value)} required />
        <input className={input} placeholder="Record ID (optional)" value={recordId} onChange={e => setRecordId(e.target.value)} />
        <input className={input} placeholder="Primary IP" value={primaryIp} onChange={e => setPrimaryIp(e.target.value)} required />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Check Type</label>
          <select className={input} value={checkType} onChange={e => setCheckType(e.target.value)}>
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
            <option value="tcp">TCP</option>
            <option value="ping">Ping</option>
          </select>
        </div>

        {isHttp && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Check Endpoint</label>
            <input className={input} placeholder="/healthz" value={checkEndpoint} onChange={e => setCheckEndpoint(e.target.value)} />
          </div>
        )}

        {isHttp && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Expected Status Code</label>
            <input className={input} type="number" placeholder="200" value={expectedStatus} onChange={e => setExpectedStatus(+e.target.value)} />
          </div>
        )}

        {isTcp && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">TCP Port</label>
            <input className={input} type="number" placeholder="80" value={checkPort} onChange={e => setCheckPort(+e.target.value)} />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Check Interval (seconds)</label>
          <input className={input} type="number" placeholder="30" value={checkInterval} onChange={e => setCheckInterval(+e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">DNS TTL (seconds)</label>
          <input className={input} type="number" placeholder="60" value={ttl} onChange={e => setTtl(+e.target.value)} />
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={autoRevert} onChange={e => setAutoRevert(e.target.checked)} />
          Auto-revert to primary
        </label>

        {checkType === 'ping' && (
          <div className="col-span-2 bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
            ℹ️ Ping check sends ICMP echo requests — no endpoint, port, or status code needed.
          </div>
        )}

        {isTcp && (
          <div className="col-span-2 bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800">
            ℹ️ TCP check attempts a socket connection to the specified port — no endpoint or status code needed.
          </div>
        )}

        <div className="col-span-2">
          <label className="font-medium text-sm">Backup IPs (in priority order)</label>
          {backupIps.map((ip, i) => (
            <div key={i} className="flex gap-2 mt-1">
              <input className={input} placeholder={`Backup IP #${i + 1}`} value={ip}
                onChange={e => { const n = [...backupIps]; n[i] = e.target.value; setBackupIps(n) }} />
              <button type="button" onClick={() => setBackupIps(backupIps.filter((_, j) => j !== i))}
                className="text-red-500 hover:text-red-700 px-2">✕</button>
            </div>
          ))}
          <button type="button" onClick={() => setBackupIps([...backupIps, ''])}
            className="text-blue-600 text-sm mt-1">+ Add backup IP</button>
        </div>

        <div className="col-span-2 flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-2 border rounded">Cancel</button>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            {domain ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  )
}
