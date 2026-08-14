/** Extract a readable error string from Axios errors including FastAPI 422 arrays. */
export function extractApiError(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const axiosError = error as { response?: { data?: { detail?: unknown } } };
  const detail = axiosError?.response?.data?.detail;
  if (!detail) return fallback;
  if (Array.isArray(detail)) {
    return (detail as Array<{ msg?: string; loc?: string[] }>)
      .map(e => e.loc?.length ? `${e.loc[e.loc.length - 1]}: ${e.msg}` : (e.msg ?? String(e)))
      .join('. ');
  }
  if (typeof detail === 'string') return detail;
  return fallback;
}

/**
 * Format currency in Indian Rupee format (₹)
 * Supports Indian numbering system (lakhs, crores)
 */
export function formatCurrency(amount: number): string {
  if (amount === null || amount === undefined) return '₹0';

  const absAmount = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';

  // Format with Indian locale
  const formatted = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(absAmount);

  return sign + formatted;
}

/**
 * Format large numbers in Indian notation (K, L, Cr)
 */
export function formatCompactCurrency(amount: number): string {
  if (amount === null || amount === undefined) return '₹0';

  const absAmount = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';

  if (absAmount >= 10000000) {
    return `${sign}₹${(absAmount / 10000000).toFixed(2)}Cr`;
  } else if (absAmount >= 100000) {
    return `${sign}₹${(absAmount / 100000).toFixed(2)}L`;
  } else if (absAmount >= 1000) {
    return `${sign}₹${(absAmount / 1000).toFixed(1)}K`;
  }

  return `${sign}₹${absAmount.toLocaleString('en-IN')}`;
}

/**
 * Format date to readable format
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '-';

  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

/**
 * Format date with time
 */
export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '-';

  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '-';

  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return formatDate(dateString);
}

/**
 * Format percentage
 */
export function formatPercent(value: number, decimals = 1): string {
  if (value === null || value === undefined) return '0%';
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}

/**
 * Format number with Indian commas
 */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value);
}

/**
 * Get color class for percentage change
 */
export function getChangeColor(value: number): string {
  if (value > 0) return 'text-emerald-600';
  if (value < 0) return 'text-red-600';
  return 'text-slate-500';
}

/**
 * Get status badge variant
 */
export function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status?.toUpperCase()) {
    case 'ACTIVE':
    case 'PAID':
    case 'APPROVED':
    case 'SUCCESS':
      return 'default';
    case 'DRAFT':
    case 'PENDING':
    case 'PENDING_APPROVAL':
      return 'secondary';
    case 'OVERDUE':
    case 'CANCELLED':
    case 'FAILED':
    case 'INACTIVE':
      return 'destructive';
    default:
      return 'outline';
  }
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, length = 50): string {
  if (!text) return '';
  if (text.length <= length) return text;
  return `${text.substring(0, length)}...`;
}

/**
 * Generate initials from name
 */
export function getInitials(name: string): string {
  if (!name) return '?';
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Format file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
