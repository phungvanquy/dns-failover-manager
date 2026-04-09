import { useState } from 'react'
import { api } from '../api'
import { useToast } from './Toast'
import type { Domain } from '../types'

const IP_RE = /^(\d{1,3}\.){3}\d{1,3}$/
const DOMAIN_RE = /^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/
const ZONE_ID_RE = /^[a-f0-9]{32}$/

function isValidIp(ip: string): boolean {
  if (!IP_RE.test(ip)) return false
  return ip.split('.').every(p => { const n = parseInt(p); return n >= 0 && n <= 255 })
}

interface Props {
  domain: Domain | null
  onClose: () => void
  onSaved: () => void
}

export default function DomainForm({ domain, onClose, onSaved }: Props) {
  const toast = useToast()
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
  const [errors, setErrors] = useState<Record<string, string>>({})

  const isHttp = checkType === 'http' || checkType === 'https'
  const isTcp = checkType === 'tcp'

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = 'Domain name is required'
    else if (!DOMAIN_RE.test(name.trim())) errs.name = 'Invalid domain name (e.g. example.com)'
    if (!zoneId.trim()) errs.zoneId = 'Zone ID is required'
    else if (!ZONE_ID_RE.test(zoneId.trim())) errs.zoneId = 'Zone ID must be a 32-char hex string'
    if (recordId.trim() && !/^[a-f0-9]{32}$/.test(recordId.trim())) errs.recordId = 'Record ID must be a 32-char hex string'
    if (!primaryIp.trim()) errs.primaryIp = 'Primary IP is required'
    else if (!isValidIp(primaryIp.trim())) errs.primaryIp = 'Invalid IP address (e.g. 1.2.3.4)'
    if (isHttp && !checkEndpoint.trim()) errs.checkEndpoint = 'Endpoint is required for HTTP checks'
    else if (isHttp && !checkEndpoint.startsWith('/')) errs.checkEndpoint = 'Endpoint must start with /'
    if (isTcp && (checkPort < 1 || checkPort > 65535)) errs.checkPort = 'Port must be 1–65535'
    if (isHttp && (expectedStatus < 100 || expectedStatus > 599)) errs.expectedStatus = 'Status must be 100–599'
    if (checkInterval < 5) errs.checkInterval = 'Interval must be at least 5 seconds'
    if (checkInterval > 3600) errs.checkInterval = 'Interval must be at most 3600 seconds'
    if (ttl < 1) errs.ttl = 'TTL must be at least 1 second'
    if (ttl > 86400) errs.ttl = 'TTL must be at most 86400 seconds'
    const filledBackups = backupIps.filter(ip => ip.trim())
    filledBackups.forEach((ip, i) => {
      if (!isValidIp(ip.trim())) errs[`backupIp_${i}`] = `Backup IP #${i + 1}: invalid IP address`
    })
    return errs
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validate()
    setErrors(errs)
    if (Object.keys(errs).length > 0) {
      toast.showError('Please fix the validation errors')
      return
    }
    const body = {
      name: name.trim(), zone_id: zoneId.trim(), record_id: recordId.trim() || null, primary_ip: primaryIp.trim(),
      check_type: checkType,
      check_endpoint: isHttp ? checkEndpoint : '/',
      check_port: isTcp ? checkPort : (checkType === 'https' ? 443 : 80),
      check_interval: checkInterval,
      expected_status: isHttp ? expectedStatus : 200,
      ttl, auto_revert: autoRevert,
      backup_ips: backupIps.filter(ip => ip.trim()).map((ip, i) => ({ ip: ip.trim(), priority: i + 1 })),
    }
    try {
      if (domain) {
        await api.put(`/domains/${domain.id}`, body)
      } else {
        await api.post('/domains', body)
      }
      onSaved()
    } catch (err: any) {
      toast.showError(err.message || 'Failed to save domain')
    }
  }

  const input = "border rounded px-3 py-2 w-full"
  const inputErr = "border-red-400 bg-red-50"
  const errText = "text-red-500 text-xs mt-0.5"

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-lg font-semibold mb-4">{domain ? 'Edit' : 'Add'} Domain</h2>
      <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
        <div>
          <input className={`${input} ${errors.name ? inputErr : ''}`} placeholder="Domain name (e.g. example.com)" value={name} onChange={e => setName(e.target.value)} required />
          {errors.name && <p className={errText}>{errors.name}</p>}
        </div>
        <div>
          <input className={`${input} ${errors.zoneId ? inputErr : ''}`} placeholder="Zone ID (32-char hex)" value={zoneId} onChange={e => setZoneId(e.target.value)} required />
          {errors.zoneId && <p className={errText}>{errors.zoneId}</p>}
        </div>
        <div>
          <input className={`${input} ${errors.recordId ? inputErr : ''}`} placeholder="Record ID (optional, 32-char hex)" value={recordId} onChange={e => setRecordId(e.target.value)} />
          {errors.recordId && <p className={errText}>{errors.recordId}</p>}
        </div>
        <div>
          <input className={`${input} ${errors.primaryIp ? inputErr : ''}`} placeholder="Primary IP (e.g. 1.2.3.4)" value={primaryIp} onChange={e => setPrimaryIp(e.target.value)} required />
          {errors.primaryIp && <p className={errText}>{errors.primaryIp}</p>}
        </div>

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
            <input className={`${input} ${errors.checkEndpoint ? inputErr : ''}`} placeholder="/healthz" value={checkEndpoint} onChange={e => setCheckEndpoint(e.target.value)} />
            {errors.checkEndpoint && <p className={errText}>{errors.checkEndpoint}</p>}
          </div>
        )}

        {isHttp && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Expected Status Code</label>
            <input className={`${input} ${errors.expectedStatus ? inputErr : ''}`} type="number" placeholder="200" value={expectedStatus} onChange={e => setExpectedStatus(+e.target.value)} />
            {errors.expectedStatus && <p className={errText}>{errors.expectedStatus}</p>}
          </div>
        )}

        {isTcp && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">TCP Port</label>
            <input className={`${input} ${errors.checkPort ? inputErr : ''}`} type="number" placeholder="80" value={checkPort} onChange={e => setCheckPort(+e.target.value)} />
            {errors.checkPort && <p className={errText}>{errors.checkPort}</p>}
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Check Interval (seconds)</label>
          <input className={`${input} ${errors.checkInterval ? inputErr : ''}`} type="number" placeholder="30" min={5} max={3600} value={checkInterval} onChange={e => setCheckInterval(+e.target.value)} />
          {errors.checkInterval && <p className={errText}>{errors.checkInterval}</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">DNS TTL (seconds)</label>
          <input className={`${input} ${errors.ttl ? inputErr : ''}`} type="number" placeholder="60" min={1} max={86400} value={ttl} onChange={e => setTtl(+e.target.value)} />
          {errors.ttl && <p className={errText}>{errors.ttl}</p>}
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
            <div key={i} className="mt-1">
              <div className="flex gap-2">
                <input className={`${input} ${errors[`backupIp_${i}`] ? inputErr : ''}`} placeholder={`Backup IP #${i + 1} (e.g. 1.2.3.4)`} value={ip}
                  onChange={e => { const n = [...backupIps]; n[i] = e.target.value; setBackupIps(n) }} />
                <button type="button" onClick={() => setBackupIps(backupIps.filter((_, j) => j !== i))}
                  className="text-red-500 hover:text-red-700 px-2">✕</button>
              </div>
              {errors[`backupIp_${i}`] && <p className={errText}>{errors[`backupIp_${i}`]}</p>}
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
