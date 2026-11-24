const DEFAULT_API_BASE_URL = import.meta.env.DEV ? '' : 'http://localhost:8000'

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
  const { headers, ...restOptions } = options
  const url = `${API_BASE_URL}${path}`

  let response
  try {
    response = await fetch(url, {
      ...restOptions,
      headers: {
        'Content-Type': 'application/json',
        ...(headers || {}),
      },
    })
  } catch (error) {
    if (error instanceof TypeError) {
      const backendTarget = API_BASE_URL || 'http://localhost:8000'
      const friendlyError = new Error(
        `No se pudo conectar con el backend local (${backendTarget}). Inicia 'python server.py' en la carpeta raiz o reinicia 'npm run dev'.`,
      )
      friendlyError.code = 'BACKEND_UNREACHABLE'
      throw friendlyError
    }

    throw error
  }

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
  search(query, maxPrice = null, options = {}) {
    return apiRequest('/api/search', {
      method: 'POST',
      body: JSON.stringify({
        query,
        maxPrice,
        conditionIds: options.conditionIds || null,
        buyingOptions: options.buyingOptions || 'ALL',
        sortOrder: options.sortOrder || null,
        stores: options.stores || null,
      }),

    })
  },


  refreshCatalog() {
    return apiRequest('/api/catalog/refresh', { method: 'GET' })
  },

  analyzeImage({ imagenes, titulo, seller_notes = '', condicion = '' }) {

    return apiRequest('/api/analyze-image', {
      method: 'POST',
      body: JSON.stringify({ imagenes, titulo, seller_notes, condicion }),
    })
  },

  sendCartToTelegram(items) {
    return apiRequest('/api/cart/send-telegram', {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
  },

  getBotConfig() {
    return apiRequest('/api/config/bot', {
      method: 'GET',
    })
  },

  parseLocalImage(payload) {
    return apiRequest('/api/parse-local-image', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  updateBotConfig(max_precio, is_running = null) {
    const body = {}
    if (max_precio !== null) body.max_precio = max_precio
    if (is_running !== null) body.is_running = is_running
    
    return apiRequest('/api/config/bot', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // ─── Inventario ────────────────────────────────
  getInventario() {
    return apiRequest('/api/inventario', { method: 'GET' })
  },

  createInventario(item) {
    return apiRequest('/api/inventario', {
      method: 'POST',
      body: JSON.stringify(item),
    })
  },

  updateInventario(id, updates) {
    return apiRequest(`/api/inventario/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  },

  deleteInventario(id) {
    return apiRequest(`/api/inventario/${id}`, { method: 'DELETE' })
  },

  // ─── Finanzas ──────────────────────────────────
  getFinanzas() {
    return apiRequest('/api/finanzas', { method: 'GET' })
  },

  // ─── Tracking ──────────────────────────────────
  trackPackage(trackingNumber) {
    return apiRequest(`/api/tracking/${encodeURIComponent(trackingNumber)}`, { method: 'GET' })
  },

  // ─── Bot Logs ──────────────────────────────────
  getBotLogs() {
    return apiRequest('/api/bot/logs', { method: 'GET' })
  },

  // ─── Feedback ML ("Equivocado") ────────────────
  reportWrongProduct(payload) {
    return apiRequest('/api/feedback/equivocado', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  getMLWrongExamples() {
    return apiRequest('/api/ml/ejemplos', { method: 'GET' })
  },

  // ─── Autocompletado de Líneas Vía IA ───────────
  getLaptopLines(marca = '', query = '') {
    const params = new URLSearchParams()
    if (marca) params.append('marca', marca)
    if (query) params.append('query', query)
    return apiRequest(`/api/ai/laptop-lines?${params.toString()}`, { method: 'GET' })
  },

  // ─── Obtener Fotos HD de Producto ──────────────
  getItemImages(itemId) {
    return apiRequest(`/api/item-images?item_id=${encodeURIComponent(itemId)}`, { method: 'GET' })
  },

  buildCollage(payload) {
    return apiRequest('/api/build-collage', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}




export { API_BASE_URL }
