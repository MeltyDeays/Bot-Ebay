import os
from typing import Dict, List, Tuple

# --- CONSTANTES ---
MAX_RESCUE_CHECKS = 10
MAX_EJEMPLOS = 5

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
    {"id": "175672", "nombre": "PC Laptops & Netbooks"}
]

MARCAS_SOPORTADAS = ["hp", "lenovo", "dell"]

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
    return {
        "max_precio": float(os.getenv("MAX_PRECIO_USD", "300")),
        "min_precio": float(os.getenv("MIN_PRECIO_USD", "30")),
        "use_ebay_api": valor_env_bool("USE_EBAY_API", True),
        "use_browser_fallback": valor_env_bool("USE_BROWSER_FALLBACK", False),
        "ebay_client_id": os.getenv("EBAY_CLIENT_ID", "").strip(),
        "ebay_client_secret": os.getenv("EBAY_CLIENT_SECRET", "").strip(),
        "ebay_marketplace_id": os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip(),
        "marcas": lista_env("MARCAS", MARCAS_SOPORTADAS),
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
