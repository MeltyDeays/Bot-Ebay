-- ═══════════════════════════════════════════════════════════════
-- BOT-eBay: Schema de Base de Datos (Supabase)
-- Idempotente: se puede ejecutar cuantas veces quieras sin error
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
CREATE TABLE IF NOT EXISTS precios_nicaragua (
    id BIGSERIAL PRIMARY KEY,
    tipo TEXT NOT NULL DEFAULT 'laptop',
    titulo_marketplace TEXT NOT NULL,
    modelo TEXT,
    procesador TEXT,
    ram TEXT,
    almacenamiento TEXT,
    precio_nic_usd DECIMAL(10,2) NOT NULL,
    moneda_original TEXT DEFAULT 'USD',
    precio_original DECIMAL(10,2),
    condicion TEXT,
    ciudad TEXT DEFAULT 'Managua',
    fuente TEXT DEFAULT 'fb_marketplace',
    notas TEXT,
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

-- Configuración del bot (Dashboard Control)
CREATE TABLE IF NOT EXISTS bot_settings (
    id SERIAL PRIMARY KEY,
    is_running BOOLEAN DEFAULT TRUE,
    budget DECIMAL(10,2) DEFAULT 250,
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Gestión de Inventario y Finanzas
CREATE TABLE IF NOT EXISTS inventario (
    id SERIAL PRIMARY KEY,
    producto_id BIGINT REFERENCES productos(id) ON DELETE SET NULL,
    titulo TEXT NOT NULL,
    tipo TEXT DEFAULT 'laptop',
    costo_total_usd DECIMAL(10,2) NOT NULL,
    precio_venta_esperado DECIMAL(10,2),
    precio_venta_real DECIMAL(10,2),
    estado TEXT DEFAULT 'en_transito',
    tracking_number TEXT,
    comprado_en TIMESTAMPTZ DEFAULT NOW(),
    vendido_en TIMESTAMPTZ,
    notas TEXT
);

-- Tabla de feedback de Machine Learning para resultados incorrectos
CREATE TABLE IF NOT EXISTS ejemplos_equivocados (
    id BIGSERIAL PRIMARY KEY,
    producto_id TEXT,
    titulo TEXT NOT NULL,
    precio DECIMAL(10,2),
    imagen_url TEXT,
    imagen_local_path TEXT,
    motivo_error TEXT NOT NULL,
    vendedor TEXT,
    marca TEXT,
    registrado_en TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- Índices (IF NOT EXISTS = seguro)
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_productos_vendedor ON productos(vendedor);
CREATE INDEX IF NOT EXISTS idx_productos_marca ON productos(marca);
CREATE INDEX IF NOT EXISTS idx_productos_precio ON productos(precio);
CREATE INDEX IF NOT EXISTS idx_productos_fecha ON productos(encontrado_en DESC);
CREATE INDEX IF NOT EXISTS idx_productos_activo ON productos(activo);
CREATE INDEX IF NOT EXISTS idx_productos_margen ON productos(margen_estimado DESC);
CREATE INDEX IF NOT EXISTS idx_precios_nic_tipo ON precios_nicaragua(tipo);
CREATE INDEX IF NOT EXISTS idx_precios_nic_modelo ON precios_nicaragua(modelo);
CREATE INDEX IF NOT EXISTS idx_busquedas_fecha ON busquedas(fecha DESC);
CREATE INDEX IF NOT EXISTS idx_ejemplos_equivocados_fecha ON ejemplos_equivocados(registrado_en DESC);


-- ═══════════════════════════════════════════════════════════════
-- RLS + Políticas (idempotente con DO $$ ... $$)
-- ═══════════════════════════════════════════════════════════════
DO $$
BEGIN
  -- Habilitar RLS (no falla si ya está habilitado)
  ALTER TABLE productos ENABLE ROW LEVEL SECURITY;
  ALTER TABLE precios_nicaragua ENABLE ROW LEVEL SECURITY;
  ALTER TABLE busquedas ENABLE ROW LEVEL SECURITY;
  ALTER TABLE alertas ENABLE ROW LEVEL SECURITY;
  ALTER TABLE bot_settings ENABLE ROW LEVEL SECURITY;
  ALTER TABLE inventario ENABLE ROW LEVEL SECURITY;

  -- Políticas: crear solo si no existen
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'productos' AND policyname = 'allow_all_productos') THEN
    CREATE POLICY "allow_all_productos" ON productos FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'precios_nicaragua' AND policyname = 'allow_all_precios_nic') THEN
    CREATE POLICY "allow_all_precios_nic" ON precios_nicaragua FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'busquedas' AND policyname = 'allow_all_busquedas') THEN
    CREATE POLICY "allow_all_busquedas" ON busquedas FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'alertas' AND policyname = 'allow_all_alertas') THEN
    CREATE POLICY "allow_all_alertas" ON alertas FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'bot_settings' AND policyname = 'allow_all_bot_settings') THEN
    CREATE POLICY "allow_all_bot_settings" ON bot_settings FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'inventario' AND policyname = 'allow_all_inventario') THEN
    CREATE POLICY "allow_all_inventario" ON inventario FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- Datos iniciales
-- ═══════════════════════════════════════════════════════════════
INSERT INTO bot_settings (id, is_running, budget)
VALUES (1, true, 250)
ON CONFLICT (id) DO NOTHING;
