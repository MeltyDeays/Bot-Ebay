import { startTransition, useDeferredValue, useEffect, useEffectEvent, useState } from 'react'
import {
  Check,
  Cpu,
  DollarSign,
  Eye,
  Filter,
  HardDrive,
  Loader2,
  Monitor,
  Plus,
  Search,
  Send,
  ShoppingCart,
  Smartphone,
  X,
} from 'lucide-react'
import { api } from './api'
import { supabase } from './supabase'

const EMPTY_SCAN_STATE = Object.freeze({ status: 'idle', data: null, error: null })

function getScanButtonLabel(status) {
  if (status === 'loading') return 'Analizando...'
  if (status === 'error') return 'Reintentar'
  if (status === 'success') return 'Reescanear'
  return 'Escanear IA'
}

function getVisualTone(scanState) {
  const visualData = scanState.data
  const isHealthy = visualData?.status === 'success' && (visualData?.score ?? 0) > 70

  return {
    background: isHealthy ? 'rgba(46, 213, 115, 0.1)' : 'rgba(255, 71, 87, 0.1)',
    border: isHealthy ? 'var(--success)' : 'var(--danger)',
    color: isHealthy ? 'var(--success)' : 'var(--danger)',
  }
}

function App() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [isRealTimeSearch, setIsRealTimeSearch] = useState(false)

  const [cart, setCart] = useState([])
  const [isCartOpen, setIsCartOpen] = useState(false)
  const [isSendingCart, setIsSendingCart] = useState(false)

  const [visualScanState, setVisualScanState] = useState({})

  const [isPriceModalOpen, setIsPriceModalOpen] = useState(false)
  const [localPriceForm, setLocalPriceForm] = useState({
    titulo: '',
    tipo: 'laptop',
    precio_usd: '',
    condicion: 'Usado',
  })
  const [isSubmittingPrice, setIsSubmittingPrice] = useState(false)

  const deferredSearchQuery = useDeferredValue(searchQuery)
  const cartIds = new Set(cart.map((item) => item.id))

  const fetchProducts = useEffectEvent(async () => {
    setLoading(true)

    try {
      let query = supabase.from('productos').select('*').order('encontrado_en', { ascending: false }).limit(50)

      if (categoryFilter !== 'all') {
        query = query.eq('categoria', categoryFilter)
      }

      const { data, error } = await query

      if (error) {
        throw error
      }

      startTransition(() => {
        setProducts(data || [])
      })
    } catch (error) {
      console.error('Error fetching products:', error)
      alert(`Error cargando productos locales: ${error.message || 'desconocido'}`)
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    if (isRealTimeSearch) {
      return
    }

    void fetchProducts()
  }, [categoryFilter, isRealTimeSearch])

  const toggleCartItem = (product) => {
    setCart((currentCart) => {
      const exists = currentCart.some((item) => item.id === product.id)
      if (exists) {
        return currentCart.filter((item) => item.id !== product.id)
      }

      return [...currentCart, product]
    })
  }

  const sendCartToTelegram = async () => {
    if (cart.length === 0) return

    setIsSendingCart(true)
    try {
      await api.sendCartToTelegram(cart)
      alert('Recomendaciones enviadas a Telegram exitosamente.')
      setCart([])
      setIsCartOpen(false)
    } catch (error) {
      console.error(error)
      alert(`Error al enviar a Telegram: ${error.message || 'desconocido'}`)
    } finally {
      setIsSendingCart(false)
    }
  }

  const scanImage = async (product) => {
    const imageCandidates =
      product.todas_las_imagenes?.filter(Boolean) || (product.imagen_url ? [product.imagen_url] : [])

    if (imageCandidates.length === 0) {
      setVisualScanState((currentState) => ({
        ...currentState,
        [product.id]: {
          status: 'error',
          data: null,
          error: 'Este producto no tiene imagenes validas para analizar.',
        },
      }))
      return
    }

    setVisualScanState((currentState) => ({
      ...currentState,
      [product.id]: {
        status: 'loading',
        data: currentState[product.id]?.data || null,
        error: null,
      },
    }))

    try {
      const data = await api.analyzeImage({
        imagenes: imageCandidates,
        titulo: product.titulo,
        seller_notes: product.seller_notes || '',
      })

      const nextStatus = data.status === 'success' ? 'success' : 'error'
      setVisualScanState((currentState) => ({
        ...currentState,
        [product.id]: {
          status: nextStatus,
          data,
          error: nextStatus === 'error' ? data.nota || 'No se pudo completar el analisis visual.' : null,
        },
      }))
    } catch (error) {
      console.error(error)
      setVisualScanState((currentState) => ({
        ...currentState,
        [product.id]: {
          status: 'error',
          data: null,
          error: error.message || 'No se pudo analizar la imagen. Intenta de nuevo.',
        },
      }))
    }
  }

  async function handleRealTimeSearch(event) {
    event.preventDefault()
    if (!searchQuery.trim()) return

    setLoading(true)
    setIsRealTimeSearch(true)
    startTransition(() => {
      setProducts([])
      setCategoryFilter('all')
    })

    try {
      const data = await api.search(searchQuery.trim())
      startTransition(() => {
        setProducts(data.results || [])
      })
    } catch (error) {
      console.error(error)
      alert(`Error al buscar ofertas: ${error.message || 'desconocido'}`)
    } finally {
      setLoading(false)
    }
  }

  const submitLocalPrice = async (event) => {
    event.preventDefault()
    if (!localPriceForm.titulo || !localPriceForm.precio_usd) return

    setIsSubmittingPrice(true)
    try {
      const { error } = await supabase.from('precios_nicaragua').insert([
        {
          tipo: localPriceForm.tipo,
          titulo_marketplace: localPriceForm.titulo,
          precio_nic_usd: parseFloat(localPriceForm.precio_usd),
          condicion: localPriceForm.condicion,
          fuente: 'Ingreso Manual Web',
        },
      ])

      if (error) {
        throw error
      }

      alert('Precio local registrado exitosamente en la base de datos.')
      setIsPriceModalOpen(false)
      setLocalPriceForm({ titulo: '', tipo: 'laptop', precio_usd: '', condicion: 'Usado' })
    } catch (error) {
      console.error(error)
      alert(`Error guardando el precio: ${error.message}`)
    } finally {
      setIsSubmittingPrice(false)
    }
  }

  const normalizedQuery = deferredSearchQuery.trim().toLowerCase()
  const filteredProducts = isRealTimeSearch
    ? products
    : products.filter((product) => {
        if (!normalizedQuery) return true
        return (
          product.titulo.toLowerCase().includes(normalizedQuery) ||
          (product.marca && product.marca.toLowerCase().includes(normalizedQuery))
        )
      })

  const categories = [
    { id: 'all', name: 'Todos', icon: <Search size={18} /> },
    { id: 'laptop', name: 'Laptops', icon: <Monitor size={18} /> },
    { id: 'phone', name: 'Telefonos', icon: <Smartphone size={18} /> },
    { id: 'ssd', name: 'Almacenamiento', icon: <HardDrive size={18} /> },
    { id: 'ram', name: 'Memoria RAM', icon: <Cpu size={18} /> },
  ]

  return (
    <div className="app-container">
      <header>
        <div className="logo">
          <span className="gradient-text">eBay AI Finder</span>
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flex: 1, justifyContent: 'flex-end' }}>
          <form onSubmit={handleRealTimeSearch} className="search-bar">
            <Search size={20} color="var(--text-muted)" />
            <input
              id="searchInput"
              name="search"
              type="text"
              placeholder="Buscar en tiempo real (Ej: Laptops HP Ryzen 5 baratas)..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <button
              type="submit"
              style={{
                background: 'var(--accent-primary)',
                color: '#fff',
                padding: '0.4rem 1rem',
                borderRadius: '100px',
                fontWeight: '600',
              }}
            >
              Buscar
            </button>
          </form>

          <button
            onClick={() => setIsPriceModalOpen(true)}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-main)',
              padding: '0.75rem',
              borderRadius: '100px',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontWeight: '500',
            }}
          >
            <DollarSign size={20} color="var(--success)" />
            Registrar Precio Local
          </button>

          <button
            onClick={() => setIsCartOpen(true)}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-main)',
              padding: '0.75rem',
              borderRadius: '100px',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              position: 'relative',
            }}
          >
            <ShoppingCart size={20} />
            {cart.length > 0 && (
              <span
                style={{
                  position: 'absolute',
                  top: '-5px',
                  right: '-5px',
                  background: 'var(--accent-primary)',
                  color: 'white',
                  fontSize: '0.7rem',
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 'bold',
                }}
              >
                {cart.length}
              </span>
            )}
          </button>
        </div>
      </header>

      <div className="main-layout animate-fade-in">
        <aside className="filters-panel glass-panel">
          <div className="filter-group">
            <h3 className="filter-title flex items-center gap-2">
              <Filter size={16} /> Categorias
            </h3>
            <div className="flex-col gap-2 mt-4">
              {categories.map((category) => (
                <button
                  key={category.id}
                  onClick={() => setCategoryFilter(category.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: categoryFilter === category.id ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                    color: categoryFilter === category.id ? 'var(--accent-primary)' : 'var(--text-main)',
                    border: `1px solid ${categoryFilter === category.id ? 'var(--accent-primary)' : 'transparent'}`,
                    fontWeight: categoryFilter === category.id ? '600' : '400',
                    width: '100%',
                    textAlign: 'left',
                  }}
                >
                  {category.icon} {category.name}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <main>
          {loading ? (
            <div className="flex justify-center p-6">
              <div style={{ color: 'var(--text-muted)' }}>Cargando ofertas con IA...</div>
            </div>
          ) : (
            <>
              <div style={{ marginBottom: '1.5rem', color: 'var(--text-muted)' }}>
                Mostrando {filteredProducts.length} resultados
              </div>

              <div className="product-grid">
                {filteredProducts.map((product) => {
                  const scanState = visualScanState[product.id] || EMPTY_SCAN_STATE
                  const visualData = scanState.data
                  const visualTone = getVisualTone(scanState)
                  const showVisualPanel = Boolean(visualData || scanState.error)
                  const isAddedToCart = cartIds.has(product.id)

                  return (
                    <div key={product.id} className="product-card glass-panel">
                      {product.imagen_url ? (
                        <img src={product.imagen_url} alt={product.titulo} className="product-image" />
                      ) : (
                        <div className="product-image flex justify-center items-center" style={{ background: '#f3f4f6' }}>
                          <Monitor size={48} color="#9ca3af" />
                        </div>
                      )}

                      <div className="product-content">
                        <h3 className="product-title">{product.titulo}</h3>
                        <div className="product-price">${product.precio?.toFixed(2)}</div>

                        <div className="product-meta" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                          {product.marca && <span className="badge accent">{product.marca.toUpperCase()}</span>}
                          <span className="badge">{product.condicion}</span>
                          {product.es_subasta && <span className="badge warning">SUBASTA</span>}

                          <button
                            onClick={() => scanImage(product)}
                            disabled={scanState.status === 'loading'}
                            title="Escanear con IA Visual"
                            style={{
                              background: 'transparent',
                              color: scanState.status === 'error' ? 'var(--danger)' : 'var(--text-muted)',
                              cursor: scanState.status === 'loading' ? 'wait' : 'pointer',
                              padding: '0.2rem',
                              marginLeft: 'auto',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                              fontSize: '0.8rem',
                            }}
                          >
                            {scanState.status === 'loading' ? <Loader2 size={16} className="spinner" /> : <Eye size={16} />}
                            {getScanButtonLabel(scanState.status)}
                          </button>
                        </div>

                        {showVisualPanel && (
                          <div
                            style={{
                              marginTop: '0.5rem',
                              padding: '0.5rem',
                              borderRadius: '4px',
                              background: visualTone.background,
                              border: `1px solid ${visualTone.border}`,
                              fontSize: '0.85rem',
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                fontWeight: 'bold',
                                color: visualTone.color,
                              }}
                            >
                              <Eye size={14} />
                              Visual:{' '}
                              {visualData
                                ? `${String(visualData.calidad_visual || 'error').toUpperCase()} (${visualData.score ?? 50}/100)`
                                : 'ERROR'}
                            </div>
                            <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-main)', fontSize: '0.8rem' }}>
                              {visualData?.nota || scanState.error}
                            </p>
                            {visualData?.provider_status && (
                              <p style={{ marginTop: '0.25rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                                Estado proveedor: {visualData.provider_status}
                              </p>
                            )}
                          </div>
                        )}

                        {product.rentabilidad ? (
                          <div className="profit-block">
                            <div className="profit-row">
                              <span style={{ color: 'var(--text-muted)' }}>Venta NIC:</span>
                              <span className="profit-val">${product.rentabilidad.precio_estimado_nic?.toFixed(2) || '?'}</span>
                            </div>
                            <div className="profit-row">
                              <span style={{ color: 'var(--text-muted)' }}>Margen:</span>
                              <span
                                className="profit-val"
                                style={{
                                  color: product.rentabilidad.porcentaje_ganancia > 40 ? 'var(--success)' : 'var(--warning)',
                                }}
                              >
                                ${product.rentabilidad.margen_estimado?.toFixed(2) || '?'} ({product.rentabilidad.porcentaje_ganancia || '?'}%)
                              </span>
                            </div>
                          </div>
                        ) : (
                          product.precio_estimado_nic &&
                          !product.es_subasta && (
                            <div className="profit-block">
                              <div className="profit-row">
                                <span style={{ color: 'var(--text-muted)' }}>Venta NIC:</span>
                                <span className="profit-val">${product.precio_estimado_nic.toFixed(2)}</span>
                              </div>
                              <div className="profit-row">
                                <span style={{ color: 'var(--text-muted)' }}>Margen:</span>
                                <span
                                  className="profit-val"
                                  style={{ color: product.porcentaje_ganancia > 40 ? 'var(--success)' : 'var(--warning)' }}
                                >
                                  ${product.margen_estimado?.toFixed(2)} ({product.porcentaje_ganancia}%)
                                </span>
                              </div>
                            </div>
                          )
                        )}

                        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                          <a
                            href={product.enlace}
                            target="_blank"
                            rel="noreferrer"
                            className="buy-btn"
                            style={{ flex: 1, padding: '0.5rem', fontSize: '0.9rem' }}
                          >
                            Ver eBay
                          </a>
                          <button
                            onClick={() => toggleCartItem(product)}
                            style={{
                              background: isAddedToCart ? 'var(--success)' : 'var(--bg-card)',
                              border: `1px solid ${isAddedToCart ? 'var(--success)' : 'var(--border-color)'}`,
                              color: 'white',
                              padding: '0.5rem',
                              borderRadius: '8px',
                              flex: 1,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '0.5rem',
                              fontSize: '0.9rem',
                            }}
                          >
                            {isAddedToCart ? (
                              <>
                                <Check size={16} /> Agregado
                              </>
                            ) : (
                              <>
                                <Plus size={16} /> Recomendar
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}

                {filteredProducts.length === 0 && (
                  <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                    No se encontraron productos. Intenta hacer una busqueda en tiempo real arriba.
                  </div>
                )}
              </div>
            </>
          )}
        </main>
      </div>

      {isCartOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: '400px',
            maxWidth: '100%',
            background: 'var(--bg-dark)',
            borderLeft: '1px solid var(--border-color)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
            animation: 'fadeIn 0.2s ease-out',
          }}
        >
          <div
            style={{
              padding: '1.5rem',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <h2 className="flex items-center gap-2">
              <ShoppingCart size={24} /> Recomendaciones
            </h2>
            <button onClick={() => setIsCartOpen(false)} style={{ background: 'transparent', color: 'var(--text-muted)' }}>
              <X size={24} />
            </button>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            {cart.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '2rem' }}>
                No hay productos seleccionados.
              </div>
            ) : (
              cart.map((item) => (
                <div key={item.id} className="glass-panel" style={{ padding: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  {item.imagen_url && (
                    <img
                      src={item.imagen_url}
                      alt=""
                      style={{ width: '60px', height: '60px', objectFit: 'contain', background: '#fff', borderRadius: '4px' }}
                    />
                  )}
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: '0.9rem',
                        fontWeight: '500',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {item.titulo}
                    </div>
                    <div style={{ fontWeight: 'bold', color: 'var(--accent-primary)', marginTop: '0.25rem' }}>
                      ${item.precio?.toFixed(2)}
                    </div>
                  </div>
                  <button onClick={() => toggleCartItem(item)} style={{ background: 'transparent', color: 'var(--danger)' }}>
                    <X size={20} />
                  </button>
                </div>
              ))
            )}
          </div>

          <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', background: 'var(--bg-card)' }}>
            <button
              onClick={sendCartToTelegram}
              disabled={cart.length === 0 || isSendingCart}
              style={{
                width: '100%',
                padding: '1rem',
                borderRadius: '8px',
                background: cart.length === 0 ? 'var(--border-color)' : 'var(--accent-primary)',
                color: 'white',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '0.5rem',
                fontWeight: 'bold',
                fontSize: '1.1rem',
                cursor: cart.length === 0 ? 'not-allowed' : 'pointer',
                opacity: isSendingCart ? 0.7 : 1,
              }}
            >
              <Send size={20} /> {isSendingCart ? 'Enviando...' : `Enviar ${cart.length} a Telegram`}
            </button>
          </div>
        </div>
      )}

      {isCartOpen && (
        <div
          onClick={() => setIsCartOpen(false)}
          style={{ position: 'fixed', top: 0, left: 0, right: '400px', bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 999 }}
        />
      )}

      {isPriceModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 2000,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          <div className="glass-panel animate-fade-in" style={{ width: '90%', maxWidth: '500px', padding: '2rem', position: 'relative' }}>
            <button onClick={() => setIsPriceModalOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}>
              <X />
            </button>

            <h2 className="flex items-center gap-2" style={{ marginBottom: '1.5rem', color: 'var(--success)' }}>
              <DollarSign size={24} /> Registrar Precio en Nicaragua
            </h2>

            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Ensena a la IA a cuanto se vende un producto en el mercado local. La IA usara esto como referencia para calcular margenes en tus futuras busquedas.
            </p>

            <form onSubmit={submitLocalPrice} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label htmlFor="titulo_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Producto (Marca, Modelo, Specs)
                </label>
                <input
                  id="titulo_producto"
                  name="titulo_producto"
                  required
                  type="text"
                  placeholder="Ej: Lenovo Thinkpad E14 Gen 2 16GB RAM 512GB"
                  value={localPriceForm.titulo}
                  onChange={(event) => setLocalPriceForm((currentForm) => ({ ...currentForm, titulo: event.target.value }))}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem' }}>
                <div style={{ flex: 1 }}>
                  <label htmlFor="categoria_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                    Categoria
                  </label>
                  <select
                    id="categoria_producto"
                    name="categoria_producto"
                    value={localPriceForm.tipo}
                    onChange={(event) => setLocalPriceForm((currentForm) => ({ ...currentForm, tipo: event.target.value }))}
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      borderRadius: '8px',
                      background: 'var(--bg-dark)',
                      border: '1px solid var(--border-color)',
                      color: 'white',
                    }}
                  >
                    <option value="laptop">Laptop</option>
                    <option value="phone">Telefono</option>
                    <option value="ssd">Almacenamiento (SSD)</option>
                    <option value="ram">Memoria RAM</option>
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label htmlFor="precio_usd" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                    Precio Venta (USD)
                  </label>
                  <input
                    id="precio_usd"
                    name="precio_usd"
                    required
                    type="number"
                    min="1"
                    step="0.01"
                    placeholder="Ej: 420"
                    value={localPriceForm.precio_usd}
                    onChange={(event) => setLocalPriceForm((currentForm) => ({ ...currentForm, precio_usd: event.target.value }))}
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      borderRadius: '8px',
                      background: 'var(--bg-dark)',
                      border: '1px solid var(--border-color)',
                      color: 'white',
                    }}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="condicion_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Condicion Normalizada
                </label>
                <select
                  id="condicion_producto"
                  name="condicion_producto"
                  value={localPriceForm.condicion}
                  onChange={(event) => setLocalPriceForm((currentForm) => ({ ...currentForm, condicion: event.target.value }))}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                  }}
                >
                  <option value="Usado">Usado</option>
                  <option value="Nuevo">Nuevo</option>
                  <option value="Refurbished">Refurbished</option>
                </select>
              </div>

              <button disabled={isSubmittingPrice} type="submit" className="buy-btn" style={{ marginTop: '1rem', background: 'var(--success)', opacity: isSubmittingPrice ? 0.7 : 1 }}>
                {isSubmittingPrice ? 'Guardando...' : 'Guardar en Base de Datos'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
