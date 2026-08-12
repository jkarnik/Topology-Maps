import { HealthBucket } from '../types/meraki';

export const HEALTH_COLORS: Record<HealthBucket, string> = {
  green: '#2ecc71',
  yellow: '#f1c40f',
  orange: '#e67e22',
  red: '#e74c3c',
  unknown: '#5a6472',
};

export const HEALTH_LABELS: Record<HealthBucket, string> = {
  green: 'Healthy',
  yellow: 'Minor issues',
  orange: 'Degraded',
  red: 'Critical',
  unknown: 'No data',
};
