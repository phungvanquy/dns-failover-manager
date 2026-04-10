export interface BackupIP {
  id: string;
  ip: string;
  priority: number;
  description?: string | null;
}

export interface Domain {
  id: string;
  name: string;
  zone_id: string;
  record_id: string | null;
  primary_ip: string;
  primary_ip_description?: string | null;
  active_ip: string;
  auto_revert: boolean;
  check_type: string;
  check_endpoint: string;
  check_port: number;
  check_interval: number;
  expected_status: number;
  ttl: number;
  monitoring_enabled: boolean;
  created_at: string;
  updated_at: string;
  backup_ips: BackupIP[];
}

export interface HealthStatus {
  id: string;
  domain_id: string;
  ip: string;
  is_healthy: boolean;
  consecutive_failures: number;
  consecutive_successes: number;
  last_checked: string | null;
  last_status_change: string | null;
}

export interface FailoverEvent {
  id: string;
  domain_id: string;
  old_ip: string | null;
  new_ip: string;
  reason: string;
  created_at: string;
}
