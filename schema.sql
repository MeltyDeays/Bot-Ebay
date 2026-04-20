-- ═══════════════════════════════════════════════════════════════
-- BOT-eBay: Schema de Base de Datos (Supabase)
-- ═══════════════════════════════════════════════════════════════

-- Tabla principal de productos encontrados en eBay
CREATE TABLE IF NOT EXISTS productos (
    id BIGSERIAL PRIMARY KEY,
    ebay_item_id TEXT UNIQUE,
    titulo TEXT NOT NULL,
    precio DECIMAL(10,2),
    precio_texto TEXT,
    moneda TEXT DEFAULT 'USD',
    condicion TEXT,
    categoria TEXT,
    marca TEXT,
    procesador TEXT,
    ram TEXT,
    ssd TEXT,
    vendedor TEXT,
    enlace TEXT,
    imagen_url TEXT,
    es_subasta BOOLEAN DEFAULT FALSE,
    tiempo_restante TEXT,
    buying_options TEXT,
    -- IA Analysis
    ia_score INTEGER DEFAULT 0,
    ia_veredicto TEXT,
    ia_defectos_fisicos TEXT,
    ia_calidad_visual TEXT,
    -- Rentabilidad Nicaragua (solo para precio fijo, NO subastas)
    precio_estimado_nic DECIMAL(10,2),
    margen_estimado DECIMAL(10,2),
    porcentaje_ganancia DECIMAL(5,2),
    analisis_rentabilidad TEXT,
    -- Metadata
    encontrado_en TIMESTAMPTZ DEFAULT NOW(),
    enviado_telegram BOOLEAN DEFAULT FALSE,
    activo BOOLEAN DEFAULT TRUE
);

-- Precios REALES de Nicaragua (alimentados manualmente por el usuario)
-- Cada vez que el usuario ve un producto en FB Marketplace NIC, lo registra aquí
CREATE TABLE IF NOT EXISTS precios_nicaragua (
    id BIGSERIAL PRIMARY KEY,
    -- Qué producto es
    tipo TEXT NOT NULL DEFAULT 'laptop',  -- laptop, phone, ssd, ram, etc
    titulo_marketplace TEXT NOT NULL,      -- Título como aparece en FB Marketplace
    modelo TEXT,                           -- Modelo simplificado (ej: "EliteBook 845 G7")
    -- Specs clave (para matching)
    procesador TEXT,
    ram TEXT,
    almacenamiento TEXT,
    -- Precio
    precio_nic_usd DECIMAL(10,2) NOT NULL,  -- Precio en USD (o córdobas convertido)
    moneda_original TEXT DEFAULT 'USD',       -- USD o NIO
    precio_original DECIMAL(10,2),            -- Precio original si es en córdobas
    -- Contexto
    condicion TEXT,            -- nuevo, usado, refurbished
    ciudad TEXT DEFAULT 'Managua',
    fuente TEXT DEFAULT 'fb_marketplace',  -- fb_marketplace, encuentra24, whatsapp
    notas TEXT,
    -- Metadata
    registrado_en TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de búsquedas realizadas (para estadísticas)
CREATE TABLE IF NOT EXISTS busquedas (
    id BIGSERIAL PRIMARY KEY,
    query TEXT,
    categoria TEXT,
    marca TEXT,
    total_encontrados INTEGER DEFAULT 0,
    total_aceptados INTEGER DEFAULT 0,
    total_rechazados INTEGER DEFAULT 0,
    duracion_segundos DECIMAL(6,2),
    fecha TIMESTAMPTZ DEFAULT NOW()
);

-- Alertas personalizadas (para expandir a multi-categoría)
CREATE TABLE IF NOT EXISTS alertas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    tipo TEXT DEFAULT 'laptop',
    categoria_ebay TEXT DEFAULT '175672',
    criterio_ia TEXT,
    keywords TEXT,
    max_precio DECIMAL(10,2) DEFAULT 200,
    activa BOOLEAN DEFAULT TRUE,
    creada_en TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_productos_vendedor ON productos(vendedor);
CREATE INDEX IF NOT EXISTS idx_productos_marca ON productos(marca);
CREATE INDEX IF NOT EXISTS idx_productos_precio ON productos(precio);
CREATE INDEX IF NOT EXISTS idx_productos_fecha ON productos(encontrado_en DESC);
CREATE INDEX IF NOT EXISTS idx_productos_activo ON productos(activo);
CREATE INDEX IF NOT EXISTS idx_productos_margen ON productos(margen_estimado DESC);
CREATE INDEX IF NOT EXISTS idx_precios_nic_tipo ON precios_nicaragua(tipo);
CREATE INDEX IF NOT EXISTS idx_precios_nic_modelo ON precios_nicaragua(modelo);
CREATE INDEX IF NOT EXISTS idx_busquedas_fecha ON busquedas(fecha DESC);

-- RLS + Políticas abiertas (para que la web app pueda leer)
ALTER TABLE productos ENABLE ROW LEVEL SECURITY;
ALTER TABLE precios_nicaragua ENABLE ROW LEVEL SECURITY;
ALTER TABLE busquedas ENABLE ROW LEVEL SECURITY;
ALTER TABLE alertas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all_productos" ON productos FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_precios_nic" ON precios_nicaragua FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_busquedas" ON busquedas FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_alertas" ON alertas FOR ALL USING (true) WITH CHECK (true);
