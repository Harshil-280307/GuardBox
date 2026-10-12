/**
 * Veronic GuardBox - Robust API Client with Timeout and Error Handling
 * Guarantees that no request hangs indefinitely, parses JSON automatically,
 * and normalizes error objects with status codes.
 */

export async function apiFetch(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  const defaultHeaders = {
    'Accept': 'application/json',
    ...(options.body && typeof options.body === 'string' && (options.body.startsWith('{') || options.body.startsWith('['))
      ? { 'Content-Type': 'application/json' }
      : {})
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers
      },
      signal: controller.signal
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}: ${res.statusText || 'Request failed'}`;
      try {
        const errorData = await res.json();
        if (errorData && (errorData.detail || errorData.message || errorData.error)) {
          errorDetail = errorData.detail || errorData.message || errorData.error;
        }
      } catch {
        // Not JSON error body
      }
      const err = new Error(errorDetail);
      err.status = res.status;
      throw err;
    }

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return await res.json();
    }
    return await res.text();
  } catch (err) {
    if (err.name === 'AbortError') {
      const timeoutErr = new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s (${url})`);
      timeoutErr.status = 408;
      throw timeoutErr;
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

