import { useEffect, useState } from 'react'
import { Search, Monitor, Smartphone, HardDrive, Cpu, Filter, ShoppingCart, Send, X, Plus, Check, Eye, Loader2, DollarSign } from 'lucide-react'
import { supabase } from './supabase'

function App() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [isRealTimeSearch, setIsRealTimeSearch] = useState(false)
  
  // Cart state
  const [cart, setCart] = useState([])
  const [isCartOpen, setIsCartOpen] = useState(false)
  const [isSendingCart, setIsSendingCart] = useState(false)

  // AI Visual Analysis State
  const [analyzingImageId, setAnalyzingImageId] = useState(null)
  const [visualAnalysis, setVisualAnalysis] = useState({})

  // Local Price Modal State
  const [isPriceModalOpen, setIsPriceModalOpen] = useState(false)
  const [localPriceForm, setLocalPriceForm] = useState({
    titulo: '', tipo: 'laptop', precio_usd: '', condicion: 'Usado'
  })
  const [isSubmittingPrice, setIsSubmittingPrice] = useState(false)

  // Fetch initial local DB catalog (Supabase)
  useEffect(() => {
    if (!isRealTimeSearch) fetchProducts()
  }, [categoryFilter, isRealTimeSearch])

  async function fetchProducts() {
    setLoading(true)
    let query = supabase
      .from('productos')
      .select('*')
      .order('encontrado_en', { ascending: false })
      .limit(50)

    if (categoryFilter !== 'all') {
      query = query.eq('categoria', categoryFilter)
    }

    const { data, error } = await query
    
    if (error) {
      console.error('Error fetching products:', error)
    } else {
      setProducts(data || [])
    }
    setLoading(false)
  }

  // Cart Functions
  const toggleCartItem = (product) => {
    const exists = cart.find(item => item.id === product.id);
    if (exists) {
      setCart(cart.filter(item => item.id !== product.id));
    } else {
      setCart([...cart, product]);
    }
  }

  const sendCartToTelegram = async () => {
    if (cart.length === 0) return;
    setIsSendingCart(true);
    try {
      const res = await fetch('http://localhost:8000/api/cart/send-telegram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: cart })
      });
      if (!res.ok) throw new Error("Error enviando a Telegram");
      alert("¡Recomendaciones enviadas a Telegram exitosamente!");
      setCart([]);
      setIsCartOpen(false);
    } catch (err) {
      console.error(err);
      alert("Error al enviar. Asegúrate de que el backend (server.py) esté corriendo.");
    }
    setIsSendingCart(false);
  }

  const scanImage = async (product) => {
    if (!product.imagen_url && (!product.todas_las_imagenes || product.todas_las_imagenes.length === 0)) return;
    setAnalyzingImageId(product.id);
    try {
      const res = await fetch('http://localhost:8000/api/analyze-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          imagenes: product.todas_las_imagenes || [product.imagen_url], 
          titulo: product.titulo,
          seller_notes: product.seller_notes || ""
        })
      });
      if (!res.ok) throw new Error("Error analizando imagen");
      const data = await res.json();
      setVisualAnalysis(prev => ({ ...prev, [product.id]: data }));
    } catch (err) {
      console.error(err);
      alert("No se pudo analizar la imagen. Intenta de nuevo.");
    }
    setAnalyzingImageId(null);
  }

  async function handleRealTimeSearch(e) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    
    setLoading(true)
    setIsRealTimeSearch(true)
    setProducts([])
    setCategoryFilter('all') // Reset category visually
    
    try {
      const res = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery })
      })
      if (!res.ok) throw new Error("Error en búsqueda API")
      const data = await res.json()
      setProducts(data.results || [])
    } catch (err) {
      console.error(err)
      alert("Error al buscar. ¿Está encendido el servidor backend (python server.py)?")
    }
    setLoading(false)
  }

  const submitLocalPrice = async (e) => {
    e.preventDefault()
    if (!localPriceForm.titulo || !localPriceForm.precio_usd) return
    setIsSubmittingPrice(true)
    try {
      const { error } = await supabase
        .from('precios_nicaragua')
        .insert([{
          tipo: localPriceForm.tipo,
          titulo_marketplace: localPriceForm.titulo,
          precio_nic_usd: parseFloat(localPriceForm.precio_usd),
          condicion: localPriceForm.condicion,
          fuente: 'Ingreso Manual Web'
        }])
      
      if (error) throw error
      alert("✅ Precio local registrado exitosamente en la base de datos.")
      setIsPriceModalOpen(false)
      setLocalPriceForm({ titulo: '', tipo: 'laptop', precio_usd: '', condicion: 'Usado' })
    } catch (err) {
      console.error(err)
      alert("Error guardando el precio: " + err.message)
    }
    setIsSubmittingPrice(false)
  }

  const filteredProducts = isRealTimeSearch 
    ? products // If it's a real-time search, show all API results as-is
    : products.filter(p => 
        p.titulo.toLowerCase().includes(searchQuery.toLowerCase()) || 
        (p.marca && p.marca.toLowerCase().includes(searchQuery.toLowerCase()))
      )

  const categories = [
    { id: 'all', name: 'Todos', icon: <Search size={18} /> },
    { id: 'laptop', name: 'Laptops', icon: <Monitor size={18} /> },
    { id: 'phone', name: 'Teléfonos', icon: <Smartphone size={18} /> },
    { id: 'ssd', name: 'Almacenamiento', icon: <HardDrive size={18} /> },
    { id: 'ram', name: 'Memoria RAM', icon: <Cpu size={18} /> }
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
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button type="submit" style={{ background: 'var(--accent-primary)', color: '#fff', padding: '0.4rem 1rem', borderRadius: '100px', fontWeight: '600' }}>
              Buscar
            </button>
          </form>

          <button 
            onClick={() => setIsPriceModalOpen(true)}
            style={{ 
              background: 'var(--bg-card)', border: '1px solid var(--border-color)', 
              color: 'var(--text-main)', padding: '0.75rem', borderRadius: '100px',
              display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: '500'
            }}>
            <DollarSign size={20} color="var(--success)" />
            Registrar Precio Local
          </button>

          <button 
            onClick={() => setIsCartOpen(true)}
            style={{ 
              background: 'var(--bg-card)', border: '1px solid var(--border-color)', 
              color: 'var(--text-main)', padding: '0.75rem', borderRadius: '100px',
              display: 'flex', alignItems: 'center', gap: '0.5rem', position: 'relative'
            }}>
            <ShoppingCart size={20} />
            {cart.length > 0 && (
              <span style={{ 
                position: 'absolute', top: '-5px', right: '-5px', background: 'var(--accent-primary)', 
                color: 'white', fontSize: '0.7rem', width: '20px', height: '20px', 
                borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold'
              }}>
                {cart.length}
              </span>
            )}
          </button>
        </div>
      </header>

      <div className="main-layout animate-fade-in">
        {/* Sidebar Filters */}
        <aside className="filters-panel glass-panel">
          <div className="filter-group">
            <h3 className="filter-title flex items-center gap-2">
              <Filter size={16} /> Categorías
            </h3>
            <div className="flex-col gap-2 mt-4">
              {categories.map(c => (
                <button 
                  key={c.id}
                  onClick={() => setCategoryFilter(c.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: categoryFilter === c.id ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                    color: categoryFilter === c.id ? 'var(--accent-primary)' : 'var(--text-main)',
                    border: `1px solid ${categoryFilter === c.id ? 'var(--accent-primary)' : 'transparent'}`,
                    fontWeight: categoryFilter === c.id ? '600' : '400',
                    width: '100%',
                    textAlign: 'left'
                  }}
                >
                  {c.icon} {c.name}
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* Product Grid */}
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
                {filteredProducts.map(product => (
                  <div key={product.id} className="product-card glass-panel">
                    {/* Image */}
                    {product.imagen_url ? (
                      <img src={product.imagen_url} alt={product.titulo} className="product-image" />
                    ) : (
                      <div className="product-image flex justify-center items-center" style={{ background: '#f3f4f6' }}>
                        <Monitor size={48} color="#9ca3af" />
                      </div>
                    )}
                    
                    {/* Content */}
                    <div className="product-content">
                      <h3 className="product-title">{product.titulo}</h3>
                      <div className="product-price">${product.precio?.toFixed(2)}</div>
                      
                      <div className="product-meta" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {product.marca && <span className="badge accent">{product.marca.toUpperCase()}</span>}
                        <span className="badge">{product.condicion}</span>
                        {product.es_subasta && <span className="badge warning">SUBASTA</span>}
                        
                        {!visualAnalysis[product.id] && (
                          <button 
                            onClick={() => scanImage(product)} 
                            disabled={analyzingImageId === product.id}
                            title="Escanear con IA Visual"
                            style={{ 
                              background: 'transparent', color: 'var(--text-muted)', 
                              cursor: 'pointer', padding: '0.2rem', marginLeft: 'auto',
                              display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.8rem'
                            }}
                          >
                            {analyzingImageId === product.id ? <Loader2 size={16} className="spinner" /> : <Eye size={16} />}
                            {analyzingImageId === product.id ? 'Analizando...' : 'Escanear IA'}
                          </button>
                        )}
                      </div>
                      
                      {/* Visual Analysis Result Overlay */}
                      {visualAnalysis[product.id] && (
                        <div style={{ marginTop: '0.5rem', padding: '0.5rem', borderRadius: '4px', background: visualAnalysis[product.id].score > 70 ? 'rgba(46, 213, 115, 0.1)' : 'rgba(255, 71, 87, 0.1)', border: `1px solid ${visualAnalysis[product.id].score > 70 ? 'var(--success)' : 'var(--danger)'}`, fontSize: '0.85rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 'bold', color: visualAnalysis[product.id].score > 70 ? 'var(--success)' : 'var(--danger)' }}>
                            <Eye size={14}/> Visual: {visualAnalysis[product.id].calidad_visual.toUpperCase()} ({visualAnalysis[product.id].score}/100)
                          </div>
                          <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-main)', fontSize: '0.8rem' }}>{visualAnalysis[product.id].nota}</p>
                        </div>
                      )}

                      {/* Profitability */}
                      {product.rentabilidad ? (
                        <div className="profit-block">
                          <div className="profit-row">
                            <span style={{ color: 'var(--text-muted)' }}>Venta NIC:</span>
                            <span className="profit-val">${product.rentabilidad.precio_estimado_nic?.toFixed(2) || '?'}</span>
                          </div>
                          <div className="profit-row">
                            <span style={{ color: 'var(--text-muted)' }}>Margen:</span>
                            <span className="profit-val" style={{ color: product.rentabilidad.porcentaje_ganancia > 40 ? 'var(--success)' : 'var(--warning)' }}>
                              ${product.rentabilidad.margen_estimado?.toFixed(2) || '?'} ({product.rentabilidad.porcentaje_ganancia || '?'}%)
                            </span>
                          </div>
                        </div>
                      ) : (
                        product.precio_estimado_nic && !product.es_subasta && (
                          <div className="profit-block">
                            <div className="profit-row">
                              <span style={{ color: 'var(--text-muted)' }}>Venta NIC:</span>
                              <span className="profit-val">${product.precio_estimado_nic.toFixed(2)}</span>
                            </div>
                            <div className="profit-row">
                              <span style={{ color: 'var(--text-muted)' }}>Margen:</span>
                              <span className="profit-val" style={{ color: product.porcentaje_ganancia > 40 ? 'var(--success)' : 'var(--warning)' }}>
                                ${product.margen_estimado?.toFixed(2)} ({product.porcentaje_ganancia}%)
                              </span>
                            </div>
                          </div>
                        )
                      )}
                      
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                        <a href={product.enlace} target="_blank" rel="noreferrer" className="buy-btn" style={{ flex: 1, padding: '0.5rem', fontSize: '0.9rem' }}>
                          Ver eBay
                        </a>
                        <button 
                          onClick={() => toggleCartItem(product)}
                          style={{ 
                            background: cart.find(i => i.id === product.id) ? 'var(--success)' : 'var(--bg-card)',
                            border: `1px solid ${cart.find(i => i.id === product.id) ? 'var(--success)' : 'var(--border-color)'}`,
                            color: 'white', padding: '0.5rem', borderRadius: '8px', flex: 1,
                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontSize: '0.9rem'
                          }}
                        >
                          {cart.find(i => i.id === product.id) ? <><Check size={16}/> Agregado</> : <><Plus size={16}/> Recomendar</>}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
                
                {filteredProducts.length === 0 && (
                  <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                    No se encontraron productos. Intenta hacer una búsqueda en tiempo real arriba.
                  </div>
                )}
              </div>
            </>
          )}
        </main>
      </div>

      {/* Cart Sidebar Modal */}
      {isCartOpen && (
        <div style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: '400px', maxWidth: '100%',
          background: 'var(--bg-dark)', borderLeft: '1px solid var(--border-color)',
          zIndex: 1000, display: 'flex', flexDirection: 'column', boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
          animation: 'fadeIn 0.2s ease-out'
        }}>
          <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 className="flex items-center gap-2"><ShoppingCart size={24} /> Recomendaciones</h2>
            <button onClick={() => setIsCartOpen(false)} style={{ background: 'transparent', color: 'var(--text-muted)' }}><X size={24} /></button>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {cart.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '2rem' }}>
                No hay productos seleccionados.
              </div>
            ) : (
              cart.map(item => (
                <div key={item.id} className="glass-panel" style={{ padding: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  {item.imagen_url && <img src={item.imagen_url} alt="" style={{ width: '60px', height: '60px', objectFit: 'contain', background: '#fff', borderRadius: '4px' }} />}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.9rem', fontWeight: '500', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{item.titulo}</div>
                    <div style={{ fontWeight: 'bold', color: 'var(--accent-primary)', marginTop: '0.25rem' }}>${item.precio?.toFixed(2)}</div>
                  </div>
                  <button onClick={() => toggleCartItem(item)} style={{ background: 'transparent', color: 'var(--danger)' }}><X size={20} /></button>
                </div>
              ))
            )}
          </div>

          <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', background: 'var(--bg-card)' }}>
            <button 
              onClick={sendCartToTelegram}
              disabled={cart.length === 0 || isSendingCart}
              style={{
                width: '100%', padding: '1rem', borderRadius: '8px',
                background: cart.length === 0 ? 'var(--border-color)' : 'var(--accent-primary)',
                color: 'white', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem',
                fontWeight: 'bold', fontSize: '1.1rem', cursor: cart.length === 0 ? 'not-allowed' : 'pointer',
                opacity: isSendingCart ? 0.7 : 1
              }}
            >
              <Send size={20} /> {isSendingCart ? "Enviando..." : `Enviar ${cart.length} a Telegram`}
            </button>
          </div>
        </div>
      )}
      
      {/* Overlay to close cart */}
      {isCartOpen && (
        <div 
          onClick={() => setIsCartOpen(false)}
          style={{ position: 'fixed', top: 0, left: 0, right: '400px', bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 999 }}
        />
      )}

      {/* Local Price Modal */}
      {isPriceModalOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)',
          zIndex: 2000, display: 'flex', justifyContent: 'center', alignItems: 'center'
        }}>
          <div className="glass-panel animate-fade-in" style={{ width: '90%', maxWidth: '500px', padding: '2rem', position: 'relative' }}>
            <button onClick={() => setIsPriceModalOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}><X/></button>
            <h2 className="flex items-center gap-2" style={{ marginBottom: '1.5rem', color: 'var(--success)' }}>
              <DollarSign size={24} /> Registrar Precio en Nicaragua
            </h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Enseña a la IA a cuánto se vende un producto en el mercado local. La IA usará esto como referencia para calcular márgenes en tus futuras búsquedas.
            </p>
            <form onSubmit={submitLocalPrice} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label htmlFor="titulo_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Producto (Marca, Modelo, Specs)</label>
                <input id="titulo_producto" name="titulo_producto" required type="text" placeholder="Ej: Lenovo Thinkpad E14 Gen 2 16GB RAM 512GB" value={localPriceForm.titulo} onChange={e => setLocalPriceForm({...localPriceForm, titulo: e.target.value})} style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white' }} />
              </div>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <div style={{ flex: 1 }}>
                  <label htmlFor="categoria_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Categoría</label>
                  <select id="categoria_producto" name="categoria_producto" value={localPriceForm.tipo} onChange={e => setLocalPriceForm({...localPriceForm, tipo: e.target.value})} style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white' }}>
                    <option value="laptop">Laptop</option>
                    <option value="phone">Teléfono</option>
                    <option value="ssd">Almacenamiento (SSD)</option>
                    <option value="ram">Memoria RAM</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label htmlFor="precio_usd" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Precio Venta (USD)</label>
                  <input id="precio_usd" name="precio_usd" required type="number" min="1" step="0.01" placeholder="Ej: 420" value={localPriceForm.precio_usd} onChange={e => setLocalPriceForm({...localPriceForm, precio_usd: e.target.value})} style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white' }} />
                </div>
              </div>
              <div>
                <label htmlFor="condicion_producto" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Condición Normalizada</label>
                <select id="condicion_producto" name="condicion_producto" value={localPriceForm.condicion} onChange={e => setLocalPriceForm({...localPriceForm, condicion: e.target.value})} style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white' }}>
                  <option value="Usado">Usado</option>
                  <option value="Nuevo">Nuevo</option>
                  <option value="Refurbished">Refurbished</option>
                </select>
              </div>
              <button disabled={isSubmittingPrice} type="submit" className="buy-btn" style={{ marginTop: '1rem', background: 'var(--success)', opacity: isSubmittingPrice ? 0.7 : 1 }}>
                {isSubmittingPrice ? "Guardando..." : "Guardar en Base de Datos"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
