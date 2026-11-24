import os
from typing import Dict, List, Tuple

# --- CONSTANTES ---
MAX_RESCUE_CHECKS = 50
MAX_VERIFY_CHECKS = 30
MAX_WORKERS_AI = 5
MAX_EJEMPLOS = 5

BLOCKED_SELLERS = [
    "plc machinery",
    "plc_machinery",
]

ESTADOS_BUSQUEDA = [
    {"id": "1000", "nombre": "New"},
    {"id": "1500", "nombre": "Open box"},
    {"id": "2000", "nombre": "Certified Refurbished"},
    {"id": "2010", "nombre": "Excellent Refurbished"},
    {"id": "2020", "nombre": "Very Good Refurbished"},
    {"id": "2030", "nombre": "Good Refurbished"},
    {"id": "3000", "nombre": "Used"},
]

CATEGORIAS_BUSQUEDA = [
    {"id": "175672", "nombre": "Intel Core i3", "terminos": ["i3", "intel core i3", "core i3"]},
    {"id": "175672", "nombre": "Intel Core i5", "terminos": ["i5", "intel core i5", "core i5"]},
    {"id": "175672", "nombre": "Intel Core i7", "terminos": ["i7", "intel core i7", "core i7"]},
    {"id": "175672", "nombre": "Ryzen 3", "terminos": ["ryzen 3"]},
    {"id": "175672", "nombre": "Ryzen 5", "terminos": ["ryzen 5"]},
    {"id": "175672", "nombre": "Ryzen 7", "terminos": ["ryzen 7"]},
    {"id": "175672", "nombre": "Ryzen 9", "terminos": ["ryzen 9"]},
    {"id": "175672", "nombre": "Intel Core i9", "terminos": ["i9", "intel core i9", "core i9"]},
]

MARCAS_SOPORTADAS = ["hp", "lenovo", "dell", "acer", "asus", "msi", "apple", "razer"]

MARCAS_Y_LINEAS = {
    "acer": ["Predator", "Nitro", "Nitro V", "Aspire", "Swift", "Spin", "TravelMate", "Enduro"],
    "asus": ["ROG Zephyrus", "ROG Strix", "TUF Gaming", "ZenBook", "VivoBook", "ProArt Studiobook", "ExpertBook"],
    "dell": ["Alienware", "XPS", "Latitude", "Inspiron", "Precision", "Vostro", "G Series"],
    "hp": ["OMEN", "Victus", "Spectre", "Envy", "Pavilion", "EliteBook", "ProBook", "ZBook"],
    "lenovo": ["Legion", "LOQ", "ThinkPad", "IdeaPad", "Yoga", "Slim", "ThinkBook"],
    "msi": ["Raider", "Stealth", "Cyborg", "Katana", "Pulse", "Thin", "Prestige", "Vector", "Titan"],
    "apple": ["MacBook Air", "MacBook Pro"],
    "razer": ["Blade 14", "Blade 15", "Blade 16", "Blade 17", "Blade 18"],
    "samsung": ["Galaxy Book", "Galaxy Book Pro", "Galaxy Book Ultra"],
    "microsoft": ["Surface Laptop", "Surface Pro", "Surface Book", "Surface Studio"],
}

TIENDAS_SOPORTADAS = ["eBay", "Amazon", "BackMarket", "Newegg", "Mercari", "BestBuy", "Walmart", "BHPhoto", "MicroCenter", "Swappa", "Woot"]



# --- UTILIDADES DE CONFIGURACIÓN ---
def cargar_env(ruta: str = ".env") -> None:
    if not os.path.exists(ruta): return
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"): continue
            if "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ[clave.strip()] = valor.strip()

def valor_env_bool(clave: str, por_defecto: bool = False) -> bool:
    v = os.getenv(clave, "").strip().lower()
    if not v: return por_defecto
    return v in ("true", "1", "yes", "si", "on")

def lista_env(clave: str, por_defecto: List[str] = None) -> List[str]:
    v = os.getenv(clave, "").strip()
    if not v: return por_defecto or []
    return [x.strip() for x in v.split(",") if x.strip()]

def _parsear_destinos_extra(raw: str) -> List[Tuple[str, str]]:
    destinos = []
    if not raw: return destinos
    for bloque in raw.split(';'):
        bloque = bloque.strip()
        if not bloque: continue
        partes = bloque.split(',')
        if len(partes) >= 2:
            tok = partes[0].strip()
            for cid in partes[1:]:
                cid = cid.strip()
                if cid: destinos.append((tok, cid))
    return destinos

def todos_los_destinos(config: dict) -> List[Tuple[str, str]]:
    destinos = []
    if config.get("telegram_token"):
        for cid in config.get("telegram_chat_ids", []):
            destinos.append((config["telegram_token"], cid))
    destinos.extend(config.get("extra_destinations", []))
    return destinos

def obtener_configuracion() -> dict:
    cargar_env()

    # CARGAR FILTROS DINAMICOS
    cats_busqueda = CATEGORIAS_BUSQUEDA
    ests_busqueda = ESTADOS_BUSQUEDA
    tiendas_activas = ["eBay"]
    combinar_resultados = True
    min_vendedor_ventas = 1000

    try:
        if os.path.exists("user_filters.json"):
            import json
            with open("user_filters.json", "r", encoding="utf-8") as f:
                filtros_json = json.load(f)
                if "categorias_activas" in filtros_json:
                    activas = set(filtros_json["categorias_activas"])
                    cats_busqueda = [c for c in CATEGORIAS_BUSQUEDA if c["nombre"] in activas]
                if "estados_activos" in filtros_json:
                    activos = set(filtros_json["estados_activos"])
                    ests_busqueda = [e for e in ESTADOS_BUSQUEDA if e["nombre"] in activos]
                if "tiendas_activas" in filtros_json:
                    tiendas_activas = filtros_json["tiendas_activas"]
                if "combinar_resultados" in filtros_json:
                    combinar_resultados = bool(filtros_json["combinar_resultados"])
                if "min_vendedor_ventas" in filtros_json:
                    min_vendedor_ventas = int(filtros_json["min_vendedor_ventas"])
    except Exception:
        pass

    return {
        "max_precio": float(os.getenv("MAX_PRECIO", "300")),
        "min_precio": float(os.getenv("MIN_PRECIO_USD", "30")),
        "min_vendedor_ventas": int(os.getenv("MIN_VENDEDOR_VENTAS", str(min_vendedor_ventas))),

        "use_ebay_api": valor_env_bool("USE_EBAY_API", True),
        "use_browser_fallback": valor_env_bool("USE_BROWSER_FALLBACK", False),
        "ebay_client_id": os.getenv("EBAY_CLIENT_ID", "").strip(),
        "ebay_client_secret": os.getenv("EBAY_CLIENT_SECRET", "").strip(),
        "ebay_marketplace_id": os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip(),
        "ebay_currency": os.getenv("EBAY_CURRENCY", "USD").strip(),
        "ebay_site": os.getenv("EBAY_SITE", "https://www.ebay.com").strip(),
        "marcas": lista_env("MARCAS", MARCAS_SOPORTADAS),
        "categorias_busqueda": cats_busqueda,
        "estados_busqueda": ests_busqueda,
        "tiendas_activas": tiendas_activas,
        "combinar_resultados": combinar_resultados,
        "telegram_token": os.getenv("TELEGRAM_TOKEN", "").strip(),
        "telegram_chat_ids": lista_env("TELEGRAM_CHAT_ID"),
        "extra_destinations": _parsear_destinos_extra(os.getenv("TELEGRAM_EXTRA_DESTINATIONS", "")),
        "run_once": valor_env_bool("RUN_ONCE", False),
        "dry_run": valor_env_bool("DRY_RUN", False),
        "max_reintentos": max(1, int(os.getenv("MAX_REINTENTOS", "3"))),
        "sleep_min_seconds": float(os.getenv("SLEEP_MIN_SEGUNDOS", "3")),
        "sleep_max_seconds": float(os.getenv("SLEEP_MAX_SEGUNDOS", "6")),
        "browser_headless": valor_env_bool("BROWSER_HEADLESS", False),
        "browser_timeout_ms": max(1000, int(os.getenv("BROWSER_TIMEOUT_MS", "45000"))),
        "browser_settle_ms": max(0, int(os.getenv("BROWSER_SETTLE_MS", "2500"))),
        "browser_results_wait_ms": max(1000, int(os.getenv("BROWSER_RESULTS_WAIT_MS", "10000"))),
        "browser_profile_dir": os.getenv("BROWSER_PROFILE_DIR", ".browser-profile").strip() or ".browser-profile",
        "browser_channel": os.getenv("BROWSER_CHANNEL", "").strip() or None,
        "browser_executable_path": os.getenv("BROWSER_EXECUTABLE_PATH", "").strip(),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "groq_api_key": os.getenv("GROQ_API_KEY", "").strip(),
        "supabase_url": os.getenv("SUPABASE_URL", "").strip(),
        "supabase_service_key": os.getenv("SUPABASE_SERVICE_KEY", "").strip(),
    }

