import { useEffect, useState } from 'react'
import { api } from './api'
import { useToast } from './components/Toast'
import type { Domain, HealthStatus } from './types'
import DomainForm from './components/DomainForm'
import DomainRow from './components/DomainRow'

export default function App() {
  const toast = useToast()
  const [domains, setDomains] = useState<Domain[]>([])
  const [healthMap, setHealthMap] = useState<Record<string, HealthStatus[]>>({})
  const [showForm, setShowForm] = useState(false)
  const [editDomain, setEditDomain] = useState<Domain | null>(null)

  const loadDomains = async () => {
    const data = await api.get<Domain[]>('/domains')
    setDomains(data)
    const hMap: Record<string, HealthStatus[]> = {}
    for (const d of data) {
      hMap[d.id] = await api.get<HealthStatus[]>(`/domains/${d.id}/health`)
    }
    setHealthMap(hMap)
  }

  useEffect(() => {
    loadDomains()
    const interval = setInterval(loadDomains, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this domain?')) return
    try {
      await api.del(`/domains/${id}`)
      loadDomains()
    } catch (err: any) {
      toast.showError(err.message || 'Failed to delete domain')
    }
  }

  return (
    <div className="min-h-screen p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">🌐 DNS Failover Manager</h1>
        <button
          onClick={() => { setEditDomain(null); setShowForm(true) }}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          + Add Domain
        </button>
      </div>

      {showForm && (
        <DomainForm
          domain={editDomain}
          onClose={() => { setShowForm(false); setEditDomain(null) }}
          onSaved={() => { setShowForm(false); setEditDomain(null); loadDomains() }}
        />
      )}

      <div className="flex flex-col gap-4">
        {domains.map(d => (
          <DomainRow
            key={d.id}
            domain={d}
            health={healthMap[d.id] || []}
            onEdit={() => { setEditDomain(d); setShowForm(true) }}
            onDelete={() => handleDelete(d.id)}
            onRefresh={loadDomains}
          />
        ))}
        {domains.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center text-gray-400">
            No domains configured. Click "+ Add Domain" to get started.
          </div>
        )}
      </div>
    </div>
  )
}
