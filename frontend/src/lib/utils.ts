/**
 * Shared utility functions.
 */

import { API_URL } from './constants';

// ---------------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------------

/**
 * Copy text to clipboard with fallback for older browsers.
 * @returns true if copy succeeded, false otherwise
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for older browsers or when clipboard API is not available
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(textarea);
      return ok;
    } catch {
      return false;
    }
  }
}

// ---------------------------------------------------------------------------
// Certificate URLs (no auth required)
// ---------------------------------------------------------------------------

export function getCertificatePdfUrl(certificateId: number): string {
  return `${API_URL}/api/certificates/${certificateId}/pdf`;
}

export function getCertificatePngUrl(certificateId: number, scale?: number): string {
  const suffix = scale ? `?scale=${scale}` : '';
  return `${API_URL}/api/certificates/${certificateId}/png${suffix}`;
}

export function getVerifiedCertificatePdfUrl(code: string): string {
  return `${API_URL}/api/certificates/verify/${code}/pdf`;
}

export function getVerifiedCertificatePngUrl(code: string, scale?: number): string {
  const suffix = scale ? `?scale=${scale}` : '';
  return `${API_URL}/api/certificates/verify/${code}/png${suffix}`;
}

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

export function formatIssuedDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}
