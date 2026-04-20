const DEFAULT_API_BASE_URL = 'http://localhost:8000'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, '')

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }

  const text = await response.text()
  return text ? { detail: text } : {}
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const payload = await parseResponse(response)

  if (!response.ok) {
    const detail =
      (typeof payload === 'object' && payload?.detail) ||
      (typeof payload === 'string' && payload) ||
      `Error HTTP ${response.status}`

    const error = new Error(detail)
    error.status = response.status
    error.payload = payload
    throw error
  }

  return payload
}

export const api = {
  search(query) {
    return apiRequest('/api/search', {
      method: 'POST',
      body: JSON.stringify({ query }),
    })
  },

  analyzeImage({ imagenes, titulo, seller_notes = '' }) {
    return apiRequest('/api/analyze-image', {
      method: 'POST',
      body: JSON.stringify({ imagenes, titulo, seller_notes }),
    })
  },

  sendCartToTelegram(items) {
    return apiRequest('/api/cart/send-telegram', {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
  },
}

export { API_BASE_URL }
