// AUTOWFO API Client
// Shared fetch helpers for all backend endpoints.

function _buildApiError(res, payload, fallbackMessage) {
  const message = payload?.message || fallbackMessage || `HTTP ${res?.status || 0}`;
  const err = new Error(String(message));
  err.name = 'ApiError';
  err.status = Number(res?.status || 0);
  err.payload = payload && typeof payload === 'object' ? payload : {};
  err.endpoint = err.payload.endpoint || '';
  err.error_utc = err.payload.error_utc || '';
  err.request_id = err.payload.request_id || '';
  err.error_code = err.payload.error_code || '';
  err.cache_error_code = err.payload.cache_error_code || '';
  err.live_error = err.payload.live_error || null;
  err.cache_error = err.payload.cache_error || null;
  return err;
}

async function _readJsonSafe(res) {
  try {
    return await res.json();
  } catch (_) {
    return {};
  }
}

export function formatApiError(error) {
  if (!error || typeof error !== 'object') {
    return {
      message: String(error || 'Unknown error'),
      status: 0,
      endpoint: '',
      error_utc: '',
      request_id: '',
      error_code: '',
      cache_error_code: '',
      live_error: null,
      cache_error: null,
    };
  }
  return {
    message: String(error.message || 'Unknown error'),
    status: Number(error.status || 0),
    endpoint: String(error.endpoint || ''),
    error_utc: String(error.error_utc || ''),
    request_id: String(error.request_id || ''),
    error_code: String(error.error_code || ''),
    cache_error_code: String(error.cache_error_code || ''),
    live_error: error.live_error || null,
    cache_error: error.cache_error || null,
  };
}

export async function fetchJson(url, options = {}) {
  const res = await fetch(url, { cache: 'no-store', ...options });
  if (!res.ok) {
    const payload = await _readJsonSafe(res);
    throw _buildApiError(res, payload, `HTTP ${res.status}`);
  }
  return res.json();
}

export async function postJson(url, body = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await _readJsonSafe(res);
  if (!res.ok || payload.ok === false) {
    throw _buildApiError(res, payload, `HTTP ${res.status}`);
  }
  return payload;
}

export async function fetchText(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    throw _buildApiError(res, {}, `HTTP ${res.status}`);
  }
  return res.text();
}
