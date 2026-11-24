import { startTransition, useCallback, useDeferredValue, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  Check,
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock,
  Cpu,
  DollarSign,
  Eye,
  Filter,
  HardDrive,
  Loader2,
  Maximize2,
  Monitor,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShoppingCart,
  Smartphone,
  Square,
  Store,
  TrendingUp,
  Undo2,
  X,
} from 'lucide-react'
import { api } from './api'
import { supabase } from './supabase'

const EMPTY_SCAN_STATE = Object.freeze({ status: 'idle', data: null, error: null })
const SEARCH_EXAMPLES = [
  'ThinkPad E14 open box',
  'Latitude 7420 en very good',
  'EliteBook restauradas por HP',
]
const SEARCH_CONDITION_LABELS = {
  new: 'Nuevas',
  open_box: 'Open box',
  certified_refurbished: 'Restauradas por eBay',
  excellent: 'Excelente',
  very_good: 'Very good',
  good: 'Good',
  refurbished: 'Restauradas',
  used: 'Usadas',
  for_parts: 'Para piezas',
}
const SEARCH_CATEGORY_LABELS = {
  '175672': 'Laptops',
  '9355': 'Telefonos',
  '175669': 'Almacenamiento',
  '170083': 'Memoria RAM',
}
const BRAND_DISPLAY_NAMES = {
  acer: 'Acer',
  alienware: 'Alienware',
  apple: 'Apple',
  asus: 'ASUS',
  dell: 'Dell',
  fujitsu: 'Fujitsu',
  gigabyte: 'Gigabyte',
  hp: 'HP',
  huawei: 'Huawei',
  lenovo: 'Lenovo',
  lg: 'LG',
  microsoft: 'Microsoft Surface',
  msi: 'MSI',
  panasonic: 'Panasonic',
  razer: 'Razer',
  samsung: 'Samsung',
  toshiba: 'Toshiba',
}

function formatDisplayName(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return ''
  return BRAND_DISPLAY_NAMES[normalized] || normalized.replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function buildSearchInsightPills(parsed) {
  if (!parsed || typeof parsed !== 'object') {
    return []
  }

  const pills = []
  const sellerUsernames = Array.isArray(parsed.sellerUsernames) ? parsed.sellerUsernames.filter(Boolean) : []

  if (parsed.q) {
    pills.push({ label: 'Busqueda', value: parsed.q, tone: 'neutral' })
  }

  if (parsed.categoryId) {
    pills.push({
      label: 'Categoria',
      value: SEARCH_CATEGORY_LABELS[String(parsed.categoryId)] || String(parsed.categoryId),
      tone: 'neutral',
    })
  }

  if (parsed.conditionPreference) {
    pills.push({
      label: 'Condicion',
      value: SEARCH_CONDITION_LABELS[parsed.conditionPreference] || parsed.conditionPreference,
      tone: 'accent',
    })
  }

  if (Array.isArray(parsed.brandHints) && parsed.brandHints.length > 0) {
    pills.push({
      label: parsed.brandHints.length > 1 ? 'Marcas' : 'Marca',
      value: parsed.brandHints.map(formatDisplayName).join(', '),
      tone: 'accent',
    })
  }

  if (parsed.refurbisherHint) {
    pills.push({
      label: 'Restaurado por',
      value: parsed.refurbisherHint === 'ebay' ? 'eBay' : formatDisplayName(parsed.refurbisherHint),
      tone: 'success',
    })
  }

  if (parsed.officialStoreBrand) {
    pills.push({
      label: 'Tienda oficial',
      value: formatDisplayName(parsed.officialStoreBrand),
      tone: 'success',
    })
  }

  if (sellerUsernames.length > 0) {
    pills.push({
      label: sellerUsernames.length > 1 ? 'Sellers' : 'Seller',
      value: sellerUsernames.join(', '),
      tone: 'success',
    })
  } else if (parsed.seller) {
    pills.push({ label: 'Seller', value: parsed.seller, tone: 'success' })
  }

  if (parsed.minPrice || parsed.maxPrice) {
    const min = parsed.minPrice || '0'
    const max = parsed.maxPrice || 'sin tope'
    pills.push({ label: 'Precio', value: `${min} - ${max}`, tone: 'neutral' })
  }

  return pills
}

function getScanButtonLabel(status) {
  if (status === 'loading') return 'Analizando...'
  if (status === 'error') return 'Reintentar'
  if (status === 'success') return 'Reescanear'
  return 'Escanear IA'
}

function toHighResImageUrl(url) {
  if (!url || typeof url !== 'string') return url
  let clean = url
  // Reemplazo de eBay: s-l225/s-l300/s-l500/s-l640 por s-l1600 HD ultra nitido
  clean = clean.replace(/\/s-l\d+\.(jpg|jpeg|png|webp)/gi, '/s-l1600.$1')
  // Reemplazo de Amazon: ._SL160_ / ._AC_US40_ por ._SL1500_
  return clean
}

function getRealStoreId(product) {
  if (!product) return 'ebay'
  const store = String(product.tienda || '').trim().toLowerCase()
  if (store.includes('amazon')) return 'amazon'
  if (store.includes('bestbuy') || store.includes('best buy')) return 'bestbuy'
  if (store.includes('walmart')) return 'walmart'
  if (store.includes('target')) return 'target'
  if (store.includes('ebay')) return 'ebay'

  const url = String(product.enlace || product.link || '').toLowerCase()
  if (url.includes('amazon.com')) return 'amazon'
  if (url.includes('bestbuy.com')) return 'bestbuy'
  if (url.includes('walmart.com')) return 'walmart'
  if (url.includes('target.com')) return 'target'
  if (url.includes('ebay.com')) return 'ebay'
  return 'ebay'
}

function getSanitizedStoreUrl(product) {
  if (!product) return 'https://www.ebay.com'

  // Si existe el enlace original directo a la publicación específica (ej. eBay / item ID), redirigir directamente al producto exacto
  const directLink = product.original_enlace || product.enlace || product.link || ''
  if (directLink && directLink.startsWith('http') && (directLink.includes('ebay.com/itm/') || directLink.includes('ebay.com/sch/'))) {
    return directLink
  }

  const store = String(product.tienda || '').trim().toLowerCase()
  const q = encodeURIComponent(String(product.titulo || 'laptop').slice(0, 80))
  const url = String(directLink).toLowerCase()

  if (store.includes('walmart') || url.includes('walmart.com')) {
    if (url.includes('walmart.com/ip/') || url.includes('walmart.com/search')) return directLink
    return `https://www.walmart.com/search?q=${q}`
  }
  if (store.includes('amazon') || url.includes('amazon.com')) {
    if (url.includes('amazon.com/dp/') || url.includes('amazon.com/s?')) return directLink
    return `https://www.amazon.com/s?k=${q}`
  }
  if (store.includes('bestbuy') || url.includes('bestbuy.com')) {
    if (url.includes('bestbuy.com/site/searchpage.jsp') || url.includes('bestbuy.com/site/')) return directLink
    return `https://www.bestbuy.com/site/searchpage.jsp?st=${q}`
  }
  if (store.includes('target') || url.includes('target.com')) {
    if (url.includes('target.com/p/') || url.includes('target.com/s?')) return directLink
    return `https://www.target.com/s?searchTerm=${q}`
  }

  if (directLink && directLink.startsWith('http')) {
    return directLink
  }
  return `https://www.ebay.com/sch/i.html?_nkw=${q}`
}

function getStoreBadge(tiendaName, linkUrl = '') {
  const store = String(tiendaName || '').trim().toLowerCase()
  if (store.includes('amazon')) return { name: 'Amazon', bg: '#FF9900', color: '#000000' }
  if (store.includes('bestbuy') || store.includes('best buy')) return { name: 'Best Buy', bg: '#0046BE', color: '#FFFFFF' }
  if (store.includes('walmart')) return { name: 'Walmart', bg: '#0071DC', color: '#FFFFFF' }
  if (store.includes('target')) return { name: 'Target', bg: '#CC0000', color: '#FFFFFF' }
  if (store.includes('mercari')) return { name: 'Mercari', bg: '#4285F4', color: '#FFFFFF' }
  if (store.includes('aliexpress')) return { name: 'AliExpress', bg: '#FF4747', color: '#FFFFFF' }

  const url = String(linkUrl || '').toLowerCase()
  if (url.includes('amazon.com')) return { name: 'Amazon', bg: '#FF9900', color: '#000000' }
  if (url.includes('bestbuy.com')) return { name: 'Best Buy', bg: '#0046BE', color: '#FFFFFF' }
  if (url.includes('walmart.com')) return { name: 'Walmart', bg: '#0071DC', color: '#FFFFFF' }
  if (url.includes('target.com')) return { name: 'Target', bg: '#CC0000', color: '#FFFFFF' }
  if (url.includes('ebay.com')) return { name: 'eBay', bg: '#E53238', color: '#FFFFFF' }

  return { name: 'eBay', bg: '#E53238', color: '#FFFFFF' }
}

function getProductImages(product, extraImages = []) {
  if (!product) return []
  let imgs = []
  if (Array.isArray(product.imagenes) && product.imagenes.length > 0) {
    imgs = [...product.imagenes]
  }
  if (Array.isArray(product.todas_las_imagenes) && product.todas_las_imagenes.length > 0) {
    product.todas_las_imagenes.forEach((i) => {
      if (i && !imgs.includes(i)) imgs.push(i)
    })
  }
  if (Array.isArray(extraImages) && extraImages.length > 0) {
    extraImages.forEach((i) => {
      if (i && !imgs.includes(i)) imgs.push(i)
    })
  }
  if (imgs.length === 0 && (product.imagen_url || product.imagen)) {
    imgs = [product.imagen_url || product.imagen]
  }

  return [...new Set(imgs.filter(Boolean))].map(toHighResImageUrl)
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

function AnnotationCanvas({ imageUrl, shapes = [], onAddShape, tool, color, strokeWidth }) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [startPos, setStartPos] = useState({ x: 0, y: 0 })
  const [currentPos, setCurrentPos] = useState({ x: 0, y: 0 })
  const [freePoints, setFreePoints] = useState([])
  const [imageObj, setImageObj] = useState(null)

  // Cargar la imagen y configurar dimensiones del canvas
  useEffect(() => {
    if (!imageUrl) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl
    img.onload = () => {
      setImageObj(img)
    }
  }, [imageUrl])

  // Redibujar el canvas
  const redrawCanvas = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !imageObj) return
    const ctx = canvas.getContext('2d')
    
    // Ajustar dimensiones internas del canvas
    canvas.width = imageObj.naturalWidth || 800
    canvas.height = imageObj.naturalHeight || 600

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(imageObj, 0, 0, canvas.width, canvas.height)

    // Dibujar formas existentes
    shapes.forEach((s) => {
      ctx.strokeStyle = s.color || '#ef4444'
      ctx.lineWidth = s.strokeWidth || 4
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.beginPath()

      if (s.type === 'circle') {
        const rx = Math.abs(s.width / 2)
        const ry = Math.abs(s.height / 2)
        const cx = s.x + s.width / 2
        const cy = s.y + s.height / 2
        ctx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI)
        ctx.stroke()
      } else if (s.type === 'square') {
        ctx.rect(s.x, s.y, s.width, s.height)
        ctx.stroke()
      } else if (s.type === 'free' && Array.isArray(s.points) && s.points.length > 1) {
        ctx.moveTo(s.points[0].x, s.points[0].y)
        for (let i = 1; i < s.points.length; i++) {
          ctx.lineTo(s.points[i].x, s.points[i].y)
        }
        ctx.stroke()
      }
    })

    // Dibujar forma actual mientras el usuario arrastra
    if (isDrawing) {
      ctx.strokeStyle = color
      ctx.lineWidth = strokeWidth
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.beginPath()

      if (tool === 'circle') {
        const w = currentPos.x - startPos.x
        const h = currentPos.y - startPos.y
        const rx = Math.abs(w / 2)
        const ry = Math.abs(h / 2)
        const cx = startPos.x + w / 2
        const cy = startPos.y + h / 2
        ctx.ellipse(cx, cy, rx, ry, 0, 0, 2 * Math.PI)
        ctx.stroke()
      } else if (tool === 'square') {
        ctx.rect(startPos.x, startPos.y, currentPos.x - startPos.x, currentPos.y - startPos.y)
        ctx.stroke()
      } else if (tool === 'free' && freePoints.length > 1) {
        ctx.moveTo(freePoints[0].x, freePoints[0].y)
        for (let i = 1; i < freePoints.length; i++) {
          ctx.lineTo(freePoints[i].x, freePoints[i].y)
        }
        ctx.stroke()
      }
    }
  }, [imageObj, shapes, isDrawing, startPos, currentPos, freePoints, tool, color, strokeWidth])

  useEffect(() => {
    redrawCanvas()
  }, [redrawCanvas])

  const getCanvasCoords = (e) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    }
  }

  const handleMouseDown = (e) => {
    const coords = getCanvasCoords(e)
    setIsDrawing(true)
    setStartPos(coords)
    setCurrentPos(coords)
    if (tool === 'free') {
      setFreePoints([coords])
    }
  }

  const handleMouseMove = (e) => {
    if (!isDrawing) return
    const coords = getCanvasCoords(e)
    setCurrentPos(coords)
    if (tool === 'free') {
      setFreePoints((prev) => [...prev, coords])
    }
  }

  const handleMouseUp = () => {
    if (!isDrawing) return
    setIsDrawing(false)

    let newShape = null
    if (tool === 'circle' || tool === 'square') {
      const w = currentPos.x - startPos.x
      const h = currentPos.y - startPos.y
      if (Math.abs(w) > 5 || Math.abs(h) > 5) {
        newShape = {
          type: tool,
          x: startPos.x,
          y: startPos.y,
          width: w,
          height: h,
          color,
          strokeWidth,
        }
      }
    } else if (tool === 'free' && freePoints.length > 1) {
      newShape = {
        type: 'free',
        points: freePoints,
        color,
        strokeWidth,
      }
    }

    if (newShape && onAddShape) {
      onAddShape(newShape)
    }
    setFreePoints([])
  }

  return (
    <div ref={containerRef} className="ml-canvas-area">
      {!imageObj && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          Cargando imagen para anotación...
        </div>
      )}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ display: imageObj ? 'block' : 'none' }}
      />
    </div>
  )
}

function App() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchInsights, setSearchInsights] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [isRealTimeSearch, setIsRealTimeSearch] = useState(false)

  // Estado para la Galería / Visor de Imágenes en Grande (Multi-imagen)
  const [galleryState, setGalleryState] = useState({ isOpen: false, product: null, currentIndex: 0, extraImages: [], isLoadingExtra: false })

  const openGallery = async (product, initialIndex = 0) => {
    setGalleryState({ isOpen: true, product, currentIndex: initialIndex, extraImages: [], isLoadingExtra: true })
    if (product?.id) {
      try {
        const res = await api.getItemImages(product.id)
        if (res?.status === 'success' && Array.isArray(res.imagenes) && res.imagenes.length > 0) {
          setGalleryState((prev) => ({
            ...prev,
            extraImages: res.imagenes,
            isLoadingExtra: false,
          }))
        } else {
          setGalleryState((prev) => ({ ...prev, isLoadingExtra: false }))
        }
      } catch (e) {
        console.error('Error obteniendo imágenes HD:', e)
        setGalleryState((prev) => ({ ...prev, isLoadingExtra: false }))
      }
    } else {
      setGalleryState((prev) => ({ ...prev, isLoadingExtra: false }))
    }
  }

  const closeGallery = () => {
    setGalleryState({ isOpen: false, product: null, currentIndex: 0, extraImages: [], isLoadingExtra: false })
  }

  const nextGalleryImage = () => {
    if (!galleryState.product) return
    const imgs = getProductImages(galleryState.product, galleryState.extraImages)
    setGalleryState((prev) => ({
      ...prev,
      currentIndex: (prev.currentIndex + 1) % imgs.length,
    }))
  }

  const prevGalleryImage = () => {
    if (!galleryState.product) return
    const imgs = getProductImages(galleryState.product, galleryState.extraImages)
    setGalleryState((prev) => ({
      ...prev,
      currentIndex: (prev.currentIndex - 1 + imgs.length) % imgs.length,
    }))
  }



  // Filtros Avanzados por Tiendas (APIs Multi-Tienda)
  const CROSS_REF_STORES = [
    { id: 'walmart', label: 'Walmart', badge: '🏬', buildUrl: (q) => `https://www.walmart.com/search?q=${q}` },
    { id: 'amazon', label: 'Amazon', badge: '📦', buildUrl: (q) => `https://www.amazon.com/s?k=${q}` },
    { id: 'bestbuy', label: 'Best Buy', badge: '🟡', buildUrl: (q) => `https://www.bestbuy.com/site/searchpage.jsp?st=${q}` },
    { id: 'target', label: 'Target', badge: '🎯', buildUrl: (q) => `https://www.target.com/s?searchTerm=${q}` },
  ]
  const [enabledCrossRefs, setEnabledCrossRefs] = useState(['walmart', 'amazon', 'bestbuy', 'target'])

  const toggleCrossRef = (storeId) => {
    setEnabledCrossRefs((prev) =>
      prev.includes(storeId)
        ? prev.filter((id) => id !== storeId)
        : [...prev, storeId]
    )
  }

  // Filtros Avanzados por Casillas: Condición, Tipo de Venta y Ordenamiento de Subastas

  const [selectedConditions, setSelectedConditions] = useState([])
  const [selectedBuyingOption, setSelectedBuyingOption] = useState('ALL')
  const [selectedSortOrder, setSelectedSortOrder] = useState('endingSoonest')

  const CONDITION_OPTIONS = [
    { id: '1000', label: 'Nuevo', badge: '🆕' },
    { id: '1500', label: 'Open Box', badge: '📦' },
    { id: '2000', label: 'Reacondicionado Certificado', badge: '🏷️' },
    { id: '2010', label: 'Excelente Reacondicionado', badge: '✨' },
    { id: '2020', label: 'Muy Bueno Reacondicionado', badge: '👍' },
    { id: '2030', label: 'Bueno Reacondicionado', badge: '👌' },
    { id: '3000', label: 'Usado', badge: '🔄' },
    { id: '7000', label: 'Para Piezas / Repuesto', badge: '🔧' },
  ]

  const toggleConditionFilter = (conditionId) => {
    setSelectedConditions((prev) =>
      prev.includes(conditionId)
        ? prev.filter((id) => id !== conditionId)
        : [...prev, conditionId]
    )
  }

  // Filtro Estricto de Marca y Líneas + Autocompletado IA
  const [selectedBrandFilter, setSelectedBrandFilter] = useState('all')

  const [selectedLineFilter, setSelectedLineFilter] = useState('')
  const [lineSuggestions, setLineSuggestions] = useState([])
  const [isSearchingLines, setIsSearchingLines] = useState(false)


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
  const [localPriceImage, setLocalPriceImage] = useState(null)
  const [isParsingImage, setIsParsingImage] = useState(false)
  
  const [isLocalPricesListOpen, setIsLocalPricesListOpen] = useState(false)
  const [localPricesList, setLocalPricesList] = useState([])
  const [editingLocalPriceId, setEditingLocalPriceId] = useState(null)
  const [isSelectingForLocalPrice, setIsSelectingForLocalPrice] = useState(false)

  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  
  const [isBotConfigModalOpen, setIsBotConfigModalOpen] = useState(false)
  const [botMaxPrecio, setBotMaxPrecio] = useState(200)
  const [botIsRunning, setBotIsRunning] = useState(true)
  const [isSavingBotConfig, setIsSavingBotConfig] = useState(false)
  const [botLogs, setBotLogs] = useState('')
  const botLogsRef = useRef(null)

  const [isFiltersModalOpen, setIsFiltersModalOpen] = useState(false)
  const [botFilters, setBotFilters] = useState({
    categorias_activas: ["Intel Core i5", "Intel Core i7", "Intel Core i9", "Ryzen 5", "Ryzen 7", "Ryzen 9", "Intel Core i3"],
    estados_activos: ["New", "Open box", "Certified Refurbished", "Excellent Refurbished", "Very Good Refurbished", "Good Refurbished", "Used"]
  })
  const [isSavingFilters, setIsSavingFilters] = useState(false)

  // Feedback Machine Learning ("Equivocado" con Anotación Visual)
  const [isEquivocadoModalOpen, setIsEquivocadoModalOpen] = useState(false)
  const [selectedEquivocadoProduct, setSelectedEquivocadoProduct] = useState(null)
  const [equivocadoPhotos, setEquivocadoPhotos] = useState([])
  const [isLoadingEquivocadoPhotos, setIsLoadingEquivocadoPhotos] = useState(false)
  const [selectedPhotoUrls, setSelectedPhotoUrls] = useState([])
  const [activeAnnotatingPhoto, setActiveAnnotatingPhoto] = useState(null)
  const [annotations, setAnnotations] = useState({}) // { [photoUrl]: { shapes: [], note: '' } }
  const [drawTool, setDrawTool] = useState('circle') // 'circle' | 'square' | 'free'
  const [drawColor, setDrawColor] = useState('#ef4444')
  const [drawStrokeWidth, setDrawStrokeWidth] = useState(3)
  const [equivocadoTags, setEquivocadoTags] = useState([])
  const [equivocadoMotivo, setEquivocadoMotivo] = useState('')
  const [isSubmittingEquivocado, setIsSubmittingEquivocado] = useState(false)

  // Visualización de Collage Numerado de IA
  const [activeCollageModal, setActiveCollageModal] = useState({ isOpen: false, url: '', title: '' })



  const [botSettings, setBotSettings] = useState({ is_running: true, budget: 250, last_seen: null })

  const [isInventoryOpen, setIsInventoryOpen] = useState(false)
  const [inventoryItems, setInventoryItems] = useState([])
  const [isInventoryFormOpen, setIsInventoryFormOpen] = useState(false)
  const [inventoryForm, setInventoryForm] = useState({ titulo: '', tipo: 'laptop', costo_total_usd: '', precio_venta_esperado: '', tracking_number: '', notas: '' })
  const [editingInventoryId, setEditingInventoryId] = useState(null)
  const [finanzas, setFinanzas] = useState(null)
  const [isFinanzasOpen, setIsFinanzasOpen] = useState(false)
  const [trackingResults, setTrackingResults] = useState({})

  const deferredSearchQuery = useDeferredValue(searchQuery)
  const cartIds = new Set(cart.map((item) => item.id))

  const [isRefreshingCatalog, setIsRefreshingCatalog] = useState(false)

  const handleRefreshCatalog = async () => {
    setIsRefreshingCatalog(true)
    setLoading(true)
    try {
      const res = await api.refreshCatalog()
      if (res.results && res.results.length > 0) {
        setIsRealTimeSearch(true)
        setProducts(res.results)
        setSearchInsights({
          rawQuery: `Ofertas Frescas (${res.query})`,
          parsed: { q: res.query },
        })
      } else {
        await fetchProducts()
      }
    } catch (err) {
      console.error(err)
      await fetchProducts()
    } finally {
      setIsRefreshingCatalog(false)
      setLoading(false)
    }
  }

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
        // Mezclar aleatoriamente el catalogo inicial con datos autenticos
        const shuffled = (data || []).slice().sort(() => Math.random() - 0.5)
        setProducts(shuffled)
      })



    } catch (error) {
      console.error('Error fetching products:', error)
      alert(`Error cargando productos locales: ${error.message || 'desconocido'}`)
    } finally {
      setLoading(false)
    }
  })

  useEffect(() => {
    const fetchLines = async () => {
      const marcaQuery = selectedBrandFilter === 'all' ? '' : selectedBrandFilter
      setIsSearchingLines(true)
      try {
        const data = await api.getLaptopLines(marcaQuery, selectedLineFilter)
        setLineSuggestions(data.lineas || [])
      } catch (e) {
        console.error(e)
      } finally {
        setIsSearchingLines(false)
      }
    }
    const timer = setTimeout(fetchLines, 300)
    return () => clearTimeout(timer)
  }, [selectedBrandFilter, selectedLineFilter])

  useEffect(() => {
    if (isRealTimeSearch) {
      return
    }


    void fetchProducts()
  }, [categoryFilter, isRealTimeSearch])

  useEffect(() => {
    const fetchBotSettings = async () => {
      try {
        // Leer config + estado del proceso + filtros desde el backend
        const apiConfig = await api.getBotConfig()
        setBotSettings({
          is_running: apiConfig.is_running,
          budget: apiConfig.max_precio,
          last_seen: apiConfig.last_seen,
          process_alive: apiConfig.process_alive,
        })
        setBotMaxPrecio(apiConfig.max_precio)
        if (apiConfig.filters) {
          setBotFilters(apiConfig.filters)
        }
      } catch(e) { console.error(e) }
    }
    fetchBotSettings()

    // Polling cada 30s para actualizar el estado del proceso
    const interval = setInterval(fetchBotSettings, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const channel = supabase
      .channel('bot_settings_changes')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'bot_settings', filter: 'id=eq.1' }, (payload) => {
        const newData = payload.new
        if (newData) {
          setBotSettings(prev => ({
            ...prev,
            is_running: newData.is_running,
            budget: newData.budget,
            last_seen: newData.last_seen
          }))
          setBotMaxPrecio(newData.budget)
        }
      })
      .subscribe()
      
    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  const handleCategoryChange = (categoryId) => {
    if (categoryId === categoryFilter && !isRealTimeSearch) {
      return
    }

    startTransition(() => {
      setCategoryFilter(categoryId)
      if (isRealTimeSearch) {
        setIsRealTimeSearch(false)
        setSearchInsights(null)
      }
    })
  }

  const applySearchExample = (example) => {
    setSearchQuery(example)
  }

  const clearRealTimeSearch = () => {
    startTransition(() => {
      setIsRealTimeSearch(false)
      setSearchInsights(null)
    })
  }

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
        condicion: product.condicion || '',
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

    const previousProducts = products
    const previousMode = isRealTimeSearch
    const previousInsights = searchInsights

    setLoading(true)

    try {
      const data = await api.search(
        searchQuery.trim(),
        priceMax ? parseFloat(priceMax) : null,
        {
          conditionIds: selectedConditions,
          buyingOptions: selectedBuyingOption,
          sortOrder: selectedSortOrder,
        }
      )


      startTransition(() => {
        setIsRealTimeSearch(true)
        setCategoryFilter('all')
        setProducts(data.results || [])
        setSearchInsights({
          rawQuery: searchQuery.trim(),
          parsed: data.query_ia || null,
        })
      })
    } catch (error) {
      console.error(error)
      startTransition(() => {
        setIsRealTimeSearch(previousMode)
        setProducts(previousProducts)
        setSearchInsights(previousInsights)
      })
      alert(`Error al buscar ofertas: ${error.message || 'desconocido'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleImageUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async (evt) => {
      const base64 = evt.target.result
      setLocalPriceImage(base64)
      setIsParsingImage(true)
      try {
        const result = await api.parseLocalImage({ image_base64: base64 })
        if (result.status === 'success' && result.titulo) {
          setLocalPriceForm(f => ({ ...f, titulo: result.titulo }))
        }
      } catch (err) {
        console.error(err)
      } finally {
        setIsParsingImage(false)
      }
    }
    reader.readAsDataURL(file)
  }

  const submitLocalPrice = async (event) => {
    event.preventDefault()
    if (!localPriceForm.titulo || !localPriceForm.precio_usd) return

    setIsSubmittingPrice(true)
    try {
      const payload = {
        tipo: localPriceForm.tipo,
        titulo_marketplace: localPriceForm.titulo,
        precio_nic_usd: parseFloat(localPriceForm.precio_usd),
        condicion: localPriceForm.condicion,
        fuente: 'Ingreso Manual Web',
      }
      
      if (localPriceImage) {
        payload.imagen_url = localPriceImage
      }

      if (editingLocalPriceId) {
        const { error } = await supabase.from('precios_nicaragua').update(payload).eq('id', editingLocalPriceId)
        if (error) throw error
        alert('Precio local actualizado exitosamente.')
      } else {
        const { error } = await supabase.from('precios_nicaragua').insert([payload])
        if (error) throw error
        alert('Precio local registrado exitosamente en la base de datos.')
      }

      setIsPriceModalOpen(false)
      setLocalPriceForm({ titulo: '', tipo: 'laptop', precio_usd: '', condicion: 'Usado' })
      setLocalPriceImage(null)
      setEditingLocalPriceId(null)
      
      // Si el modal de lista estaba abierto de fondo, actualizarlo
      if (isLocalPricesListOpen) {
        openLocalPricesList()
      }
    } catch (error) {
      console.error(error)
      alert(`Error guardando el precio: ${error.message}`)
    } finally {
      setIsSubmittingPrice(false)
    }
  }

  const handleEditLocalPrice = (item) => {
    setLocalPriceForm({
      titulo: item.titulo_marketplace || '',
      tipo: item.tipo || 'laptop',
      precio_usd: item.precio_nic_usd || '',
      condicion: item.condicion || 'Usado'
    })
    setLocalPriceImage(item.imagen_url || null)
    setEditingLocalPriceId(item.id)
    setIsLocalPricesListOpen(false)
    setIsPriceModalOpen(true)
  }

  const handleDeleteLocalPrice = async (id) => {
    if (!window.confirm('¿Seguro que deseas eliminar este precio registrado?')) return
    try {
      const { error } = await supabase.from('precios_nicaragua').delete().eq('id', id)
      if (error) throw error
      openLocalPricesList() // refresh
    } catch (err) {
      console.error(err)
      alert(`Error al eliminar: ${err.message}`)
    }
  }

  const openLocalPricesList = async () => {
    setIsLocalPricesListOpen(true)
    try {
      const { data, error } = await supabase
        .from('precios_nicaragua')
        .select('*')
        .order('registrado_en', { ascending: false })
      if (error) throw error
      setLocalPricesList(data || [])
    } catch (err) {
      console.error(err)
    }
  }

  const handleSelectProductForLocal = async (product) => {
    setIsSelectingForLocalPrice(false)
    setIsPriceModalOpen(true)
    setLocalPriceImage(product.imagen_url)
    setIsParsingImage(true)
    
    try {
      const payload = { 
        image_url: product.imagen_url, 
        original_title: product.titulo,
        item_url: product.enlace,
        extra_specs: {
          marca: product.marca,
          procesador: product.procesador,
          ram: product.ram,
          ssd: product.ssd
        }
      }
      const result = await api.parseLocalImage(payload)
      if (result.status === 'success' && result.titulo) {
        setLocalPriceForm(f => ({ ...f, titulo: result.titulo }))
      } else {
        setLocalPriceForm(f => ({ ...f, titulo: product.titulo }))
      }
    } catch (err) {
      console.error(err)
      setLocalPriceForm(f => ({ ...f, titulo: product.titulo }))
    } finally {
      setIsParsingImage(false)
    }
  }

  const openBotConfigModal = async () => {
    setIsBotConfigModalOpen(true)
    try {
      const config = await api.getBotConfig()
      setBotMaxPrecio(config.max_precio || 200)
      if (typeof config.is_running === 'boolean') {
        setBotIsRunning(config.is_running)
      }
      const logsData = await api.getBotLogs()
      setBotLogs(logsData.logs || 'Sin logs disponibles.')
    } catch (error) {
      console.error(error)
    }
  }

  const saveBotConfig = async (e) => {
    e.preventDefault()
    setIsSavingBotConfig(true)
    try {
      await api.updateBotConfig(parseFloat(botMaxPrecio), botIsRunning)
      alert('Configuración del bot actualizada correctamente.')
      setIsBotConfigModalOpen(false)
    } catch (error) {
      console.error(error)
      alert(`Error guardando configuración: ${error.message}`)
    } finally {
      setIsSavingBotConfig(false)
    }
  }

  useEffect(() => {
    if (!isBotConfigModalOpen) return
    const interval = setInterval(async () => {
      try {
        const logsData = await api.getBotLogs()
        if (logsData.logs) {
          setBotLogs(logsData.logs)
          if (botLogsRef.current) {
            botLogsRef.current.scrollTop = botLogsRef.current.scrollHeight
          }
        }
      } catch (err) {
        // Ignorar fallos temporales en segundo plano
      }
    }, 10000)
    return () => clearInterval(interval)
  }, [isBotConfigModalOpen])


  const toggleBotRunning = async () => {
    const newState = !botSettings.is_running
    setBotSettings(prev => ({ ...prev, is_running: newState })) // Optimistic update
    try {
      const res = await api.updateBotConfig(null, newState)
      setBotSettings(prev => ({ ...prev, is_running: newState, process_alive: res.process_alive }))
    } catch (e) {
      console.error(e)
      setBotSettings(prev => ({ ...prev, is_running: !newState })) // Revert on error
      alert(`Error controlando el bot: ${e.message}`)
    }
  }

  const isBotOnline = () => {
    // Primero chequear si el proceso está vivo (directo del server)
    if (botSettings.process_alive !== undefined) return botSettings.process_alive
    // Fallback al heartbeat de Supabase
    if (!botSettings.last_seen) return false
    const lastSeenDate = new Date(botSettings.last_seen)
    const diffMinutes = (new Date() - lastSeenDate) / (1000 * 60)
    return diffMinutes <= 5
  }

  const openInventory = async () => {
    setIsInventoryOpen(true)
    try {
      const res = await api.getInventario()
      const items = res.items || []
      setInventoryItems(items)

      // Auto-rastrear todos los items en_transito que tengan tracking
      const inTransitWithTracking = items.filter(i => i.estado === 'en_transito' && i.tracking_number)
      let needsRefresh = false
      for (const item of inTransitWithTracking) {
        try {
          const data = await api.trackPackage(item.tracking_number)
          setTrackingResults(prev => ({ ...prev, [item.tracking_number]: { ...data, loading: false } }))
          if (data.auto_updated) needsRefresh = true
        } catch (e) { console.error(e) }
      }
      // Si algún item fue auto-actualizado (delivered→en_stock), refrescar la lista
      if (needsRefresh) {
        const refreshed = await api.getInventario()
        setInventoryItems(refreshed.items || [])
      }
    } catch (e) { console.error(e) }
  }

  const submitInventoryItem = async (e) => {
    e.preventDefault()
    try {
      const payload = {
        titulo: inventoryForm.titulo,
        tipo: inventoryForm.tipo,
        costo_total_usd: parseFloat(inventoryForm.costo_total_usd),
        precio_venta_esperado: inventoryForm.precio_venta_esperado ? parseFloat(inventoryForm.precio_venta_esperado) : undefined,
        tracking_number: inventoryForm.tracking_number || undefined,
        notas: inventoryForm.notas || undefined,
      }
      if (editingInventoryId) {
        await api.updateInventario(editingInventoryId, payload)
      } else {
        await api.createInventario(payload)
      }
      setIsInventoryFormOpen(false)
      setEditingInventoryId(null)
      setInventoryForm({ titulo: '', tipo: 'laptop', costo_total_usd: '', precio_venta_esperado: '', tracking_number: '', notas: '' })
      openInventory()
    } catch (e) {
      console.error(e)
      alert(`Error: ${e.message}`)
    }
  }

  const updateInventoryStatus = async (id, estado, precio_venta_real) => {
    try {
      const updates = { estado }
      if (precio_venta_real !== undefined) updates.precio_venta_real = precio_venta_real
      await api.updateInventario(id, updates)
      openInventory()
    } catch (e) {
      console.error(e)
      alert(`Error: ${e.message}`)
    }
  }

  const deleteInventoryItem = async (id) => {
    if (!window.confirm('¿Eliminar este item del inventario?')) return
    try {
      await api.deleteInventario(id)
      openInventory()
    } catch (e) { console.error(e); alert(`Error: ${e.message}`) }
  }

  const openFinanzas = async () => {
    setIsFinanzasOpen(true)
    try {
      const data = await api.getFinanzas()
      setFinanzas(data)
    } catch (e) { console.error(e) }
  }

  const trackPackage = async (trackingNumber) => {
    setTrackingResults(prev => ({ ...prev, [trackingNumber]: { loading: true } }))
    try {
      const data = await api.trackPackage(trackingNumber)
      setTrackingResults(prev => ({ ...prev, [trackingNumber]: { ...data, loading: false } }))
      // Si el tracking auto-actualizó el inventario, refrescar la lista
      if (data.auto_updated) {
        const res = await api.getInventario()
        setInventoryItems(res.items || [])
      }
    } catch (e) {
      console.error(e)
      setTrackingResults(prev => ({ ...prev, [trackingNumber]: { loading: false, error: e.message } }))
    }
  }

  const handleOpenEquivocadoModal = async (product) => {
    setSelectedEquivocadoProduct(product)
    setEquivocadoMotivo('')
    setEquivocadoTags([])
    setAnnotations({})
    setIsEquivocadoModalOpen(true)
    setIsLoadingEquivocadoPhotos(true)

    // Obtener fotos base
    const initialPhotos = getProductImages(product)
    const baseList = initialPhotos.length > 0 ? initialPhotos : (product.imagen_url ? [product.imagen_url] : [])
    setEquivocadoPhotos(baseList)
    
    // Seleccionar por defecto la primera foto
    const firstPhoto = baseList[0] || null
    if (firstPhoto) {
      setSelectedPhotoUrls([firstPhoto])
      setActiveAnnotatingPhoto(firstPhoto)
    } else {
      setSelectedPhotoUrls([])
      setActiveAnnotatingPhoto(null)
    }

    // Intentar cargar imágenes HD adicionales desde la API si es un item ID válido
    if (product?.id) {
      try {
        const res = await api.getItemImages(product.id)
        if (res?.status === 'success' && Array.isArray(res.imagenes) && res.imagenes.length > 0) {
          const combined = [...new Set([...baseList, ...res.imagenes.map(toHighResImageUrl)])]
          setEquivocadoPhotos(combined)
        }
      } catch (e) {
        console.error('Error obteniendo imagenes adicionales para feedback ML:', e)
      } finally {
        setIsLoadingEquivocadoPhotos(false)
      }
    } else {
      setIsLoadingEquivocadoPhotos(false)
    }
  }

  const togglePhotoSelection = (url) => {
    setSelectedPhotoUrls(prev => {
      if (prev.includes(url)) {
        const next = prev.filter(u => u !== url)
        if (activeAnnotatingPhoto === url) {
          setActiveAnnotatingPhoto(next[0] || null)
        }
        return next
      } else {
        setActiveAnnotatingPhoto(url)
        return [...prev, url]
      }
    })
  }

  const toggleEquivocadoTag = (tag) => {
    setEquivocadoTags(prev => 
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    )
  }

  const handlePhotoNoteChange = (url, note) => {
    setAnnotations(prev => ({
      ...prev,
      [url]: {
        ...(prev[url] || { shapes: [] }),
        note
      }
    }))
  }

  const handleAddShapeToPhoto = (url, shape) => {
    setAnnotations(prev => {
      const current = prev[url] || { shapes: [], note: '' }
      return {
        ...prev,
        [url]: {
          ...current,
          shapes: [...current.shapes, shape]
        }
      }
    })
  }

  const handleUndoShape = (url) => {
    setAnnotations(prev => {
      const current = prev[url] || { shapes: [], note: '' }
      if (!current.shapes.length) return prev
      return {
        ...prev,
        [url]: {
          ...current,
          shapes: current.shapes.slice(0, -1)
        }
      }
    })
  }

  const handleSubmitEquivocado = async (e) => {
    e.preventDefault()
    if (!selectedEquivocadoProduct) return

    if (selectedPhotoUrls.length === 0 && !equivocadoMotivo.trim() && equivocadoTags.length === 0) {
      alert('Por favor selecciona al menos una foto problematica, un tag o escribe una justificacion.')
      return
    }

    setIsSubmittingEquivocado(true)
    try {
      const annotatedItems = selectedPhotoUrls.map(url => ({
        imagen_url: url,
        shapes: annotations[url]?.shapes || [],
        nota: annotations[url]?.note || ''
      }))

      await api.reportWrongProduct({
        producto_id: String(selectedEquivocadoProduct.id || ''),
        titulo: selectedEquivocadoProduct.titulo,
        precio: selectedEquivocadoProduct.precio || 0,
        imagen_url: selectedEquivocadoProduct.imagen_url || selectedPhotoUrls[0] || '',
        motivo_general: equivocadoMotivo.trim(),
        tags: equivocadoTags,
        anotaciones: annotatedItems,
        vendedor: selectedEquivocadoProduct.vendedor || '',
        marca: selectedEquivocadoProduct.marca || '',
      })

      alert('¡Excelente! El reporte de feedback visual y las marcas han sido guardados para reentrenar el modelo ML.')
      setIsEquivocadoModalOpen(false)
      setSelectedEquivocadoProduct(null)
      setEquivocadoPhotos([])
      setSelectedPhotoUrls([])
      setActiveAnnotatingPhoto(null)
      setAnnotations({})
      setEquivocadoTags([])
      setEquivocadoMotivo('')
    } catch (error) {
      console.error(error)
      alert(`Error enviando feedback: ${error.message}`)
    } finally {
      setIsSubmittingEquivocado(false)
    }
  }

  const normalizedQuery = deferredSearchQuery.trim().toLowerCase()
  const brandFilterClean = selectedBrandFilter.toLowerCase()
  const lineFilterClean = selectedLineFilter.trim().toLowerCase()

  const displayProducts = useMemo(() => {
    if (!products || products.length === 0) return []

    return products.map((product) => {
      const searchQ = encodeURIComponent(String(product.titulo || 'laptop').slice(0, 80))
      const crossRefLinks = CROSS_REF_STORES
        .filter((st) => enabledCrossRefs.includes(st.id))
        .map((st) => ({ id: st.id, label: st.label, badge: getStoreBadge(st.label), url: st.buildUrl(searchQ) }))

      const realLink = getSanitizedStoreUrl(product)

      return {
        ...product,
        enlace: realLink,
        tienda: product.tienda || 'eBay',
        crossRefLinks,
      }
    })
  }, [products, enabledCrossRefs])

  const filteredProducts = displayProducts.filter((product) => {
    const titleLower = String(product.titulo || '').toLowerCase()
    // Exclusión estricta de accesorios y protectores de pantalla
    if (/\b(screen protector|screen filter|anti glare|protective film|tempered glass|laptop skin|decal|sticker)\b/.test(titleLower)) {
      return false
    }

    if (
      /\b[im][3579][-\s]?[1-7]\d{3}(?!\d)\w*\b/.test(titleLower) ||
      /\b[1-7]\d{3}(?!\d)(mq|hq|qm|u|m|y|h|t)\b/.test(titleLower) ||
      /\b(1st|2nd|3rd|4th|5th|6th|7th)\s*gen\b|\bgen\s*[1-7]\b/.test(titleLower) ||
      /\b(core\s*2\s*duo|pentium|celeron|atom|athlon)\b/.test(titleLower)
    ) {
      return false
    }


    // ── Descartar publicaciones finalizadas, terminadas o sin stock ($0.00 / ENDED) ──
    if (product.precio <= 0 || product.es_finalizada) {
      return false
    }
    const titleUpper = String(product.titulo || '').toUpperCase()
    if (titleUpper.includes('[ENDED]') || titleUpper.includes('OUT OF STOCK') || titleUpper.includes('ITEM ENDED')) {
      return false
    }
    if (product.es_subasta) {
      const tiempoStr = String(product.tiempo_restante || '').toLowerCase()
      if (tiempoStr === 'terminada' || tiempoStr.includes('terminad')) {
        return false
      }
    }


    // Filtro por Rango de Precio USD (Mínimo y Máximo)
    const minVal = priceMin ? parseFloat(priceMin) : 0
    const maxVal = priceMax ? parseFloat(priceMax) : Infinity
    if (product.precio < minVal || product.precio > maxVal) {
      return false
    }

    // Filtro por query general (Solo para catalogo local; en busqueda en tiempo real el backend ya entrego los resultados filtrados)
    if (!isRealTimeSearch && normalizedQuery) {
      const matchQuery = product.titulo.toLowerCase().includes(normalizedQuery) || (product.marca && product.marca.toLowerCase().includes(normalizedQuery))
      if (!matchQuery) return false
    }


    // Filtro estricto por Marca
    if (brandFilterClean !== 'all') {
      const prodMarca = (product.marca || '').toLowerCase()
      const prodTitulo = (product.titulo || '').toLowerCase()
      if (!prodMarca.includes(brandFilterClean) && !prodTitulo.includes(brandFilterClean)) {
        return false
      }
    }

    // Filtro estricto por Línea de laptop
    if (lineFilterClean) {
      const prodTitulo = (product.titulo || '').toLowerCase()
      const prodModelo = (product.modelo || '').toLowerCase()
      if (!prodTitulo.includes(lineFilterClean) && !prodModelo.includes(lineFilterClean)) {
        return false
      }
    }

    return true
  })


  const categories = [
    { id: 'all', name: 'Todos', icon: <Search size={18} /> },
    { id: 'laptop', name: 'Laptops', icon: <Monitor size={18} /> },
    { id: 'phone', name: 'Telefonos', icon: <Smartphone size={18} /> },
    { id: 'ssd', name: 'Almacenamiento', icon: <HardDrive size={18} /> },
    { id: 'ram', name: 'Memoria RAM', icon: <Cpu size={18} /> },
  ]
  const searchInsightPills = buildSearchInsightPills(searchInsights?.parsed)
  const activeSellerTargetList = (Array.isArray(searchInsights?.parsed?.sellerUsernames) ? searchInsights.parsed.sellerUsernames : [])
    .map((value) => String(value || '').trim())
    .filter(Boolean)
  const activeSellerTargets = new Set(activeSellerTargetList.map((value) => value.toLowerCase()))

  return (
    <div className="app-container">
      <header>
        <div className="logo">
          <span className="gradient-text">eBay AI Finder</span>
        </div>

        <div className="header-actions">
          <div className="header-actions-top">
            <form onSubmit={handleRealTimeSearch} className="search-bar">
              <Search size={20} color="var(--text-muted)" />
              <label htmlFor="searchInput" style={{ display: 'none' }}>Buscar</label>
              <input
                id="searchInput"
                name="search"
                type="text"
                placeholder="Buscar en tiempo real (Ej: ThinkPad E14 open box o restauradas por Dell)..."
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

            {/* ── Toolbar compacto ── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <button onClick={() => { setIsPriceModalOpen(true); setLocalPriceImage(null); }} title="Registrar Precio Local" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <DollarSign size={18} color="var(--success)" />
              </button>
              <button onClick={openLocalPricesList} title="Ver Precios Locales" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Eye size={18} color="var(--accent-primary)" />
              </button>
              <button onClick={openInventory} title="Inventario" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Package size={18} color="var(--accent-primary)" />
              </button>

              <button onClick={openFinanzas} title="Panel de Finanzas" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <BarChart3 size={18} color="var(--success)" />
              </button>
            </div>

            {/* ── Bot status pill ── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', background: 'var(--bg-card)', padding: '0.2rem 0.4rem', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
              <button
                onClick={toggleBotRunning}
                title={botSettings.is_running ? 'Pausar Bot' : 'Iniciar Bot'}
                style={{
                  background: botSettings.is_running ? 'rgba(46,213,115,0.1)' : 'rgba(255,71,87,0.1)',
                  color: botSettings.is_running ? 'var(--success)' : 'var(--danger)',
                  border: `1px solid ${botSettings.is_running ? 'var(--success)' : 'var(--danger)'}`,
                  padding: '0.3rem 0.7rem',
                  borderRadius: '8px',
                  fontWeight: '600',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  fontSize: '0.78rem',
                }}
              >
                <div style={{ width: '7px', height: '7px', borderRadius: '50%', background: botSettings.is_running ? 'var(--success)' : 'var(--danger)', boxShadow: botSettings.is_running ? '0 0 6px var(--success)' : 'none' }} />
                {botSettings.is_running ? 'ON' : 'OFF'}
              </button>
              <span style={{ fontSize: '0.65rem', color: isBotOnline() ? 'var(--success)' : 'var(--text-muted)', padding: '0 0.25rem' }}>
                {isBotOnline() ? '●' : '○'}
              </span>
              <button onClick={openBotConfigModal} title="Config Bot" style={{ color: 'var(--text-main)', padding: '0.3rem', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Settings size={16} color="var(--accent-primary)" />
              </button>
            </div>

            {/* ── Carrito ── */}
            <button
              onClick={() => setIsCartOpen(true)}
              title="Carrito de Recomendaciones"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-main)',
                padding: '0.6rem',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                position: 'relative',
              }}
            >
              <ShoppingCart size={18} />
              {cart.length > 0 && (
                <span
                  style={{
                    position: 'absolute',
                    top: '-5px',
                    right: '-5px',
                    background: 'var(--accent-primary)',
                    color: 'white',
                    fontSize: '0.65rem',
                    width: '18px',
                    height: '18px',
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

          <div className="search-guide-row">
            <span className="search-guide-label">Prueba:</span>
            {SEARCH_EXAMPLES.map((example) => (
              <button key={example} type="button" className="search-guide-chip" onClick={() => applySearchExample(example)}>
                {example}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="main-layout animate-fade-in">
        <aside className="filters-panel glass-panel">
          {/* ── Filtro: Rango de Precios USD ── */}
          <div className="filter-group" style={{ marginBottom: '1.75rem' }}>
            <h3 className="filter-title flex items-center gap-2" style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
              <DollarSign size={16} color="var(--accent-primary)" /> Rango de Precio (USD)
            </h3>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                  Mínimo
                </label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  placeholder="$0"
                  value={priceMin}
                  onChange={(e) => setPriceMin(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.55rem 0.65rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                    fontSize: '0.85rem',
                  }}
                />
              </div>
              <span style={{ color: 'var(--text-muted)', marginTop: '1.2rem', fontSize: '0.85rem' }}>—</span>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                  Máximo
                </label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  placeholder="∞"
                  value={priceMax}
                  onChange={(e) => setPriceMax(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.55rem 0.65rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                    fontSize: '0.85rem',
                  }}
                />
              </div>
            </div>
            {(priceMin || priceMax) && (
              <button
                type="button"
                onClick={() => {
                  setPriceMin('')
                  setPriceMax('')
                }}
                style={{
                  marginTop: '0.5rem',
                  fontSize: '0.72rem',
                  color: 'var(--accent-primary)',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  padding: 0,
                }}
              >
                Limpiar rango
              </button>
            )}
          </div>

          {/* ── Cross-Reference: Buscar similar en otras tiendas ── */}
          <div className="filter-group" style={{ marginBottom: '1.75rem' }}>
            <h3 className="filter-title flex items-center gap-2" style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
              <Store size={16} color="var(--accent-primary)" /> Buscar similar en
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {CROSS_REF_STORES.map((st) => {
                const isSelected = enabledCrossRefs.includes(st.id)
                return (
                  <label
                    key={st.id}
                    onClick={() => toggleCrossRef(st.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.45rem 0.65rem',
                      borderRadius: '8px',
                      background: isSelected ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-dark)',
                      border: `1px solid ${isSelected ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      color: isSelected ? 'white' : 'var(--text-muted)',
                      transition: 'all 0.15s ease',
                      userSelect: 'none',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => {}}
                      style={{ accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
                    />
                    <span>{st.badge} {st.label}</span>
                  </label>
                )
              })}
              {enabledCrossRefs.length < CROSS_REF_STORES.length && (
                <button
                  type="button"
                  onClick={() => setEnabledCrossRefs(CROSS_REF_STORES.map((s) => s.id))}
                  style={{
                    marginTop: '0.25rem',
                    fontSize: '0.72rem',
                    color: 'var(--accent-primary)',
                    background: 'transparent',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  Seleccionar todas ({enabledCrossRefs.length}/{CROSS_REF_STORES.length})
                </button>
              )}
            </div>
          </div>

          {/* ── Filtro Avanzado: Estado del Producto por Casillas ── */}

          <div className="filter-group" style={{ marginBottom: '1.75rem' }}>
            <h3 className="filter-title flex items-center gap-2" style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
              <CheckSquare size={16} color="var(--accent-primary)" /> Estado / Condición
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {CONDITION_OPTIONS.map((c) => {
                const isSelected = selectedConditions.includes(c.id)
                return (
                  <label
                    key={c.id}
                    onClick={() => toggleConditionFilter(c.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.4rem 0.6rem',
                      borderRadius: '8px',
                      background: isSelected ? 'rgba(99, 102, 241, 0.2)' : 'var(--bg-dark)',
                      border: `1px solid ${isSelected ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                      cursor: 'pointer',
                      fontSize: '0.78rem',
                      color: isSelected ? 'white' : 'var(--text-muted)',
                      transition: 'all 0.15s ease',
                      userSelect: 'none',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => {}}
                      style={{ accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
                    />
                    <span>{c.badge} {c.label}</span>
                  </label>
                )
              })}
              {selectedConditions.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedConditions([])}
                  style={{
                    marginTop: '0.25rem',
                    fontSize: '0.72rem',
                    color: 'var(--accent-primary)',
                    background: 'transparent',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  Limpiar casillas ({selectedConditions.length})
                </button>
              )}
            </div>
          </div>

          {/* ── Filtro: Modalidad de Venta & Ordenamiento de Subastas ── */}
          <div className="filter-group" style={{ marginBottom: '1.75rem' }}>
            <h3 className="filter-title flex items-center gap-2" style={{ fontSize: '0.9rem', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
              <Clock size={16} color="var(--accent-primary)" /> Subastas y Venta
            </h3>
            
            {/* Modalidad de Venta */}
            <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '0.85rem' }}>
              {[
                { id: 'ALL', label: 'Todos' },
                { id: 'FIXED_PRICE', label: 'Fijo' },
                { id: 'AUCTION', label: '🔨 Subastas' },
              ].map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setSelectedBuyingOption(opt.id)}
                  style={{
                    flex: 1,
                    padding: '0.45rem 0.2rem',
                    fontSize: '0.75rem',
                    fontWeight: selectedBuyingOption === opt.id ? '600' : '400',
                    borderRadius: '6px',
                    background: selectedBuyingOption === opt.id ? 'var(--accent-primary)' : 'var(--bg-dark)',
                    color: selectedBuyingOption === opt.id ? 'white' : 'var(--text-muted)',
                    border: `1px solid ${selectedBuyingOption === opt.id ? 'var(--accent-primary)' : 'var(--border-color)'}`,
                    cursor: 'pointer',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Orden de Subastas / Resultados */}
            <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.3rem' }}>
              Ordenamiento de búsqueda:
            </label>
            <select
              value={selectedSortOrder}
              onChange={(e) => setSelectedSortOrder(e.target.value)}
              style={{
                width: '100%',
                padding: '0.55rem',
                borderRadius: '8px',
                background: 'var(--bg-dark)',
                border: '1px solid var(--border-color)',
                color: 'white',
                fontSize: '0.8rem',
              }}
            >
              <option value="endingSoonest">⏳ Subastas por terminar pronto</option>
              <option value="newlyListed">⌛ Recién publicadas</option>
              <option value="price">💲 Precio: Menor a Mayor</option>
              <option value="-price">💰 Precio: Mayor a Menor</option>
            </select>
          </div>

          {/* ── Filtro por Marca y Línea ── */}

          <div className="filter-group" style={{ marginBottom: '2rem' }}>
            <h3 className="filter-title flex items-center gap-2">
              <Monitor size={16} /> Marca y Línea (IA)
            </h3>
            <div className="flex-col gap-2 mt-4">
              <select
                value={selectedBrandFilter}
                onChange={(e) => {
                  setSelectedBrandFilter(e.target.value)
                  setSelectedLineFilter('')
                }}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  borderRadius: '8px',
                  background: 'var(--bg-dark)',
                  border: '1px solid var(--border-color)',
                  color: 'white',
                  fontWeight: '500',
                }}
              >
                <option value="all">Todas las marcas</option>
                <option value="acer">Acer (Predator, Nitro...)</option>
                <option value="asus">ASUS (ROG, TUF, ZenBook...)</option>
                <option value="dell">Dell (Alienware, XPS, Latitude...)</option>
                <option value="hp">HP (OMEN, Victus, EliteBook...)</option>
                <option value="lenovo">Lenovo (Legion, ThinkPad, LOQ...)</option>
                <option value="msi">MSI (Raider, Stealth, Katana...)</option>
                <option value="apple">Apple (MacBook Air, Pro)</option>
                <option value="razer">Razer (Blade)</option>
                <option value="samsung">Samsung (Galaxy Book)</option>
                <option value="microsoft">Microsoft (Surface)</option>
              </select>

              <div style={{ position: 'relative', marginTop: '0.5rem' }}>
                <input
                  type="text"
                  placeholder="Línea/Modelo (ej: Predator, Nitro...)"
                  value={selectedLineFilter}
                  onChange={(e) => setSelectedLineFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                  }}
                />
                {isSearchingLines && (
                  <Loader2 size={14} className="animate-spin" style={{ position: 'absolute', right: '10px', top: '12px', color: 'var(--accent-primary)' }} />
                )}

                {/* Sugerencias de Autocompletado IA en Tiempo Real */}
                {lineSuggestions.length > 0 && selectedLineFilter && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '100%',
                      left: 0,
                      right: 0,
                      background: 'var(--bg-dark)',
                      border: '1px solid var(--accent-primary)',
                      borderRadius: '8px',
                      marginTop: '4px',
                      zIndex: 50,
                      maxHeight: '180px',
                      overflowY: 'auto',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                    }}
                  >
                    {lineSuggestions.map((line) => (
                      <div
                        key={line}
                        onClick={() => setSelectedLineFilter(line)}
                        style={{
                          padding: '0.6rem 0.8rem',
                          cursor: 'pointer',
                          fontSize: '0.85rem',
                          color: 'var(--text-main)',
                          borderBottom: '1px solid var(--border-color)',
                          transition: 'background 0.2s',
                        }}
                        onMouseEnter={(e) => (e.target.style.background = 'rgba(99, 102, 241, 0.2)')}
                        onMouseLeave={(e) => (e.target.style.background = 'transparent')}
                      >
                        ✨ {line}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>


          <div className="filter-group">
            <h3 className="filter-title flex items-center gap-2">
              <Filter size={16} /> Categorias
            </h3>
            <div className="flex-col gap-2 mt-4">
              {categories.map((category) => (
                <button
                  key={category.id}
                  onClick={() => handleCategoryChange(category.id)}
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
              {isRealTimeSearch && searchInsights && (
                <div className="search-summary glass-panel animate-fade-in">
                  <div className="search-summary-header">
                    <div>
                      <div className="search-summary-kicker">Busqueda IA activa</div>
                      <div className="search-summary-title">{searchInsights.rawQuery}</div>
                    </div>
                    <button type="button" className="search-summary-reset" onClick={clearRealTimeSearch}>
                      Volver al catalogo
                    </button>
                  </div>

                  {searchInsightPills.length > 0 && (
                    <div className="search-pill-row">
                      {searchInsightPills.map((pill) => (
                        <span key={`${pill.label}-${pill.value}`} className={`search-pill search-pill--${pill.tone || 'neutral'}`}>
                          <span className="search-pill-label">{pill.label}</span>
                          <span>{pill.value}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', color: 'var(--text-muted)' }}>
                <span style={{ fontSize: '0.9rem', fontWeight: '500' }}>
                  {isRealTimeSearch ? `Mostrando ${filteredProducts.length} resultados en tiempo real` : `Mostrando ${filteredProducts.length} resultados`}
                </span>

                <button
                  type="button"
                  onClick={handleRefreshCatalog}
                  disabled={isRefreshingCatalog}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.45rem',
                    background: 'rgba(99, 102, 241, 0.15)',
                    border: '1px solid var(--accent-primary)',
                    color: 'white',
                    padding: '0.45rem 0.85rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    fontWeight: '600',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    boxShadow: '0 2px 8px rgba(99, 102, 241, 0.2)',
                  }}
                >
                  <RefreshCw size={14} className={isRefreshingCatalog ? 'animate-spin' : ''} />
                  {isRefreshingCatalog ? 'Obteniendo ofertas frescas...' : '🔄 Refrescar Ofertas Frescas'}
                </button>
              </div>


              <div className="product-grid">
                {filteredProducts.map((product) => {
                  const scanState = visualScanState[product.id] || EMPTY_SCAN_STATE
                  const visualData = scanState.data
                  const visualTone = getVisualTone(scanState)
                  const showVisualPanel = Boolean(visualData || scanState.error)
                  const isAddedToCart = cartIds.has(product.id)
                  const productImages = getProductImages(product)
                  const storeBadge = getStoreBadge(product.tienda, product.enlace || product.link)
                  const sellerName = String(product.vendedor || product.seller_username || '').trim()

                  const isOfficialSellerMatch = sellerName ? activeSellerTargets.has(sellerName.toLowerCase()) : false


                  return (
                    <div 
                      key={product.id} 
                      className="product-card glass-panel"
                      onClick={() => isSelectingForLocalPrice ? handleSelectProductForLocal(product) : null}
                      style={{ 
                        cursor: isSelectingForLocalPrice ? 'pointer' : 'default', 
                        border: isSelectingForLocalPrice ? '2px solid var(--accent-primary)' : '' 
                      }}
                    >
                      <div 
                        className="product-image-container" 
                        onClick={(e) => {
                          if (!isSelectingForLocalPrice) {
                            e.stopPropagation()
                            openGallery(product, 0)
                          }
                        }}
                        style={{ 
                          pointerEvents: isSelectingForLocalPrice ? 'none' : 'auto',
                          position: 'relative',
                          cursor: 'pointer',
                        }}
                        title="Haz clic para ver las fotos en grande"
                      >
                        {/* ── Badge de Tienda de Origen ── */}
                        <div
                          style={{
                            position: 'absolute',
                            top: '10px',
                            left: '10px',
                            zIndex: 2,
                            background: storeBadge.bg,
                            color: storeBadge.color,
                            padding: '0.25rem 0.65rem',
                            borderRadius: '100px',
                            fontWeight: '700',
                            fontSize: '0.75rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.3rem',
                            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                          }}
                        >
                          <Store size={12} />
                          {storeBadge.name}
                        </div>

                        {/* ── Indicador de fotos disponibles & Collage IA ── */}
                        <div
                          style={{
                            position: 'absolute',
                            bottom: '10px',
                            right: '10px',
                            zIndex: 2,
                            display: 'flex',
                            gap: '0.35rem',
                          }}
                        >
                          {productImages.length >= 2 && (
                            <button
                              type="button"
                              onClick={async (e) => {
                                e.stopPropagation()
                                let collageUrl = product.collage_url || product.analisis_visual?.collage_url
                                if (!collageUrl) {
                                  try {
                                    const buildRes = await api.buildCollage({
                                      imagenes: productImages,
                                      titulo: product.titulo,
                                    })
                                    if (buildRes?.collage_url) {
                                      collageUrl = buildRes.collage_url
                                    } else {
                                      const res = await api.analyzeImage({
                                        imagenes: productImages,
                                        titulo: product.titulo,
                                        seller_notes: product.notas_vendedor || '',
                                        condicion: product.condicion || '',
                                      })
                                      collageUrl = res?.collage_url
                                    }
                                  } catch (err) {
                                    console.error(err)
                                  }
                                }
                                if (collageUrl) {
                                  setActiveCollageModal({ isOpen: true, url: collageUrl, title: product.titulo })
                                } else {
                                  alert('No se pudo generar el collage para este producto.')
                                }
                              }}
                              style={{
                                background: 'rgba(99, 102, 241, 0.85)',
                                backdropFilter: 'blur(4px)',
                                color: '#fff',
                                padding: '0.2rem 0.55rem',
                                borderRadius: '8px',
                                fontWeight: '600',
                                fontSize: '0.72rem',
                                border: 'none',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.3rem',
                              }}
                              title="Ver collage numerado compuesto enviado a Groq Vision"
                            >
                              <Eye size={12} />
                              Collage IA
                            </button>
                          )}
                          <div
                            style={{
                              background: 'rgba(0,0,0,0.75)',
                              backdropFilter: 'blur(4px)',
                              color: '#fff',
                              padding: '0.2rem 0.55rem',
                              borderRadius: '8px',
                              fontWeight: '600',
                              fontSize: '0.72rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.3rem',
                            }}
                          >
                            <Maximize2 size={12} />
                            {productImages.length > 1 ? `${productImages.length} fotos` : 'Ver en grande'}
                          </div>
                        </div>

                        {product.imagen_url || productImages[0] ? (
                          <img src={productImages[0] || product.imagen_url} alt={product.titulo} className="product-image" />
                        ) : (
                          <div className="product-image flex justify-center items-center" style={{ background: '#f3f4f6' }}>
                            <Monitor size={48} color="#9ca3af" />
                          </div>
                        )}
                      </div>

                      <div className="product-content">
                        <h3 className="product-title">{product.titulo}</h3>
                        <div className="product-price">${product.precio?.toFixed(2)}</div>

                        <div className="product-meta" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                          <span 
                            className="badge accent" 
                            style={{ background: storeBadge.bg, color: storeBadge.color, fontWeight: 'bold' }}
                          >
                            {storeBadge.name}
                          </span>
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


                        {sellerName && (
                          <div className="product-seller-row">
                            <span className="product-seller-kicker">{isOfficialSellerMatch ? 'Tienda oficial' : 'Seller'}</span>
                            <span className={`product-seller-name${isOfficialSellerMatch ? ' product-seller-name--official' : ''}`}>
                              {sellerName}
                            </span>
                          </div>
                        )}

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

                        {/* ── Fila de Acciones Premium ── */}
                        <div style={{ display: 'flex', gap: '0.4rem', marginTop: '1rem', flexWrap: 'wrap' }}>
                          <a
                            href={product.enlace}
                            target="_blank"
                            rel="noreferrer"
                            style={{ 
                              flex: '1 1 auto',
                              minWidth: '110px',
                              padding: '0.55rem 0.75rem', 
                              fontSize: '0.82rem',
                              background: `linear-gradient(135deg, ${storeBadge.bg}, ${storeBadge.bg}DD)`,
                              color: storeBadge.color,
                              fontWeight: '700',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '0.35rem',
                              borderRadius: '10px',
                              textDecoration: 'none',
                              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                              transition: 'transform 0.15s ease, boxShadow 0.15s ease',
                            }}
                          >
                            <Store size={15} />
                            Ver en {storeBadge.name}
                          </a>

                          <button
                            onClick={() => toggleCartItem(product)}
                            style={{
                              flex: '1 1 auto',
                              minWidth: '110px',
                              background: isAddedToCart 
                                ? 'linear-gradient(135deg, #10b981, #059669)' 
                                : 'linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03))',
                              border: `1px solid ${isAddedToCart ? '#10b981' : 'var(--border-color)'}`,
                              color: 'white',
                              padding: '0.55rem 0.75rem',
                              borderRadius: '10px',
                              fontWeight: '600',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '0.4rem',
                              fontSize: '0.82rem',
                              cursor: 'pointer',
                              backdropFilter: 'blur(6px)',
                              boxShadow: isAddedToCart ? '0 4px 12px rgba(16,185,129,0.3)' : 'none',
                              transition: 'all 0.15s ease',
                            }}
                          >
                            {isAddedToCart ? (
                              <>
                                <Check size={15} /> Agregado
                              </>
                            ) : (
                              <>
                                <Plus size={15} /> Recomendar
                              </>
                            )}
                          </button>

                          <button
                            onClick={() => handleOpenEquivocadoModal(product)}
                            title="Marcar resultado equivocado (Feedback IA)"
                            style={{
                              background: 'rgba(239, 68, 68, 0.12)',
                              border: '1px solid rgba(239, 68, 68, 0.4)',
                              color: '#ef4444',
                              padding: '0.55rem 0.65rem',
                              borderRadius: '10px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.82rem',
                              fontWeight: '600',
                              cursor: 'pointer',
                              gap: '0.3rem',
                              transition: 'all 0.15s ease',
                            }}
                          >
                            <X size={15} /> Equivocado
                          </button>
                        </div>

                        {/* ── Cross-reference: buscar similar en otras tiendas ── */}
                        {product.crossRefLinks && product.crossRefLinks.length > 0 && (
                          <div style={{ display: 'flex', gap: '0.3rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                            {product.crossRefLinks.map((ref) => (
                              <a
                                key={ref.id}
                                href={ref.url}
                                target="_blank"
                                rel="noreferrer"
                                title={`Buscar similar en ${ref.label}`}
                                style={{
                                  flex: '1 1 0',
                                  minWidth: '0',
                                  padding: '0.35rem 0.4rem',
                                  fontSize: '0.68rem',
                                  background: `${ref.badge.bg}22`,
                                  border: `1px solid ${ref.badge.bg}55`,
                                  color: ref.badge.bg,
                                  fontWeight: '600',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '0.2rem',
                                  borderRadius: '8px',
                                  textDecoration: 'none',
                                  transition: 'all 0.15s ease',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                }}
                              >
                                <Search size={11} />
                                {ref.label}
                              </a>
                            ))}
                          </div>
                        )}

                      </div>
                    </div>

                  )
                })}

                {filteredProducts.length === 0 && (
                  <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                    <div className="empty-state-title">No se encontraron productos</div>
                    <div className="empty-state-copy">
                      {activeSellerTargetList.length > 0
                        ? `La busqueda se restringio al seller oficial ${activeSellerTargetList.join(', ')}. Si esa tienda no tiene stock exacto ahora, es normal ver cero resultados.`
                        : 'Intenta hacer una busqueda en tiempo real arriba, quitar parte del modelo o usar una condicion menos estricta.'}
                    </div>
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
            <button onClick={() => { setIsPriceModalOpen(false); setEditingLocalPriceId(null); setLocalPriceForm({ titulo: '', tipo: 'laptop', precio_usd: '', condicion: 'Usado' }); }} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}>
              <X />
            </button>

            <h2 style={{ marginBottom: '1.5rem', color: 'var(--accent-primary)' }}>
              {editingLocalPriceId ? '✏️ Editar Precio' : '💲 Registrar Precio en Nicaragua'}
            </h2>

            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Ensena a la IA a cuanto se vende un producto en el mercado local. La IA usara esto como referencia para calcular margenes en tus futuras busquedas.
            </p>

            <form onSubmit={submitLocalPrice} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <span style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                  Sube captura de Marketplace (Opcional - Extrae Titulo con IA)
                </span>
                <input type="file" name="file-upload" accept="image/*" onChange={handleImageUpload} style={{ marginBottom: '1rem', display: 'none' }} id="file-upload" />
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
                  <label htmlFor="file-upload" style={{ background: 'var(--bg-card)', padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', border: '1px solid var(--border-color)', flex: 1, textAlign: 'center' }}>
                    Subir desde PC
                  </label>
                  <button 
                    type="button" 
                    onClick={() => { setIsPriceModalOpen(false); setIsSelectingForLocalPrice(true); }}
                    style={{ background: 'var(--accent-primary)', color: '#fff', padding: '0.5rem 1rem', borderRadius: '8px', border: 'none', cursor: 'pointer', flex: 1 }}
                  >
                    Elegir publicacion de eBay
                  </button>
                </div>
                
                {localPriceImage && (
                  <div style={{ marginBottom: '1rem' }}>
                    <img src={localPriceImage} alt="Preview" style={{ maxWidth: '100px', borderRadius: '8px' }} />
                  </div>
                )}
                {isParsingImage && <p style={{ color: 'var(--accent-primary)', fontSize: '0.9rem' }}>Extrayendo y limpiando titulo con IA Vision...</p>}
              </div>

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

      {isLocalPricesListOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.7)',
            zIndex: 2000,
            display: 'flex', justifyContent: 'center', alignItems: 'center',
          }}
        >
          <div className="glass-panel animate-fade-in" style={{ width: '90%', maxWidth: '700px', maxHeight: '80vh', padding: '2rem', position: 'relative', overflowY: 'auto' }}>
            <button onClick={() => setIsLocalPricesListOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}>
              <X />
            </button>
            <h2 style={{ marginBottom: '1.5rem', color: 'var(--accent-primary)' }}>Mis Precios Registrados</h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {localPricesList.length === 0 ? (
                <p>No tienes precios locales registrados aún.</p>
              ) : (
                localPricesList.map(item => (
                  <div key={item.id} style={{ display: 'flex', gap: '1rem', background: 'var(--bg-dark)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                    {item.imagen_url ? (
                      <img src={item.imagen_url} alt="" style={{ width: '80px', height: '80px', objectFit: 'cover', borderRadius: '4px' }} />
                    ) : (
                      <div style={{ width: '80px', height: '80px', background: 'var(--border-color)', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem' }}>Sin foto</div>
                    )}
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 'bold' }}>{item.titulo_marketplace}</div>
                      <div style={{ color: 'var(--success)', fontWeight: 'bold', fontSize: '1.1rem', marginTop: '0.25rem' }}>${item.precio_nic_usd}</div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>{item.tipo} | {item.condicion}</div>
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                        <button onClick={() => handleEditLocalPrice(item)} style={{ background: 'var(--bg-lighter)', color: 'var(--text-main)', border: '1px solid var(--border-color)', padding: '0.25rem 0.75rem', borderRadius: '4px', fontSize: '0.8rem', cursor: 'pointer' }}>
                          Editar
                        </button>
                        <button onClick={() => handleDeleteLocalPrice(item.id)} style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '0.25rem 0.75rem', borderRadius: '4px', fontSize: '0.8rem', cursor: 'pointer' }}>
                          Eliminar
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {isBotConfigModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.75)',
            backdropFilter: 'blur(4px)',
            zIndex: 2000,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            padding: '1rem',
          }}
        >
          <div
            className="glass-panel animate-fade-in"
            style={{
              width: '100%',
              maxWidth: '550px',
              maxHeight: '85vh',
              padding: '1.75rem',
              position: 'relative',
              overflowY: 'auto',
              borderRadius: '16px',
            }}
          >
            <button
              onClick={() => setIsBotConfigModalOpen(false)}
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-muted)',
                borderRadius: '50%',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <X size={18} />
            </button>

            {/* Header con Status Pill */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Settings size={22} color="var(--accent-primary)" />
                <h2 style={{ fontSize: '1.25rem', color: 'var(--text-main)', margin: 0, fontWeight: '700' }}>
                  Configuración del Bot
                </h2>
              </div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.25rem 0.75rem',
                  borderRadius: '100px',
                  fontSize: '0.78rem',
                  fontWeight: '600',
                  background: botIsRunning ? 'rgba(46, 213, 115, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                  color: botIsRunning ? 'var(--success)' : '#ef4444',
                  border: `1px solid ${botIsRunning ? 'rgba(46, 213, 115, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                  cursor: 'pointer',
                }}
                onClick={() => setBotIsRunning(!botIsRunning)}
                title="Haz clic para cambiar estado local del bot"
              >
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: botIsRunning ? 'var(--success)' : '#ef4444',
                    boxShadow: botIsRunning ? '0 0 8px var(--success)' : 'none',
                  }}
                />
                {botIsRunning ? 'Activo' : 'Pausado'}
              </div>
            </div>

            <form onSubmit={saveBotConfig} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Presupuesto Máximo */}
              <div style={{ background: 'var(--bg-dark)', padding: '1rem', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
                <label htmlFor="bot_max_precio" style={{ display: 'block', marginBottom: '0.4rem', fontWeight: '600', fontSize: '0.85rem' }}>
                  Presupuesto Máximo en Subastas & Compras (USD)
                </label>
                <input
                  id="bot_max_precio"
                  name="bot_max_precio"
                  required
                  type="number"
                  min="1"
                  step="0.01"
                  placeholder="Ej: 200"
                  value={botMaxPrecio}
                  onChange={(event) => setBotMaxPrecio(event.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.65rem 0.75rem',
                    borderRadius: '8px',
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                    fontSize: '0.95rem',
                    fontWeight: 'bold',
                  }}
                />
              </div>

              {/* Filtro por Procesador (Pills Coloreados) */}
              <div>
                <h3 style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Filtro por Procesadores
                </h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                  {[
                    { id: 'Intel Core i3', color: '#60a5fa' },
                    { id: 'Intel Core i5', color: '#3b82f6' },
                    { id: 'Intel Core i7', color: '#2563eb' },
                    { id: 'Intel Core i9', color: '#1d4ed8' },
                    { id: 'Ryzen 3', color: '#f87171' },
                    { id: 'Ryzen 5', color: '#ef4444' },
                    { id: 'Ryzen 7', color: '#dc2626' },
                    { id: 'Ryzen 9', color: '#b91c1c' },
                  ].map((cpu) => {
                    const isSelected = botFilters.categorias_activas.includes(cpu.id)
                    return (
                      <span
                        key={cpu.id}
                        onClick={() => {
                          const activas = isSelected
                            ? botFilters.categorias_activas.filter((c) => c !== cpu.id)
                            : [...botFilters.categorias_activas, cpu.id]
                          setBotFilters({ ...botFilters, categorias_activas: activas })
                        }}
                        style={{
                          padding: '0.35rem 0.7rem',
                          borderRadius: '100px',
                          fontSize: '0.78rem',
                          fontWeight: '600',
                          cursor: 'pointer',
                          userSelect: 'none',
                          transition: 'all 0.15s ease',
                          background: isSelected ? `${cpu.color}22` : 'var(--bg-dark)',
                          color: isSelected ? cpu.color : 'var(--text-muted)',
                          border: `1px solid ${isSelected ? `${cpu.color}66` : 'var(--border-color)'}`,
                        }}
                      >
                        {isSelected ? '✓ ' : '+ '}
                        {cpu.id.replace('Intel Core ', '')}
                      </span>
                    )
                  })}
                </div>
              </div>

              {/* Filtro por Condiciones */}
              <div>
                <h3 style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginBottom: '0.6rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Condición Física Aceptada
                </h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                  {[
                    'New',
                    'Open box',
                    'Certified Refurbished',
                    'Excellent Refurbished',
                    'Very Good Refurbished',
                    'Good Refurbished',
                    'Used',
                  ].map((est) => {
                    const isSelected = botFilters.estados_activos.includes(est)
                    return (
                      <span
                        key={est}
                        onClick={() => {
                          const activas = isSelected
                            ? botFilters.estados_activos.filter((c) => c !== est)
                            : [...botFilters.estados_activos, est]
                          setBotFilters({ ...botFilters, estados_activos: activas })
                        }}
                        style={{
                          padding: '0.35rem 0.7rem',
                          borderRadius: '100px',
                          fontSize: '0.75rem',
                          fontWeight: '500',
                          cursor: 'pointer',
                          userSelect: 'none',
                          transition: 'all 0.15s ease',
                          background: isSelected ? 'rgba(99, 102, 241, 0.15)' : 'var(--bg-dark)',
                          color: isSelected ? 'var(--accent-primary)' : 'var(--text-muted)',
                          border: `1px solid ${isSelected ? 'rgba(99, 102, 241, 0.4)' : 'var(--border-color)'}`,
                        }}
                      >
                        {isSelected ? '✓ ' : '+ '}
                        {est.replace(' Refurbished', ' Refurb')}
                      </span>
                    )
                  })}
                </div>
              </div>

              <button
                disabled={isSavingBotConfig}
                type="submit"
                className="buy-btn"
                style={{
                  marginTop: '0.5rem',
                  padding: '0.75rem',
                  borderRadius: '10px',
                  fontSize: '0.9rem',
                  fontWeight: '600',
                  opacity: isSavingBotConfig ? 0.7 : 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                }}
              >
                {isSavingBotConfig && <Loader2 size={16} className="animate-spin" />}
                {isSavingBotConfig ? 'Guardando cambios...' : 'Guardar y Aplicar Configuración'}
              </button>
            </form>

            {/* Visor de Logs del Bot */}
            <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <h3 style={{ fontSize: '0.85rem', color: 'var(--text-main)', margin: 0, fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Clock size={14} color="var(--accent-primary)" /> Registros del Bot (Logs)
                </h3>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const d = await api.getBotLogs()
                      setBotLogs(d.logs || 'Sin logs.')
                    } catch (e) {
                      console.error(e)
                    }
                  }}
                  style={{
                    background: 'rgba(99,102,241,0.15)',
                    color: 'var(--accent-primary)',
                    border: '1px solid rgba(99,102,241,0.3)',
                    padding: '0.2rem 0.6rem',
                    borderRadius: '6px',
                    fontSize: '0.7rem',
                    cursor: 'pointer',
                  }}
                >
                  Refrescar
                </button>
              </div>
              <pre
                ref={botLogsRef}
                style={{
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  padding: '0.75rem',
                  fontSize: '0.72rem',
                  color: '#a1a1aa',
                  maxHeight: '180px',
                  overflowY: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  fontFamily: 'monospace',
                  lineHeight: '1.4',
                }}
              >
                {botLogs || 'Sin registros acumulados en el ciclo actual.'}
              </pre>
            </div>
          </div>
        </div>
      )}



      {isSelectingForLocalPrice && (
        <div style={{
          position: 'fixed', bottom: '2rem', left: '50%', transform: 'translateX(-50%)',
          background: 'var(--accent-primary)', color: '#fff',
          padding: '1rem 2rem', borderRadius: '100px', zIndex: 3000,
          boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', gap: '1rem',
          animation: 'fadeIn 0.3s ease',
        }}>
          <span style={{ fontWeight: 'bold' }}>Toca una laptop de los resultados para extraer su imagen y titulo...</span>
          <button
            onClick={() => { setIsSelectingForLocalPrice(false); setIsPriceModalOpen(true); }}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff', padding: '0.5rem 1rem', borderRadius: '50px', cursor: 'pointer' }}
          >
            Cancelar
          </button>
        </div>
      )}

      {/* ═══ INVENTARIO MODAL ═══ */}
      {isInventoryOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', zIndex: 2000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div className="glass-panel animate-fade-in" style={{ width: '95%', maxWidth: '900px', maxHeight: '85vh', padding: '2rem', position: 'relative', overflowY: 'auto' }}>
            <button onClick={() => setIsInventoryOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}><X /></button>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
              <h2 className="flex items-center gap-2" style={{ color: 'var(--accent-primary)' }}><Package size={24} /> Inventario</h2>
              <button onClick={() => { setIsInventoryFormOpen(true); setEditingInventoryId(null); setInventoryForm({ titulo: '', tipo: 'laptop', costo_total_usd: '', precio_venta_esperado: '', tracking_number: '', notas: '' }); }} style={{ background: 'var(--accent-primary)', color: '#fff', padding: '0.5rem 1rem', borderRadius: '8px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><Plus size={16} /> Nueva Compra</button>
            </div>

            {/* Stats bar */}
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
              {[
                { label: 'En tránsito', count: inventoryItems.filter(i => i.estado === 'en_transito').length, color: '#f59e0b' },
                { label: 'En stock', count: inventoryItems.filter(i => i.estado === 'en_stock').length, color: 'var(--accent-primary)' },
                { label: 'Vendidos', count: inventoryItems.filter(i => i.estado === 'vendido').length, color: 'var(--success)' },
              ].map(s => (
                <div key={s.label} style={{ background: 'var(--bg-dark)', padding: '0.75rem 1.25rem', borderRadius: '8px', border: `1px solid ${s.color}33`, flex: 1, minWidth: '120px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: s.color }}>{s.count}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{s.label}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {inventoryItems.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>No hay items en tu inventario aún. ¡Registra tu primera compra!</p>
              ) : inventoryItems.map(item => {
                const estadoColor = item.estado === 'vendido' ? 'var(--success)' : item.estado === 'en_stock' ? 'var(--accent-primary)' : '#f59e0b'
                const estadoLabel = item.estado === 'vendido' ? '✅ Vendido' : item.estado === 'en_stock' ? '📦 En stock' : '✈️ En tránsito'
                const tr = item.tracking_number ? trackingResults[item.tracking_number] : null
                return (
                  <div key={item.id} style={{ background: 'var(--bg-dark)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ flex: 1, minWidth: '200px' }}>
                        <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>{item.titulo}</div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                          Costo: <strong style={{ color: 'var(--danger)' }}>${item.costo_total_usd}</strong>
                          {item.precio_venta_esperado && <> · Venta esperada: <strong>${item.precio_venta_esperado}</strong></>}
                          {item.precio_venta_real && <> · Vendido a: <strong style={{ color: 'var(--success)' }}>${item.precio_venta_real}</strong></>}
                        </div>
                      </div>
                      <span style={{ padding: '0.25rem 0.75rem', borderRadius: '100px', fontSize: '0.8rem', fontWeight: '600', background: `${estadoColor}22`, color: estadoColor, border: `1px solid ${estadoColor}44` }}>{estadoLabel}</span>
                      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                        {item.estado === 'en_transito' && <button onClick={() => updateInventoryStatus(item.id, 'en_stock')} style={{ background: 'rgba(99,102,241,0.15)', color: 'var(--accent-primary)', border: '1px solid rgba(99,102,241,0.3)', padding: '0.3rem 0.6rem', borderRadius: '6px', fontSize: '0.78rem' }}>Recibido</button>}
                        {item.estado === 'en_stock' && <button onClick={() => { const p = prompt('¿A cuánto lo vendiste? (USD)'); if (p) updateInventoryStatus(item.id, 'vendido', parseFloat(p)); }} style={{ background: 'rgba(46,213,115,0.15)', color: 'var(--success)', border: '1px solid rgba(46,213,115,0.3)', padding: '0.3rem 0.6rem', borderRadius: '6px', fontSize: '0.78rem' }}>Vendido</button>}
                        <button onClick={() => deleteInventoryItem(item.id)} style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', padding: '0.3rem 0.6rem', borderRadius: '6px', fontSize: '0.78rem' }}>Eliminar</button>
                      </div>
                    </div>
                    
                    {/* Tracking real */}
                    {item.tracking_number && (
                      <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            📍 <code style={{ background: 'var(--bg-dark)', padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: '0.8rem' }}>{item.tracking_number}</code>
                            {tr && !tr.loading && tr.name && <span style={{ fontSize: '0.75rem', color: 'var(--accent-primary)' }}>({tr.name})</span>}
                          </div>
                          <div style={{ display: 'flex', gap: '0.4rem' }}>
                            <button onClick={() => trackPackage(item.tracking_number)} disabled={tr?.loading} style={{ background: 'rgba(55,66,250,0.15)', color: '#3742fa', border: '1px solid rgba(55,66,250,0.3)', padding: '0.25rem 0.6rem', borderRadius: '6px', fontSize: '0.75rem', fontWeight: '600' }}>
                              {tr?.loading ? '⏳ Consultando...' : '🔍 Rastrear'}
                            </button>
                            {tr && tr.tracking_url && (
                              <a href={tr.tracking_url} target="_blank" rel="noopener noreferrer" style={{ background: 'rgba(99,102,241,0.15)', color: 'var(--accent-primary)', border: '1px solid rgba(99,102,241,0.3)', padding: '0.25rem 0.6rem', borderRadius: '6px', fontSize: '0.75rem', textDecoration: 'none', fontWeight: '600' }}>
                                🌐 Ver en {tr.name || 'web'}
                              </a>
                            )}
                          </div>
                        </div>

                        {/* Resultado del tracking */}
                        {tr && !tr.loading && tr.status_text && (
                          <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                            <span style={{ padding: '0.2rem 0.6rem', borderRadius: '100px', background: `${tr.status_display?.color || '#747d8c'}22`, color: tr.status_display?.color || '#747d8c', fontWeight: '600', fontSize: '0.8rem', border: `1px solid ${tr.status_display?.color || '#747d8c'}44` }}>
                              {tr.status_display?.label || tr.status_text}
                            </span>
                            {tr.location && <span style={{ color: 'var(--text-muted)' }}>📍 {tr.location}</span>}
                            {tr.last_update && <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>({tr.last_update})</span>}
                          </div>
                        )}
                        {tr && !tr.loading && tr.error && (
                          <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--danger)' }}>Error consultando: {tr.error}</div>
                        )}
                        {tr && !tr.loading && !tr.status_text && !tr.error && tr.universal_url && (
                          <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                            No se pudo obtener estado automático. <a href={tr.universal_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-primary)' }}>Consultar en 17track →</a>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ═══ INVENTARIO FORM MODAL ═══ */}
      {isInventoryFormOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.8)', zIndex: 2100, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div className="glass-panel animate-fade-in" style={{ width: '90%', maxWidth: '500px', padding: '2rem', position: 'relative' }}>
            <button onClick={() => setIsInventoryFormOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}><X /></button>
            <h2 style={{ marginBottom: '1.5rem', color: 'var(--accent-primary)' }}>{editingInventoryId ? 'Editar Compra' : 'Registrar Compra'}</h2>
            <form onSubmit={submitInventoryItem} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <input required placeholder="Título (ej: ThinkPad E14 Gen 3)" value={inventoryForm.titulo} onChange={e => setInventoryForm(f => ({ ...f, titulo: e.target.value }))} style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white', width: '100%' }} />
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input required type="number" step="0.01" placeholder="Costo total USD" value={inventoryForm.costo_total_usd} onChange={e => setInventoryForm(f => ({ ...f, costo_total_usd: e.target.value }))} style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white', flex: 1 }} />
                <input type="number" step="0.01" placeholder="Venta esperada USD" value={inventoryForm.precio_venta_esperado} onChange={e => setInventoryForm(f => ({ ...f, precio_venta_esperado: e.target.value }))} style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white', flex: 1 }} />
              </div>
              <input placeholder="Tracking number (opcional)" value={inventoryForm.tracking_number} onChange={e => setInventoryForm(f => ({ ...f, tracking_number: e.target.value }))} style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white', width: '100%' }} />
              <textarea placeholder="Notas (opcional)" value={inventoryForm.notas} onChange={e => setInventoryForm(f => ({ ...f, notas: e.target.value }))} rows={2} style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--bg-dark)', border: '1px solid var(--border-color)', color: 'white', width: '100%', resize: 'vertical' }} />
              <button type="submit" className="buy-btn" style={{ marginTop: '0.5rem' }}>{editingInventoryId ? 'Guardar Cambios' : 'Registrar Compra'}</button>
            </form>
          </div>
        </div>
      )}

      {/* ═══ FINANZAS MODAL ═══ */}
      {isFinanzasOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', zIndex: 2000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div className="glass-panel animate-fade-in" style={{ width: '95%', maxWidth: '800px', maxHeight: '85vh', padding: '2rem', position: 'relative', overflowY: 'auto' }}>
            <button onClick={() => setIsFinanzasOpen(false)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent' }}><X /></button>
            <h2 className="flex items-center gap-2" style={{ marginBottom: '1.5rem', color: 'var(--success)' }}><BarChart3 size={24} /> Panel de Finanzas</h2>

            {!finanzas ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Cargando datos financieros...</p>
            ) : (
              <>
                {/* KPIs */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                  <div style={{ background: 'var(--bg-dark)', padding: '1.25rem', borderRadius: '12px', border: '1px solid rgba(239,68,68,0.2)', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Total Invertido</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#ef4444' }}>${finanzas.total_invertido}</div>
                  </div>
                  <div style={{ background: 'var(--bg-dark)', padding: '1.25rem', borderRadius: '12px', border: '1px solid rgba(46,213,115,0.2)', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Total Vendido</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--success)' }}>${finanzas.total_vendido}</div>
                  </div>
                  <div style={{ background: 'var(--bg-dark)', padding: '1.25rem', borderRadius: '12px', border: `1px solid ${finanzas.ganancia_neta >= 0 ? 'rgba(46,213,115,0.2)' : 'rgba(239,68,68,0.2)'}`, textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Ganancia Neta</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: finanzas.ganancia_neta >= 0 ? 'var(--success)' : '#ef4444' }}>${finanzas.ganancia_neta}</div>
                  </div>
                  <div style={{ background: 'var(--bg-dark)', padding: '1.25rem', borderRadius: '12px', border: '1px solid rgba(99,102,241,0.2)', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>ROI Global</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--accent-primary)' }}>{finanzas.roi_global}%</div>
                  </div>
                </div>

                {/* Status counts */}
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: '100px', textAlign: 'center', padding: '0.75rem', borderRadius: '8px', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)' }}>
                    <div style={{ fontWeight: 'bold', color: '#f59e0b' }}>{finanzas.en_transito}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>En tránsito</div>
                  </div>
                  <div style={{ flex: 1, minWidth: '100px', textAlign: 'center', padding: '0.75rem', borderRadius: '8px', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)' }}>
                    <div style={{ fontWeight: 'bold', color: 'var(--accent-primary)' }}>{finanzas.en_stock}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>En stock</div>
                  </div>
                  <div style={{ flex: 1, minWidth: '100px', textAlign: 'center', padding: '0.75rem', borderRadius: '8px', background: 'rgba(46,213,115,0.1)', border: '1px solid rgba(46,213,115,0.2)' }}>
                    <div style={{ fontWeight: 'bold', color: 'var(--success)' }}>{finanzas.vendidos}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Vendidos</div>
                  </div>
                </div>

                {/* Top ventas */}
                {finanzas.top_ventas && finanzas.top_ventas.length > 0 && (
                  <div>
                    <h3 className="flex items-center gap-2" style={{ marginBottom: '1rem', color: 'var(--text-main)' }}><TrendingUp size={18} /> Top Ventas Más Rentables</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {finanzas.top_ventas.map((v, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', background: 'var(--bg-dark)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                          <span style={{ flex: 1, fontWeight: '500' }}>{v.titulo}</span>
                          <span style={{ color: 'var(--success)', fontWeight: 'bold', marginLeft: '1rem' }}>+${v.ganancia} ({v.roi}%)</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ═══ EQUIVOCADO ML FEEDBACK MODAL ═══ */}

      {/* ═══ EQUIVOCADO ML FEEDBACK VISUAL ANNOTATION MODAL ═══ */}
      {isEquivocadoModalOpen && selectedEquivocadoProduct && (
        <div className="ml-modal-overlay">
          <div className="ml-modal animate-fade-in">
            <button 
              onClick={() => setIsEquivocadoModalOpen(false)} 
              style={{ position: 'absolute', top: '1.25rem', right: '1.25rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            >
              <X size={22} />
            </button>

            <h2 style={{ marginBottom: '0.4rem', color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '1.25rem' }}>
              <AlertTriangle size={24} /> Reportar Feedback para IA (Anotación Visual)
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Selecciona las fotos con problemas, encierra o señala los defectos (bisagras rotas, repuestos, pantallas con líneas) y añade etiquetas para reentrenar el modelo de IA.
            </p>

            {/* Info producto */}
            <div style={{ padding: '0.75rem 1rem', background: 'rgba(0,0,0,0.4)', borderRadius: '10px', border: '1px solid var(--border-color)', marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Producto analizado:</div>
                <div style={{ fontWeight: '600', color: 'var(--text-main)', fontSize: '0.9rem' }}>{selectedEquivocadoProduct.titulo}</div>
              </div>
              <div style={{ fontWeight: '700', color: 'var(--success)', fontSize: '1rem' }}>${selectedEquivocadoProduct.precio}</div>
            </div>

            <form onSubmit={handleSubmitEquivocado}>
              {/* Paso 1: Selección de fotos del producto */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: '600', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>1. Selecciona la(s) foto(s) con fallas o irrelevantes:</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {isLoadingEquivocadoPhotos ? 'Cargando fotos HD...' : `${equivocadoPhotos.length} foto(s) disponible(s)`}
                  </span>
                </label>

                <div className="ml-photo-grid">
                  {equivocadoPhotos.map((url, idx) => {
                    const isSelected = selectedPhotoUrls.includes(url)
                    const isAnnotating = activeAnnotatingPhoto === url
                    return (
                      <div
                        key={idx}
                        className={`ml-photo-thumb ${isSelected ? 'selected' : ''} ${isAnnotating ? 'annotating' : ''}`}
                        onClick={() => togglePhotoSelection(url)}
                      >
                        <img src={url} alt={`Preview ${idx}`} />
                        <div className="ml-photo-check">
                          {isSelected && <Check size={14} color="white" />}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Paso 2: Canvas de anotación para la foto activa */}
              {activeAnnotatingPhoto && selectedPhotoUrls.includes(activeAnnotatingPhoto) && (
                <div style={{ padding: '1rem', background: 'rgba(0,0,0,0.3)', borderRadius: '14px', border: '1px solid rgba(99,102,241,0.2)', marginBottom: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Pencil size={16} /> Señalar defectos en foto activa:
                    </div>
                    <button
                      type="button"
                      onClick={() => handleUndoShape(activeAnnotatingPhoto)}
                      className="ml-tool-btn"
                      title="Deshacer última marca"
                    >
                      <Undo2 size={14} /> Deshacer marca
                    </button>
                  </div>

                  {/* Toolbar de herramientas */}
                  <div className="ml-toolbar">
                    <button
                      type="button"
                      className={`ml-tool-btn ${drawTool === 'circle' ? 'active' : ''}`}
                      onClick={() => setDrawTool('circle')}
                    >
                      <Circle size={14} /> Círculo
                    </button>
                    <button
                      type="button"
                      className={`ml-tool-btn ${drawTool === 'square' ? 'active' : ''}`}
                      onClick={() => setDrawTool('square')}
                    >
                      <Square size={14} /> Cuadro
                    </button>
                    <button
                      type="button"
                      className={`ml-tool-btn ${drawTool === 'free' ? 'active' : ''}`}
                      onClick={() => setDrawTool('free')}
                    >
                      <Pencil size={14} /> Lápiz Libre
                    </button>

                    <div className="ml-tool-sep" />

                    {['#ef4444', '#f59e0b', '#10b981', '#6366f1'].map(c => (
                      <div
                        key={c}
                        className={`ml-color-swatch ${drawColor === c ? 'active' : ''}`}
                        style={{ background: c }}
                        onClick={() => setDrawColor(c)}
                      />
                    ))}

                    <div className="ml-tool-sep" />

                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Grosor:</span>
                    <input
                      type="range"
                      min="2"
                      max="12"
                      value={drawStrokeWidth}
                      onChange={(e) => setDrawStrokeWidth(parseInt(e.target.value))}
                      className="ml-stroke-slider"
                    />
                  </div>

                  {/* Canvas interactivo */}
                  <AnnotationCanvas
                    imageUrl={activeAnnotatingPhoto}
                    shapes={annotations[activeAnnotatingPhoto]?.shapes || []}
                    onAddShape={(shape) => handleAddShapeToPhoto(activeAnnotatingPhoto, shape)}
                    tool={drawTool}
                    color={drawColor}
                    strokeWidth={drawStrokeWidth}
                  />

                  {/* Nota específica por foto */}
                  <textarea
                    placeholder="Detalle o justificación específica para esta foto (ej: Bisagra rota en esquina derecha, pantalla manchada)..."
                    value={annotations[activeAnnotatingPhoto]?.note || ''}
                    onChange={(e) => handlePhotoNoteChange(activeAnnotatingPhoto, e.target.value)}
                    className="ml-photo-note"
                    rows={2}
                  />
                </div>
              )}

              {/* Paso 3: Tags Rápidos de Categorización */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: '600', display: 'block', marginBottom: '0.4rem' }}>
                  2. Tipo de problema (Tags Rápidos):
                </label>
                <div className="ml-tags-row">
                  {[
                    'Pieza / Repuesto',
                    'Cargador / Accesorio',
                    'Daño Físico / Golpe',
                    'Pantalla Rota / Líneas',
                    'Procesador Antiguo (Generación vieja)',
                    'Sin Batería',
                    'No es Laptop',
                    'Anuncio Engañoso / Falso',
                    'Falta Teclado / Pieza'
                  ].map(tag => {
                    const isSelected = equivocadoTags.includes(tag)
                    return (
                      <span
                        key={tag}
                        className={`ml-tag ${isSelected ? 'active' : ''}`}
                        onClick={() => toggleEquivocadoTag(tag)}
                      >
                        {isSelected ? '✓ ' : '+ '}{tag}
                      </span>
                    )
                  })}
                </div>
              </div>

              {/* Paso 4: Motivo general */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-main)', fontWeight: '600', display: 'block', marginBottom: '0.4rem' }}>
                  3. Comentarios adicionales para la IA (opcional):
                </label>
                <textarea
                  placeholder="Explica cualquier otro detalle relevante para ayudar a entrenar la IA..."
                  value={equivocadoMotivo}
                  onChange={(e) => setEquivocadoMotivo(e.target.value)}
                  rows={2}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '8px',
                    background: 'var(--bg-dark)',
                    border: '1px solid var(--border-color)',
                    color: 'white',
                    resize: 'vertical',
                    fontFamily: 'inherit',
                    fontSize: '0.82rem'
                  }}
                />
              </div>

              {/* Botón de envío */}
              <button
                type="submit"
                disabled={isSubmittingEquivocado}
                className="ml-submit-btn"
              >
                {isSubmittingEquivocado ? (
                  'Guardando Feedback ML...'
                ) : (
                  <>
                    <Send size={16} /> Enviar Reporte de Feedback e Imágenes Anotadas
                    <span className="ml-counter-badge">{selectedPhotoUrls.length} foto(s)</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* ── MODAL GALERIA DE FOTOS EN GRANDE (MULTI-IMAGEN Y ORIGEN DE TIENDA) ── */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {galleryState.isOpen && galleryState.product && (
        (() => {
          const imgs = getProductImages(galleryState.product, galleryState.extraImages)
          const galleryStoreLink = getSanitizedStoreUrl(galleryState.product)
          const storeBadge = getStoreBadge(galleryState.product.tienda, galleryStoreLink)
          const currentImg = imgs[galleryState.currentIndex] || galleryState.product.imagen_url


          return (
            <div
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(5, 7, 15, 0.92)',
                backdropFilter: 'blur(12px)',
                zIndex: 2000,
                display: 'flex',
                flexDirection: 'column',
                animation: 'fadeIn 0.2s ease-out',
              }}
            >
              {/* ── Header del Visor ── */}
              <div
                style={{
                  padding: '1rem 1.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderBottom: '1px solid rgba(255,255,255,0.1)',
                  background: 'rgba(0,0,0,0.4)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', overflow: 'hidden' }}>
                  <span
                    style={{
                      background: storeBadge.bg,
                      color: storeBadge.color,
                      padding: '0.3rem 0.8rem',
                      borderRadius: '100px',
                      fontWeight: '700',
                      fontSize: '0.82rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <Store size={14} />
                    {storeBadge.name}
                  </span>

                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <h3 style={{ margin: 0, fontSize: '1rem', color: '#fff', fontWeight: '600' }}>
                      {galleryState.product.titulo}
                    </h3>
                    <span style={{ fontSize: '0.85rem', color: 'var(--accent-primary)', fontWeight: 'bold' }}>
                      ${galleryState.product.precio?.toFixed(2)}
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  {imgs.length > 0 && (
                    <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.85rem', fontWeight: '500' }}>
                      Foto {galleryState.currentIndex + 1} de {imgs.length}
                    </span>
                  )}

                  <a
                    href={galleryStoreLink}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      background: storeBadge.bg,
                      color: storeBadge.color,
                      padding: '0.4rem 0.9rem',
                      borderRadius: '8px',
                      fontWeight: '600',
                      fontSize: '0.82rem',
                      textDecoration: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    Ver en {storeBadge.name}
                  </a>

                  <button
                    onClick={() => setGalleryState(prev => ({ ...prev, zoomLevel: prev.zoomLevel === 1 ? 1.6 : prev.zoomLevel === 1.6 ? 2.4 : 1 }))}
                    style={{
                      background: galleryState.zoomLevel > 1 ? 'var(--accent-primary)' : 'rgba(255,255,255,0.1)',
                      border: '1px solid rgba(255,255,255,0.2)',
                      color: '#fff',
                      padding: '0.4rem 0.8rem',
                      borderRadius: '8px',
                      fontWeight: '600',
                      fontSize: '0.8rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      transition: 'all 0.15s ease',
                    }}
                    title="Alternar Zoom HD (1x / 1.6x / 2.4x)"
                  >
                    <Maximize2 size={14} />
                    Zoom {galleryState.zoomLevel || 1}x
                  </button>

                  <button
                    onClick={closeGallery}
                    style={{
                      background: 'rgba(255,255,255,0.1)',
                      border: 'none',
                      color: '#fff',
                      padding: '0.5rem',
                      borderRadius: '50%',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                    title="Cerrar visor"
                  >
                    <X size={20} />
                  </button>
                </div>
              </div>

              {/* ── Cuerpo Principal: Imagen en Grande HD + Flechas + Zoom Scroll ── */}
              <div
                style={{
                  flex: 1,
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '1rem',
                  userSelect: 'none',
                  overflow: 'auto',
                }}
              >
                {/* Flecha Izquierda */}
                {imgs.length > 1 && (
                  <button
                    onClick={prevGalleryImage}
                    style={{
                      position: 'fixed',
                      left: '1.5rem',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      zIndex: 30,
                      background: 'rgba(0,0,0,0.7)',
                      border: '1px solid rgba(255,255,255,0.3)',
                      color: '#fff',
                      width: '52px',
                      height: '52px',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      backdropFilter: 'blur(6px)',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                      transition: 'all 0.15s ease',
                    }}
                    title="Imagen anterior (Flecha Izquierda)"
                  >
                    <ChevronLeft size={32} />
                  </button>
                )}

                {/* Contenedor Imagen Principal HD con Zoom */}
                {currentImg ? (
                  <div
                    onClick={() => setGalleryState(prev => ({ ...prev, zoomLevel: prev.zoomLevel === 1 ? 1.6 : prev.zoomLevel === 1.6 ? 2.4 : 1 }))}
                    style={{
                      cursor: galleryState.zoomLevel > 1 ? 'zoom-out' : 'zoom-in',
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center',
                      maxWidth: '100%',
                      maxHeight: '100%',
                      overflow: 'auto',
                    }}
                    title="Haz clic sobre la imagen para hacer zoom ultra nítido"
                  >
                    <img
                      src={currentImg}
                      alt={galleryState.product.titulo}
                      style={{
                        maxWidth: (galleryState.zoomLevel || 1) > 1 ? 'none' : '90vw',
                        maxHeight: (galleryState.zoomLevel || 1) > 1 ? 'none' : 'calc(88vh - 160px)',
                        transform: `scale(${galleryState.zoomLevel || 1})`,
                        transformOrigin: 'center center',
                        transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                        objectFit: 'contain',
                        borderRadius: '12px',
                        boxShadow: '0 25px 60px rgba(0,0,0,0.9)',
                        margin: (galleryState.zoomLevel || 1) > 1 ? '4rem' : 'auto',
                      }}
                    />
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-muted)', textAlign: 'center' }}>
                    <Monitor size={64} />
                    <p style={{ marginTop: '0.5rem' }}>Imagen no disponible</p>
                  </div>
                )}

                {/* Flecha Derecha */}
                {imgs.length > 1 && (
                  <button
                    onClick={nextGalleryImage}
                    style={{
                      position: 'fixed',
                      right: '1.5rem',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      zIndex: 30,
                      background: 'rgba(0,0,0,0.7)',
                      border: '1px solid rgba(255,255,255,0.3)',
                      color: '#fff',
                      width: '52px',
                      height: '52px',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      backdropFilter: 'blur(6px)',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                      transition: 'all 0.15s ease',
                    }}
                    title="Imagen siguiente (Flecha Derecha)"
                  >
                    <ChevronRight size={32} />
                  </button>
                )}
              </div>


              {/* ── Carrusel Inferior de Miniaturas ── */}
              {imgs.length > 1 && (
                <div
                  style={{
                    padding: '1rem',
                    background: 'rgba(0,0,0,0.6)',
                    borderTop: '1px solid rgba(255,255,255,0.1)',
                    display: 'flex',
                    justifyContent: 'center',
                    gap: '0.6rem',
                    overflowX: 'auto',
                  }}
                >
                  {imgs.map((imgUrl, idx) => {
                    const isActive = idx === galleryState.currentIndex
                    return (
                      <button
                        key={`${imgUrl}-${idx}`}
                        onClick={() => setGalleryState((prev) => ({ ...prev, currentIndex: idx }))}
                        style={{
                          background: 'none',
                          border: isActive ? `3px solid ${storeBadge.bg}` : '2px solid transparent',
                          borderRadius: '8px',
                          padding: 0,
                          cursor: 'pointer',
                          opacity: isActive ? 1 : 0.5,
                          transform: isActive ? 'scale(1.08)' : 'scale(1)',
                          transition: 'all 0.15s ease',
                          overflow: 'hidden',
                          width: '64px',
                          height: '64px',
                          flexShrink: 0,
                        }}
                      >
                        <img
                          src={imgUrl}
                          alt=""
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })()
      )}

      {/* ── Modal de Previsualización de Collage Numerado de IA ── */}
      {activeCollageModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.85)',
            backdropFilter: 'blur(8px)',
            zIndex: 3000,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            padding: '1.5rem',
          }}
          onClick={() => setActiveCollageModal({ isOpen: false, url: '', title: '' })}
        >
          <div
            className="glass-panel animate-fade-in"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '900px',
              width: '100%',
              maxHeight: '90vh',
              padding: '1.5rem',
              borderRadius: '16px',
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-color)',
            }}
          >
            <button
              onClick={() => setActiveCollageModal({ isOpen: false, url: '', title: '' })}
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                background: 'rgba(255,255,255,0.1)',
                border: 'none',
                color: 'white',
                borderRadius: '50%',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-main)', fontSize: '1.1rem', textAlign: 'center', fontWeight: 'bold' }}>
              🖼️ Collage Numerado Compuesto de IA
            </h3>
            <p style={{ margin: '0 0 1rem 0', color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center' }}>
              {activeCollageModal.title} — Este es el mosaico unificado con celdas numeradas (`#1`, `#2`...) enviado a Groq Vision.
            </p>

            <div style={{ flex: 1, width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden', borderRadius: '12px', background: '#09090b', border: '1px solid rgba(255,255,255,0.1)' }}>
              <img
                src={activeCollageModal.url}
                alt="Collage IA"
                style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain', borderRadius: '8px' }}
              />
            </div>
          </div>
        </div>
      )}

    </div>
  )
}



export default App
