import base64
import html
import json
import os
import random
import re
import sys
# Forzar UTF-8 en Windows para que los emojis no crasheen la terminal
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, Playwright, sync_playwright
except ModuleNotFoundError:
    PlaywrightError = Exception
    Page = Any
    Playwright = Any
    sync_playwright = None

# --- CONFIGURACIÓN DE BÚSQUEDA ---
ESTADOS_BUSQUEDA = [
    {"nombre": "Nuevo", "condition_id": "1000"},
    {"nombre": "Open Box", "condition_id": "1500"},
    {"nombre": "Certificado - Renovado", "condition_id": "2000"},
    {"nombre": "Excelente - Renovado", "condition_id": "2501"},
    {"nombre": "Muy Bueno - Renovado", "condition_id": "2502"},
    {"nombre": "Vendedor - Renovado", "condition_id": "2500"},
    {"nombre": "Usado", "condition_id": "3000"},
]

CATEGORIAS_BUSQUEDA = [
    {"nombre": "Ryzen 3", "terminos": ["ryzen 3", "r3"]},
    {"nombre": "Ryzen 5", "terminos": ["ryzen 5", "r5"]},
    {"nombre": "Ryzen 7", "terminos": ["ryzen 7", "r7"]},
    {"nombre": "Ryzen 9", "terminos": ["ryzen 9", "r9"]},
    {"nombre": "Intel i3", "terminos": ["i3", "core i3"]},
    {"nombre": "Intel i5", "terminos": ["i5", "core i5", "ultra 5"]},
    {"nombre": "Intel i7", "terminos": ["i7", "core i7", "ultra 7"]},
    {"nombre": "Intel i9", "terminos": ["i9", "core i9", "ultra 9"]},
]

DB_LOCAL = "ofertas_enviadas.json"
MARCAS_DEFAULT = ["HP", "Dell", "Lenovo", "Asus", "Acer", "MSI"]

# --- FILTRO EXTREMO DE CHATARRA ESTÉTICA Y DE PIEZAS ---
EXCLUSION_PATTERN = re.compile(
    r'(\bfor parts\b|\bnot working\b|\bparts only\b|\bbroken\b|\bdead pixel[s]?\b|\blines on screen\b|'
    r'\bbad screen\b|\bcracked screen\b|\bdamaged screen\b|'
    r'\bwater damage\b|\bspill\b|\bdamaged\b|'
    r'\bno ram\b|\bno ssd\b|\bno hdd\b|\bno drive\b|\bno hard drive\b|'
    r'\bwithout ram\b|\bwithout ssd\b|\bwithout hdd\b|\bw/o ram\b|\bw/o ssd\b|'
    r'\bmissing ram\b|\bmissing ssd\b|\bmissing hdd\b|\bmissing hard drive\b|'
    r'\bwithout ssd\b|\bno battery\b|\bno batt\b|\bwithout battery\b|\bw/o battery\b|\bmissing battery\b|'
    r'\bno ac\b|\bno charger\b|\bno power adapter\b|\bno ac adapter\b|'
    r'\bwithout charger\b|\bw/o charger\b|\bmissing charger\b|\bmissing power\b|'
    r'\bno power cord\b|\bwithout power cord\b|\bmissing cord\b|'
    r'\bno\b.{0,15}\bpower adapter\b|'
    r'\bdevice only\b|\blaptop only\b|'
    r'\bbarebone\b|\bgrade c\b|\bgrade d\b|\bfair condition\b|\bheavy wear\b|\bheavily scratched\b|\bdeep scratches\b|\bchipped\b|'
    r'\bas is\b|\bas-is\b|\buntested\b|\bno power\b|\bwont turn on\b|'
    r'\bicloud\b|\bmdm\b|\bbios lock\b|\bcomputrace\b|[\*\#]+read[\*\#]+|\bread description\b|'
    r'\bplease read\b|\bmust read\b|\bsee notes\b|\bread notes\b|\bcheck notes\b|\bneeds repair\b|'
    r'\bburn[- ]in\b|\bcracked\b|\bcrack\b|'
    # --- Piezas sueltas (NO son laptops completas) ---
    r'\bmotherboard\b|\bmainboard\b|\bsystem board\b|\blogic board\b|\bmobo\b|'
    r'\blaptop keyboard\b|\bkeyboard for\b|\breplacement keyboard\b|\bpalmrest\b|\bpalm rest\b|'
    r'\blcd screen\b|\blcd panel\b|\bdisplay panel\b|\bscreen only\b|\bpanel only\b|'
    r'\bbottom case\b|\bbottom cover\b|\btop case\b|\btop cover\b|\bback cover\b|'
    r'\bhinge[s]?\b|\bbezel\b|\blcd lid\b|\blaptop lid\b|\bbase cover\b|\bbase only\b|'
    r'\bbattery for\b|\breplacement battery\b|\bcharger for\b|\bac adapter for\b|\bpower adapter for\b|'
    r'\bscreen protector\b|\bcircuit breaker[s]?\b|\btempered glass\b|\bcover\b|\bcase\b|\bsleeve\b|\bskin\b|\bdecal\b|\bsticker\b|\bbag\b|\bbackpack\b|'
    r'\bpower supply\b|\breplacement screen\b|\bkeycap\b|\bheat sink\b|\bcooling fan\b|\bdc jack\b|\bpower jack\b|\bgaming charger\b|\bcharger compatible\b|'
    r'\breplacement\b|\bspare part\b|\brepair part\b|\bcomponent\b|'
    # --- Accesorios y fundas (NO son laptops) ---
    r'\bcontour case\b|\bbroonel\b|\blaptop case\b|\blaptop sleeve\b|\bsleeve\b|\bcarrying case\b|'
    r'\blaptop bag\b|\bprotective case\b|\bhard case\b|\bshell case\b|\bcover case\b|'
    # --- CPU/procesadores sueltos y adaptadores ---
    r'\bcpu processor\b|\bprocessor for\b|\bcpu for\b|\bcpu only\b|'
    r'\blaptop adapter\b|\bcharger adapter\b|\bac adapter\b|\badapter for\b|'
    r'\blaptop charger\b|\bcharger for\b|\bpower supply\b|\bdocking station\b|\bdock\b|'
    # --- Sistemas operativos viejos (laptops obsoletas) ---
    r'\bwindows 7\b|\bwin 7\b|\bwin7\b|\bwindows vista\b|\bwindows xp\b|\bwin xp\b|'
    r'\bchrome\s*os\b|\bchromebook\b|'
    # --- Piezas extraídas / BIOS ---
    r'\btook out from\b|\bremoved from\b|\bpulled from\b|\bextracted from\b|'
    r'\bbios password\b|\bno storage\b)',
    re.IGNORECASE
)

# Patrones para DESCRIPCIONES (frases complejas que no aparecen en títulos)
DESCRIPTION_RED_FLAGS = re.compile(
    r'(battery.{0,20}not included|charger.{0,20}not included|'
    r'power adapter.{0,20}not included|adapter.{0,20}not included|'
    r'storage.{0,20}not included|ssd.{0,20}not included|'
    r'ram.{0,20}not included|drive.{0,20}not included|'
    r'does not come with.{0,20}(?:battery|charger|adapter|ssd|ram|drive)|'
    r'does not include.{0,20}(?:battery|charger|adapter|ssd|ram|drive)|'
    r'(?:battery|charger|adapter|power).{0,10}(?:not|is not|isn.t).{0,10}included|'
    r'included\)?\s*:?\s*no\b|'
    r'(?:no|without|missing).{0,5}(?:storage|hard) drive)',
    re.IGNORECASE
)

INTERVENCION_TOKENS = [
    "splashui/challenge", "sorry for the interruption", "disculpa la interrupcion",
    "to continue, please verify", "signin.ebay.com"
]

BROWSER_PATHS_WINDOWS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]

class EbayChallengeError(RuntimeError):
    pass

@dataclass
class OfertaLaptop:
    procesador: str
    estado: str
    titulo: str
    precio: float
    precio_texto: str
    enlace: str
    imagen: str
    es_subasta: bool
    tiempo_restante: str
    vendedor: str = ""

# --- FUNCIONES DE UTILIDAD Y TIEMPO ---
def calcular_tiempo_restante(fecha_fin_iso: str) -> str:
    if not fecha_fin_iso: return "Desconocido"
    try:
        end_date = datetime.strptime(fecha_fin_iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = end_date - now
        
        if diff.total_seconds() <= 0: return "Terminada"
        
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0: return f"{days}d {hours}h"
        if hours > 0: return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except:
        return "Desconocido"

def cargar_env(ruta: str = ".env") -> None:
    if not os.path.exists(ruta): return
    with open(ruta, "r", encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea: continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())

def valor_env_bool(nombre: str, default: bool = False) -> bool:
    valor = os.getenv(nombre)
    return default if valor is None else valor.strip().lower() in {"1", "true", "yes", "si", "on"}

def lista_env(nombre: str, default: List[str]) -> List[str]:
    valor = os.getenv(nombre, "")
    if not valor.strip(): return list(default)
    return [item.strip() for item in valor.split(",") if item.strip()]

def _parsear_destinos_extra() -> List[Tuple[str, str]]:
    """Lee TELEGRAM_EXTRA_1, TELEGRAM_EXTRA_2, etc. del .env.
    Formato: token:chat_id (separados por dos puntos)."""
    destinos = []
    i = 1
    while True:
        raw = os.getenv(f"TELEGRAM_EXTRA_{i}", "").strip()
        if not raw:
            break
        if ":" in raw:
            token, chat_id = raw.split(":", 1)
            # El token de Telegram tiene formato NNNNNNN:AAAA..., así que hay que re-juntar
            # Formato esperado en .env: TELEGRAM_EXTRA_1=TOKEN_COMPLETO|CHAT_ID
            pass
        i += 1
    # Usar formato con pipe: TOKEN|CHAT_ID
    i = 1
    destinos = []
    while True:
        raw = os.getenv(f"TELEGRAM_EXTRA_{i}", "").strip()
        if not raw:
            break
        if "|" in raw:
            token, chat_id = raw.rsplit("|", 1)
            if token.strip() and chat_id.strip():
                destinos.append((token.strip(), chat_id.strip()))
        i += 1
    return destinos

def _todos_los_destinos(config: dict) -> List[Tuple[str, str]]:
    """Retorna lista de (token, chat_id) para todos los destinos configurados."""
    destinos = []
    token_principal = config["telegram_token"]
    for cid in config["telegram_chat_ids"]:
        destinos.append((token_principal, cid))
    destinos.extend(config.get("telegram_destinos_extra", []))
    return destinos

def obtener_configuracion() -> dict:
    cargar_env()
    return {
        "telegram_token": os.getenv("TELEGRAM_TOKEN", "").strip(),
        "telegram_chat_ids": [cid.strip() for cid in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()],
        # Soporte para destinos adicionales (otros bots)
        "telegram_destinos_extra": _parsear_destinos_extra(),
        "dry_run": valor_env_bool("DRY_RUN", False),
        "run_once": valor_env_bool("RUN_ONCE", False),
        "use_browser_fallback": valor_env_bool("USE_BROWSER_FALLBACK", False),
        "ebay_site": os.getenv("EBAY_SITE", "https://www.ebay.com").strip().rstrip("/"),
        "marcas": lista_env("MARCAS", MARCAS_DEFAULT),
        "use_ebay_api": valor_env_bool("USE_EBAY_API", True),
        "ebay_client_id": os.getenv("EBAY_CLIENT_ID", "").strip(),
        "ebay_client_secret": os.getenv("EBAY_CLIENT_SECRET", "").strip(),
        "ebay_marketplace_id": os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip() or "EBAY_US",
        "ebay_currency": os.getenv("EBAY_CURRENCY", "USD").strip() or "USD",
        "max_precio": float(os.getenv("MAX_PRECIO", "200")),
        "intervalo_horas": float(os.getenv("INTERVALO_HORAS", "8")),
        "top_por_mensaje": max(1, int(os.getenv("TOP_POR_MENSAJE", "15"))),
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
    }

def cargar_ofertas_enviadas() -> Set[str]:
    if not os.path.exists(DB_LOCAL): return set()
    try:
        with open(DB_LOCAL, "r", encoding="utf-8") as archivo: return set(json.load(archivo))
    except (json.JSONDecodeError, IOError): return set()

def guardar_ofertas_enviadas(enlaces: Set[str]) -> None:
    with open(DB_LOCAL, "w", encoding="utf-8") as archivo:
        json.dump(sorted(enlaces), archivo, indent=4)

def extraer_precio(texto: str) -> Optional[float]:
    texto_limpio = re.sub(r"[^\d.,]", "", texto)
    if " " in texto.strip():
        partes = texto.strip().split()
        for p in partes:
            if any(c.isdigit() for c in p):
                texto_limpio = re.sub(r"[^\d.,]", "", "".join(partes[partes.index(p):]))
                break
    match = re.search(r"(\d+(?:[.,\s]\d{3})*(?:[.,]\d{2})?)", texto)
    if not match: return None
    valor_str = match.group(1)
    if "," in valor_str and "." in valor_str:
        if valor_str.find(",") < valor_str.find("."): valor_str = valor_str.replace(",", "")
        else: valor_str = valor_str.replace(".", "").replace(",", ".")
    elif "," in valor_str:
        if len(valor_str.split(",")[-1]) == 2: valor_str = valor_str.replace(",", ".")
        else: valor_str = valor_str.replace(",", "")
    return float(re.sub(r"[^\d.]", "", valor_str))

def limpiar_texto(texto: str) -> str: return re.sub(r"\s+", " ", html.unescape(texto)).strip()

def es_titulo_valido(titulo: str) -> bool:
    return not bool(EXCLUSION_PATTERN.search(titulo))

# --- FILTRO DE GENERACIÓN CPU (ESTRICTO) ---

def es_generacion_valida(titulo: str, categoria: dict) -> bool:
    t = titulo.lower()

    # --- Limpieza de ruido antes de analizar ---
    t = re.sub(r'\d{3,4}\s*x\s*\d{3,4}', '', t)            # resoluciones ej. 1920x1080
    t = re.sub(r'\b(?:fhd|hd|uhd|4k|ips|tn|oled|led)\b', '', t)  # tipos de pantalla
    t = re.sub(r'\b\d{1,2}\.?\d?"?\s*(?:inch|in\b)', '', t)  # tamaños de pantalla
    t = re.sub(r'[-_/]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    nombre_cat = categoria["nombre"].lower()

    # 1. RECHAZAR GENERACIONES EXPLICITAMENTE MALAS PRIMERO (Ahorra API calls y evita falsos positivos en el fallback)
    if "ryzen" in nombre_cat or "amd" in nombre_cat:
        # Generación MALA explícita: 1xxx-3xxx
        if re.search(r'\b[123]\d{3}[a-z]*\b', t): return False, True
        # Athlon o A-Series (A9, A12, etc.)
        if re.search(r'\bathlon\b|\ba\d{1,2}\b', t): return False, True

    if "intel" in nombre_cat or "i" in nombre_cat:
        # Generaciones explícitamente viejas (1st-10th)
        if re.search(r'\b[1-9]th\b|\b10th\b|\b[1-3]rd\b|\b[1-2]nd\b|\b1st\b', t): return False, True
        if re.search(r'\bgen\s*[1-9]\b|\bgen\s*10\b|\b[1-9]\s*gen\b|\b10\s*gen\b', t): return False, True
        # Número de modelo Intel malo (3/4 dígitos viejos o 10xxx)
        if re.search(r'\b\d{3,4}[a-z]?\d?\b', t) or re.search(r'\b10\d{2,3}[a-z]?\d?\b', t): return False, True

    # 2. Verificar que el término de la categoría esté en el título
    # Si no está, no podemos asegurar que sea buena, va a rescate.
    if not any(termino in t for termino in categoria["terminos"]):
        return False, False

    # 3. VERIFICAR GENERACIONES BUENAS
    if "ryzen" in nombre_cat:
        # Generación BUENA: 4xxx–8xxx
        if re.search(r'\b[45678]\d{3}[a-z]*\b', t): return True, True
        
    if "intel" in nombre_cat or "i" in nombre_cat:
        # Core Ultra siempre válido
        if re.search(r'\bultra\s*[579]\b', t) or (re.search(r'\b[12]\d{2}[a-z]+\b', t) and 'ultra' in t): return True, True
        # Generación explícita buena (11th–15th)
        if re.search(r'\b1[12345]th\b|\bgen\s*1[12345]\b|\b1[12345]\s*gen\b', t): return True, True
        # Número de modelo Intel bueno (11xx–15xx)
        if re.search(r'\b1[12345]\d{2,3}[a-z]?\d?\b', t): return True, True

    # Sin modelo explícito (ej. solo "Ryzen 5" o "Core i7")
    return False, False

def cumple_especificaciones_almacenamiento(titulo: str) -> bool:
    """Solo rechaza si el título menciona specs MALAS explícitamente.
    Si el vendedor no especifica RAM/SSD → se acepta (muy común en eBay)."""
    t = titulo.lower()
    # RAM aceptable: 16/32/64 GB
    tiene_ram_buena = bool(re.search(r'\b(?:16|32|64)\s*(?:gb|g\b|ram|ddr[345]?)\b|\b(?:16|32|64)\s*/', t))
    # RAM mala: 4 u 8 GB explícito
    tiene_ram_mala  = bool(re.search(r'\b(?:4|6|8)\s*(?:gb|g\b|ram|ddr[345]?)\b(?!\s*/\s*(?:16|32|64))', t))
    # SSD aceptable: 240/250/256/480/500/512 GB, 1TB, 2TB
    tiene_rom_buena = bool(re.search(
        r'\b(?:240|250|256|480|500|512)\s*(?:gb|g\b|ssd|nvme|pcie|m\.2)\b'
        r'|\b(?:1|1\.5|2)\s*tb\b'
        r'|/\s*(?:240|250|256|480|500|512)\b', t))
    # SSD malo: 32/64/120/128 GB
    tiene_rom_mala  = bool(re.search(r'\b(?:32|64|120|128)\s*(?:gb|g\b|ssd|nvme|hdd|emmc)\b', t))

    if tiene_ram_mala and not tiene_ram_buena: return False
    if tiene_rom_mala and not tiene_rom_buena: return False
    return True

# --- VERIFICACIÓN PROFUNDA VIA API (Descripción + Item Specifics) ---

def obtener_detalle_item_api(config: dict, item_id: str) -> Optional[dict]:
    """Obtiene detalles completos de un item: descripción HTML + item specifics."""
    try:
        token = obtener_token_ebay_app(config)
        encoded_id = quote_plus(item_id)
        url = f"https://api.ebay.com/buy/browse/v1/item/{encoded_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
        }
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def extraer_texto_enriquecido(detalle: dict) -> str:
    """Combina título + descripción + item specifics en un solo texto."""
    partes = [detalle.get("title", "")]
    # Descripción completa (HTML → texto plano)
    desc_html = detalle.get("description", "")
    if desc_html:
        sopa = BeautifulSoup(desc_html, "html.parser")
        partes.append(sopa.get_text(" ", strip=True))
    # Item specifics (campos estructurados del vendedor)
    for aspecto in detalle.get("localizedAspects", []):
        nombre = aspecto.get("name", "")
        valor = aspecto.get("value", "")
        if nombre and valor:
            partes.append(f"{nombre}: {valor}")
    # Short description
    short = detalle.get("shortDescription", "")
    if short:
        partes.append(short)
    return " ".join(filter(None, partes))

def _extraer_gb(texto: str) -> Optional[int]:
    """Extrae cantidad en GB de texto como '16 GB', '512GB', '1 TB'."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*(gb|tb)', texto.lower())
    if not m: return None
    val = float(m.group(1))
    if m.group(2) == 'tb': val *= 1024
    return int(val)

def cumple_specs_detalladas(detalle: dict, categoria: dict) -> Tuple[bool, str]:
    """Verifica generación y specs usando datos completos del item (getItem).
    Revisa los item specifics estructurados Y el texto completo."""
    # Extraer item specifics como diccionario
    aspectos = {}
    for a in detalle.get("localizedAspects", []):
        name = (a.get("name") or "").strip().lower()
        value = (a.get("value") or "").strip()
        if name and value:
            aspectos[name] = value

    procesador = (aspectos.get("processor", "")
                  or aspectos.get("processor model", "")
                  or aspectos.get("processor type", ""))
    ram_str    = (aspectos.get("ram size", "")
                  or aspectos.get("ram", "")
                  or aspectos.get("maximum ram size", ""))
    ssd_str    = (aspectos.get("ssd capacity", "")
                  or aspectos.get("hard drive capacity", "")
                  or aspectos.get("storage capacity", "")
                  or aspectos.get("total storage capacity", ""))

    # --- Verificar GENERACIÓN ---
    texto_completo = extraer_texto_enriquecido(detalle)
    titulo_item = detalle.get("title", "")
    
    # Intentar con el campo procesador primero (más fiable)
    gen_ok = False
    if procesador:
        texto_proc = f"{procesador} {categoria['nombre']}"
        gen_ok, _ = es_generacion_valida(texto_proc, categoria)
    
    # Si no hay campo procesador o falló, intentar con el título original
    if not gen_ok:
        texto_tit = f"{titulo_item} {categoria['nombre']}"
        gen_ok, _ = es_generacion_valida(texto_tit, categoria)
    if not gen_ok:
        return False, "gen_vieja"

    # --- Verificar RAM desde item specifics ---
    if ram_str:
        ram_gb = _extraer_gb(ram_str)
        if ram_gb is not None and ram_gb < 16:
            return False, "sin_ram_ssd"

    # --- Verificar SSD desde item specifics ---
    if ssd_str:
        ssd_gb = _extraer_gb(ssd_str)
        if ssd_gb is not None and ssd_gb < 240:
            return False, "sin_ram_ssd"

    # Si falta RAM o SSD en item specifics, revisar texto completo
    if not ram_str or not ssd_str:
        if not cumple_especificaciones_almacenamiento(texto_completo):
            return False, "sin_ram_ssd"

    # Verificar red flags de descripción (componentes faltantes)
    # NO aplicar EXCLUSION_PATTERN aquí — contiene palabras cosméticas
    # ("chipped", "scratches") que aparecen en plantillas de vendedores legítimos.
    if DESCRIPTION_RED_FLAGS.search(texto_completo):
        return False, "chatarra"

    return True, "ok"

def verificar_descripcion_limpia(config: dict, item_id: str) -> Tuple[bool, str]:
    """Verificación LIGERA: solo checa red flags en la descripción.
    Para items que ya pasaron el filtro de título (gen + specs OK)."""
    detalle = obtener_detalle_item_api(config, item_id)
    if not detalle:
        return True, "ok"  # Sin detalle = aceptar (ya pasó título)

    texto = extraer_texto_enriquecido(detalle)

    # Solo verificar red flags de descripción (componentes faltantes)
    # NO usar EXCLUSION_PATTERN aquí — tiene palabras cosméticas que aparecen
    # en plantillas estándar de vendedores legítimos como Regency Technologies.
    match = DESCRIPTION_RED_FLAGS.search(texto)
    if match:
        return False, f"desc: {match.group(0)[:40]}"

    return True, "ok"

# --- IA: ANÁLISIS INTELIGENTE (Groq + Gemini fallback) ---
_PROMPT_LAPTOP = """Analiza este listing de eBay y decide si es una LAPTOP VÁLIDA para compra/reventa.

TÍTULO: {titulo}
PRECIO: ${precio:.2f}
CONDICIÓN: {condition}

ESPECIFICACIONES:
{specs_text}

DESCRIPCIÓN: {desc_text}

CRITERIOS OBLIGATORIOS (todos deben cumplirse):
1. Es una LAPTOP COMPLETA (no motherboard, no pieza suelta, no accesorio)
2. Procesador MODERNO: Intel 11th Gen+ O AMD Ryzen 4000+
3. RAM >= 16GB (o no especificada pero probable por el modelo)
4. SSD/HDD >= 256GB (o no especificado pero probable por el modelo)
5. NO está marcada como "for parts", "broken", "not working"
6. Incluye cargador/power adapter (o al menos no dice explícitamente que falta)
7. La condición física es aceptable (daño cosmético menor OK, daño funcional NO)

Responde SOLO con una palabra: ACEPTAR o RECHAZAR"""

def _llamar_groq(api_key: str, prompt: str) -> str:
    """Llama a Groq API (Llama 3.3 70B) — ultra rápido y gratuito."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "meta-llama/llama-4-scout-17b-16e-instruct", "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 10, "temperature": 0.1},
        timeout=15
    )
    if resp.status_code != 200:
        return ""
    return resp.json()["choices"][0]["message"]["content"].strip().upper()

def _llamar_gemini(api_key: str, prompt: str) -> str:
    """Llama a Gemini Flash — fallback si Groq falla."""
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 10}},
        timeout=15
    )
    if resp.status_code != 200:
        return ""
    return resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip().upper()

def analizar_con_gemini(config: dict, titulo: str, detalle: dict, precio: float) -> str:
    """Evalúa un listing con IA. Usa Groq (primario) o Gemini (fallback)."""
    groq_key = config.get("groq_api_key", "")
    gemini_key = config.get("gemini_api_key", "")
    if not groq_key and not gemini_key:
        return "RECHAZAR"

    try:
        specs = detalle.get("localizedAspects", [])
        specs_text = "\n".join(f"  {s['name']}: {s['value']}" for s in specs if s.get("name"))
        desc_text = (detalle.get("shortDescription") or "")[:300]
        condition = detalle.get("condition", "Unknown")
        prompt = _PROMPT_LAPTOP.format(titulo=titulo, precio=precio, condition=condition, specs_text=specs_text, desc_text=desc_text)

        # Intentar Groq primero (más rápido, tiene cuota)
        text = ""
        if groq_key:
            text = _llamar_groq(groq_key, prompt)
        # Fallback a Gemini si Groq no respondió
        if not text and gemini_key:
            text = _llamar_gemini(gemini_key, prompt)

        return "ACEPTAR" if "ACEPTAR" in text else "RECHAZAR"
    except Exception as e:
        print(f"    [🤖] Error IA: {e}")
        return "RECHAZAR"

def normalizar_enlace_ebay(enlace: str, base_url: str) -> str:
    enlace = enlace.strip()
    if not enlace: return ""
    enlace_absoluto = urljoin(f"{base_url}/", enlace)
    match = re.search(r"/itm/(?:[^/]+/)?(\d+)", enlace_absoluto)
    if match: return f"{base_url}/itm/{match.group(1)}"
    url = urlparse(enlace_absoluto)
    return urlunparse(url._replace(query="", fragment=""))

# --- SISTEMA PLAYWRIGHT (INTACTO) ---
def guardar_html_debug(contenido: str, ruta: str = "ultimo_bloqueo_ebay.html") -> None:
    with open(ruta, "w", encoding="utf-8") as archivo: archivo.write(contenido)

def asegurar_playwright_disponible() -> None:
    if sync_playwright is None: raise RuntimeError("Falta instalar Playwright. Ejecuta: python -m pip install -r requirements.txt")

def resolver_ruta_navegador(config: dict) -> Optional[str]:
    ruta_configurada = config["browser_executable_path"]
    if ruta_configurada:
        ruta = Path(ruta_configurada).expanduser()
        if not ruta.exists(): raise RuntimeError(f"No existe el navegador configurado: {ruta}")
        return str(ruta)
    for ruta in BROWSER_PATHS_WINDOWS:
        if ruta.exists(): return str(ruta)
    return None

def es_pagina_intervencion_ebay(url: str, contenido: str) -> bool:
    url_lower, contenido_lower = url.lower(), contenido.lower()
    return any(token in url_lower or token in contenido_lower for token in INTERVENCION_TOKENS)

def obtener_headers_publicos() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Cache-Control": "max-age=0", "Pragma": "no-cache",
    }

def obtener_html_publico(url: str, max_reintentos: int) -> str:
    ultimo_error: Optional[Exception] = None
    for intento in range(max_reintentos):
        try:
            respuesta = requests.get(url, headers=obtener_headers_publicos(), timeout=30)
            respuesta.raise_for_status()
            return respuesta.text
        except requests.RequestException as error:
            ultimo_error = error
            if intento == max_reintentos - 1: break
            time.sleep((intento + 1) * 2)
    raise RuntimeError(f"No se pudo obtener HTML publico: {ultimo_error}")

class EbayBrowser:
    def __init__(self, config: dict) -> None:
        asegurar_playwright_disponible()
        self.config = config
        self._playwright: Optional[Playwright] = None
        self.context = None
        self.page: Optional[Page] = None
        self.browser_path = resolver_ruta_navegador(config)
        self.profile_dir = Path(config["browser_profile_dir"]).expanduser().resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._iniciar()

    def _iniciar(self) -> None:
        self._playwright = sync_playwright().start()
        launch_kwargs = {
            "headless": self.config["browser_headless"], "viewport": None, "locale": "en-US",
            "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
        }
        if self.browser_path: launch_kwargs["executable_path"] = self.browser_path
        elif self.config["browser_channel"]: launch_kwargs["channel"] = self.config["browser_channel"]

        self.context = self._playwright.chromium.launch_persistent_context(str(self.profile_dir), **launch_kwargs)
        self.context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(self.config["browser_timeout_ms"])

    def close(self) -> None:
        if self.context: self.context.close(); self.context = None
        if self._playwright: self._playwright.stop(); self._playwright = None

    def _pedir_intervencion_usuario(self, url_objetivo: str, contenido: str) -> str:
        guardar_html_debug(contenido)
        if not sys.stdin.isatty(): raise EbayChallengeError("eBay pidio verificacion manual en modo no interactivo.")
        print("    [!] eBay abrio un challenge. Resuelvelo en el navegador.")
        while True:
            input("    [>] Cuando termines, presiona Enter para reintentar...")
            self.page.goto(url_objetivo, wait_until="domcontentloaded", timeout=self.config["browser_timeout_ms"])
            self.page.wait_for_timeout(self.config["browser_settle_ms"])
            contenido = self.page.content()
            if not es_pagina_intervencion_ebay(self.page.url, contenido): return contenido

    def obtener_html(self, url: str) -> str:
        ultimo_error: Optional[Exception] = None
        for intento in range(self.config["max_reintentos"]):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=self.config["browser_timeout_ms"])
                self.page.wait_for_timeout(self.config["browser_settle_ms"])
                contenido = self.page.content()
                if es_pagina_intervencion_ebay(self.page.url, contenido): contenido = self._pedir_intervencion_usuario(url, contenido)
                try:
                    self.page.wait_for_selector("li.s-item, .s-item__wrapper", timeout=self.config["browser_results_wait_ms"])
                    self.page.wait_for_timeout(1000)
                except PlaywrightError: pass
                contenido = self.page.content()
                if es_pagina_intervencion_ebay(self.page.url, contenido): contenido = self._pedir_intervencion_usuario(url, contenido)
                return contenido
            except EbayChallengeError: raise
            except PlaywrightError as error:
                ultimo_error = error
                if intento == self.config["max_reintentos"] - 1: break
                time.sleep((intento + 1) * 5)
        raise RuntimeError(f"No se pudo cargar la pagina en el navegador: {ultimo_error}")

def obtener_items_resultado(sopa: BeautifulSoup) -> List[Tag]:
    return sopa.select("li.s-item") or sopa.select("li.s-card") or sopa.select(".s-item__wrapper")

def es_pagina_sin_resultados(sopa: BeautifulSoup) -> bool:
    encabezado = sopa.select_one("h1")
    return bool(encabezado and ("0 resultados para" in limpiar_texto(encabezado.get_text(" ", strip=True)).lower() or "0 results for" in limpiar_texto(encabezado.get_text(" ", strip=True)).lower()))

def extraer_oferta_desde_item(item: Tag, base_url: str, categoria: dict, max_precio: float, enlaces_excluidos: Set[str]) -> Tuple[Optional[OfertaLaptop], str]:
    titulo_tag = item.select_one(".s-item__title") or item.select_one(".s-card__title")
    precio_tag = item.select_one(".s-item__price") or item.select_one(".s-card__price")
    enlace_tag = item.select_one(".s-item__link") or item.select_one("a.s-card__link")
    img_tag = item.select_one(".s-item__image-img")
    time_tag = item.select_one(".s-item__time-left") or item.select_one(".s-item__time-end")

    if not titulo_tag or not precio_tag or not enlace_tag: return None, "sin_datos"

    titulo = limpiar_texto(titulo_tag.get_text(" ", strip=True)).replace("Se abre en una ventana nueva", "").strip()
    
    if not titulo or titulo.lower() == "shop on ebay" or not es_titulo_valido(titulo): return None, "chatarra"
    titulo_pasa_gen, _ = es_generacion_valida(titulo, categoria)
    if not titulo_pasa_gen: return None, "gen_vieja"
    if not cumple_especificaciones_almacenamiento(titulo): return None, "sin_ram_ssd"

    precio_texto = limpiar_texto(precio_tag.get_text(" ", strip=True))
    precio = extraer_precio(precio_texto)
    if precio is None or precio > max_precio: return None, "precio_alto"

    enlace = normalizar_enlace_ebay(enlace_tag.get("href", ""), base_url)
    if not enlace: return None, "enlace_roto"
    if enlace in enlaces_excluidos: return None, "duplicado"

    estado_tag = item.select_one(".SECONDARY_INFO") or item.select_one(".s-item__subtitle")
    estado = limpiar_texto(estado_tag.get_text(" ", strip=True)) if estado_tag else "No especificado"
    
    imagen_url = img_tag.get("src", "") if img_tag else ""
    es_subasta = bool(time_tag)
    tiempo_restante = time_tag.get_text(strip=True) if es_subasta else ""

    return OfertaLaptop(
        categoria["nombre"], estado, titulo, precio, precio_texto,
        enlace, imagen_url, es_subasta, tiempo_restante, ""
    ), "ok"

# --- TELEGRAM ---
def enviar_telegram_texto(token: str, chat_id: str, mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, json=payload, timeout=30)
    except: pass

def enviar_telegram_foto(token: str, chat_id: str, oferta: OfertaLaptop) -> None:
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    titulo_limpio = html.escape(oferta.titulo)
    
    caption = (
        f"💻 <b>{titulo_limpio}</b>\n\n"
        f"✨ <b>Estado:</b> {html.escape(oferta.estado)}\n"
        f"⚙️ <b>CPU:</b> {oferta.procesador}\n"
        f"💰 <b>Precio:</b> {html.escape(oferta.precio_texto)}\n"
    )
    
    vendedor_limpio = oferta.vendedor.strip()
    if vendedor_limpio:
        if vendedor_limpio.lower() == "regencytechnologies":
            caption += f"⭐ <b>Vendedor:</b> {html.escape(vendedor_limpio)} (¡Prioridad!)\n"
        else:
            caption += f"🏢 <b>Vendedor:</b> {html.escape(vendedor_limpio)}\n"
    
    if oferta.es_subasta:
        caption += f"⏳ <b>SUBASTA:</b> {oferta.tiempo_restante} restantes\n"
        
    caption += f"\n🔗 <a href='{oferta.enlace}'>COMPRAR EN EBAY</a>"
    
    if not oferta.imagen:
        enviar_telegram_texto(token, chat_id, caption)
        return

    payload = {"chat_id": chat_id, "photo": oferta.imagen, "caption": caption, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except:
        enviar_telegram_texto(token, chat_id, caption)

# --- API DE EBAY CON SUBASTAS HABILITADAS ---
_EBAY_TOKEN_CACHE: dict = {}

def _ebay_basic_auth_header(client_id: str, client_secret: str) -> str:
    cred = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(cred).decode("ascii")

def obtener_token_ebay_app(config: dict) -> str:
    ahora = int(time.time())
    if _EBAY_TOKEN_CACHE.get("access_token") and ahora < _EBAY_TOKEN_CACHE.get("expires_at", 0) - 60:
        return _EBAY_TOKEN_CACHE["access_token"]

    client_id = config["ebay_client_id"]
    client_secret = config["ebay_client_secret"]
    
    if not client_id or not client_secret: raise RuntimeError("Faltan credenciales API eBay")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _ebay_basic_auth_header(client_id, client_secret),
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    resp = requests.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    _EBAY_TOKEN_CACHE["access_token"] = payload["access_token"]
    _EBAY_TOKEN_CACHE["expires_at"] = ahora + int(payload.get("expires_in", 7200))
    return _EBAY_TOKEN_CACHE["access_token"]

# Límites de verificación por búsqueda (respetar rate limits API)
MAX_VERIFY_CHECKS = 15    # Verificar descripciones de items que pasaron título
MAX_RESCUE_CHECKS = 40    # Rescatar items que fallaron título (muchos no ponen modelo en título)

def buscar_ofertas_categoria_api(config: dict, categoria: dict, marca: str, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    nombre_limpio = categoria['nombre'].replace("Intel ", "").strip()
    encabezado = f"{marca} {categoria['nombre']}"
    q = f"{marca} {nombre_limpio}"
    print(f"\n[?] (API) Buscando: {encabezado}... Q: {q}")

    try:
        token = obtener_token_ebay_app(config)
        filtros = f"conditionIds:{{1000|1500|2000|2501|2502|2500|3000}},price:[..{config['max_precio']}],priceCurrency:{config['ebay_currency']},buyingOptions:{{FIXED_PRICE|BEST_OFFER|AUCTION}}"
        headers = {
            "Authorization": f"Bearer {token}", "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
        }
        # Doble búsqueda: nuevos + baratos (para atrapar subastas)
        # Categoría 175672 = Laptops & Netbooks (filtra sin necesidad de "laptop" en título)
        items_vistos = set()
        items = []
        for sort_method in ["newlyListed", "price"]:
            for offset in ["0", "200"]:  # Paginación: traer hasta 400 items por sort
                params = {"q": q, "category_ids": "175672", "limit": "200", "offset": offset, "sort": sort_method, "filter": filtros}
                resp = requests.get("https://api.ebay.com/buy/browse/v1/item_summary/search", headers=headers, params=params, timeout=30)
                data = resp.json()
                
                summaries = data.get("itemSummaries") or []
                for it in summaries:
                    item_id = it.get("itemId", "")
                    if item_id and item_id not in items_vistos:
                        items_vistos.add(item_id)
                        items.append(it)
                time.sleep(0.3)
                if len(summaries) < 200:
                    break  # No hay más páginas
    except Exception as e:
        print(f"  [!] Falló llamada API: {e}")
        return []

    ofertas: List[OfertaLaptop] = []
    rechazos = {"chatarra": 0, "gen_vieja": 0, "sin_ram_ssd": 0, "precio_alto": 0, "duplicado": 0}
    # Ejemplos de títulos rechazados (máx 3 por razón) para depuración
    ejemplos_rechazo: dict = {"chatarra": [], "gen_vieja": [], "sin_ram_ssd": [], "precio_alto": [], "duplicado": []}
    MAX_EJEMPLOS = 3
    # Candidatos separados para verificación y rescate
    candidatos_verificar: List[dict] = []   # Pasaron título → verificar descripción
    candidatos_rescatar: List[dict] = []    # Fallaron título → intentar rescate

    # ══════════════════════════════════════════════════════════════════════
    # PASE 1: Filtro rápido por título (sin llamadas extra a la API)
    # ══════════════════════════════════════════════════════════════════════
    for it in items:
        titulo = (it.get("title") or "").strip()

        if not es_titulo_valido(titulo):
            rechazos["chatarra"] += 1
            if len(ejemplos_rechazo["chatarra"]) < MAX_EJEMPLOS:
                # Mostrar qué palabra del filtro lo atrapó
                match = EXCLUSION_PATTERN.search(titulo)
                palabra = match.group(0) if match else "?"
                ejemplos_rechazo["chatarra"].append(f'"{titulo[:70]}" → [{palabra}]')
            continue

        price_obj = it.get("price") or {}
        currency = price_obj.get("currency") or config["ebay_currency"]
        precio_raw = price_obj.get("value")
        # Subastas puras no tienen "price" — usar currentBidPrice como fallback
        if precio_raw is None:
            bid_price = it.get("currentBidPrice", {}).get("value")
            precio_raw = bid_price
        try: precio = float(precio_raw)
        except: precio = 0.01  # Subastas sin precio conocido → aceptar para no perderlas
        precio_texto = f"{currency} {precio:.2f}" if precio > 0.01 else f"{currency} (subasta)"
        if precio > config["max_precio"]:
            rechazos["precio_alto"] += 1
            if len(ejemplos_rechazo["precio_alto"]) < MAX_EJEMPLOS:
                ejemplos_rechazo["precio_alto"].append(f'"{titulo[:60]}" → ${precio:.0f}')
            continue

        enlace = normalizar_enlace_ebay((it.get("itemWebUrl") or "").strip(), config["ebay_site"])
        if not enlace or enlace in enlaces_excluidos:
            rechazos["duplicado"] += 1; continue

        # Verificar gen + specs por título
        titulo_pasa_gen, es_gen_explicita = es_generacion_valida(titulo, categoria)
        titulo_pasa_specs = cumple_especificaciones_almacenamiento(titulo)

        if not titulo_pasa_gen and es_gen_explicita:
            # Es explícitamente una generación vieja, rechazar de inmediato sin gastar API
            rechazos["gen_vieja"] += 1
            if len(ejemplos_rechazo["gen_vieja"]) < MAX_EJEMPLOS:
                ejemplos_rechazo["gen_vieja"].append(f'"{titulo[:70]}" → [título: gen_vieja]')
            continue

        item_data = {
            "item_id": it.get("itemId", ""),
            "titulo": titulo, "precio": precio, "precio_texto": precio_texto,
            "enlace": enlace,
            "estado": (it.get("condition") or "No especificado").strip() or "No especificado",
            "imagen_url": it.get("image", {}).get("imageUrl", ""),
            "buying_options": it.get("buyingOptions", []),
            "item_end_date": it.get("itemEndDate", ""),
        }

        if titulo_pasa_gen and titulo_pasa_specs:
            candidatos_verificar.append(item_data)
        else:
            razon = "gen_vieja" if not titulo_pasa_gen else "sin_ram_ssd"
            item_data["razon_titulo"] = razon
            candidatos_rescatar.append(item_data)

    # ══════════════════════════════════════════════════════════════════════
    # PASE 2: Verificar descripciones de items que PASARON título
    #         (atrapar motherboards, sin batería, sin SSD, BIOS lock, etc.)
    # ══════════════════════════════════════════════════════════════════════
    rechazados_desc = 0
    max_verificar = min(len(candidatos_verificar), MAX_VERIFY_CHECKS)
    if candidatos_verificar:
        print(f"  [🛡️] Verificando descripción de {max_verificar} items que pasaron título...")

    for cand in candidatos_verificar[:MAX_VERIFY_CHECKS]:
        es_subasta = "AUCTION" in cand["buying_options"]
        tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
        item_id = cand["item_id"]

        if item_id:
            limpia, razon_desc = verificar_descripcion_limpia(config, item_id)
            if not limpia:
                rechazos["chatarra"] += 1
                rechazados_desc += 1
                if len(ejemplos_rechazo["chatarra"]) < MAX_EJEMPLOS:
                    ejemplos_rechazo["chatarra"].append(f'"{cand["titulo"][:55]}" → [{razon_desc}]')
                time.sleep(0.3)
                continue
            time.sleep(0.3)

        ofertas.append(OfertaLaptop(
            categoria["nombre"], cand["estado"], cand["titulo"],
            cand["precio"], cand["precio_texto"], cand["enlace"],
            cand["imagen_url"], es_subasta, tiempo_restante,
            cand.get("seller", "")
        ))

    # Items que no se pudieron verificar (exceso de límite) → aceptar por título
    for cand in candidatos_verificar[MAX_VERIFY_CHECKS:]:
        es_subasta = "AUCTION" in cand["buying_options"]
        tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
        ofertas.append(OfertaLaptop(
            categoria["nombre"], cand["estado"], cand["titulo"],
            cand["precio"], cand["precio_texto"], cand["enlace"],
            cand["imagen_url"], es_subasta, tiempo_restante,
            cand.get("seller", "")
        ))

    # ══════════════════════════════════════════════════════════════════════
    # PASE 3: Rescatar items que FALLARON título (verificación completa)
    #         Con Gemini AI como segundo filtro inteligente
    # ══════════════════════════════════════════════════════════════════════
    rescatados = 0
    verificados_rescate = 0
    max_rescatar = min(len(candidatos_rescatar), MAX_RESCUE_CHECKS)
    if candidatos_rescatar:
        print(f"  [🔍] {len(candidatos_rescatar)} candidatos para rescate (revisando {max_rescatar})...")

    for cand in candidatos_rescatar[:MAX_RESCUE_CHECKS]:
        item_id = cand["item_id"]
        if not item_id:
            rechazos[cand["razon_titulo"]] += 1; continue

        verificados_rescate += 1
        detalle = obtener_detalle_item_api(config, item_id)

        if not detalle:
            rechazos[cand["razon_titulo"]] += 1
            if len(ejemplos_rechazo[cand["razon_titulo"]]) < MAX_EJEMPLOS:
                ejemplos_rechazo[cand["razon_titulo"]].append(f'"{cand["titulo"][:70]}" → [sin detalle API]')
            continue

        pasa, razon = cumple_specs_detalladas(detalle, categoria)

        # Si el regex lo rechaza pero tiene Gemini disponible, pedir segunda opinión
        if not pasa and config.get("gemini_api_key"):
            veredicto_ia = analizar_con_gemini(config, cand["titulo"], detalle, cand["precio"])
            if veredicto_ia == "ACEPTAR":
                pasa = True
                razon = "ok"
                print(f"    [🤖] Gemini RESCATÓ: {cand['titulo'][:60]}")

        if pasa:
            es_subasta = "AUCTION" in cand["buying_options"]
            tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
            titulo_det = (detalle.get("title") or cand["titulo"]).strip()
            ofertas.append(OfertaLaptop(
                categoria["nombre"], cand["estado"], titulo_det,
                cand["precio"], cand["precio_texto"], cand["enlace"],
                cand["imagen_url"], es_subasta, tiempo_restante,
                cand.get("seller", "")
            ))
            rescatados += 1
        else:
            rechazos[razon] += 1
            if len(ejemplos_rechazo[razon]) < MAX_EJEMPLOS:
                ejemplos_rechazo[razon].append(f'"{cand["titulo"][:70]}" → [detalle: {razon}]')

        time.sleep(0.3)
    # Los que no se verificaron en rescate → contar como rechazo
    for cand in candidatos_rescatar[MAX_RESCUE_CHECKS:]:
        rechazos[cand["razon_titulo"]] += 1
        if len(ejemplos_rechazo[cand["razon_titulo"]]) < MAX_EJEMPLOS:
            ejemplos_rechazo[cand["razon_titulo"]].append(f'"{cand["titulo"][:70]}" → [no verificado]')

    # ══════════════════════════════════════════════════════════════════════
    # Reporte con ejemplos de rechazos
    # ══════════════════════════════════════════════════════════════════════
    print(f"  [-] De {len(items)} items analizados:")

    for razon, etiqueta in [
        ("gen_vieja", "Generación vieja/sin modelo"),
        ("sin_ram_ssd", "RAM mala <16GB o SSD <256GB"),
        ("chatarra", "Daños/piezas/accesorios/desc"),
        ("precio_alto", f"Precio > ${config['max_precio']}"),
        ("duplicado", "Duplicados/ya enviados"),
    ]:
        count = rechazos[razon]
        if count == 0: continue
        print(f"      -> {count} descartados ({etiqueta})")
        for ej in ejemplos_rechazo[razon]:
            print(f"         · {ej}")

    if rechazados_desc > 0:
        print(f"      -> 🛡️ {rechazados_desc} eliminados por descripción sospechosa")
    if rescatados > 0:
        print(f"      -> 🔍 {rescatados} RESCATADOS gracias a descripción/specs ({verificados_rescate} verificados)")
    print(f"      -> ✅ {len(ofertas)} pasaron TODOS los filtros.")
    if ofertas:
        for o in ofertas:
            seller_tag = f" [⭐ {o.vendedor}]" if o.vendedor.lower() == "regencytechnologies" else (f" [{o.vendedor}]" if o.vendedor else "")
            print(f"         🟢 {o.titulo} -> {o.precio_texto}{seller_tag}")

    ofertas.sort(key=lambda x: x.precio)
    return ofertas

def buscar_ofertas_categoria_scraping(browser: Optional[EbayBrowser], config: dict, categoria: dict, marca: str, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    condiciones = "1000%7C1500%7C2000%7C2500%7C2501%7C2502%7C2503%7C3000%7C4000%7C5000%7C6000"
    nombre_limpio = categoria['nombre'].replace("Intel ", "").strip()
    query = f"{marca} {nombre_limpio} laptop"
    url = f"{config['ebay_site']}/sch/i.html?_nkw={quote_plus(query)}&_sacat=0&LH_ItemCondition={condiciones}&_ipg=240&_sop=15"
    
    print(f"\n[?] Buscando: {marca} {categoria['nombre']}... URL: {url}")
    html_busqueda = obtener_html_publico(url, config["max_reintentos"])
    
    if es_pagina_intervencion_ebay(url, html_busqueda):
        if config["use_browser_fallback"] and browser:
            html_busqueda = browser.obtener_html(url)
        else: return []
    
    sopa = BeautifulSoup(html_busqueda, "html.parser")
    if es_pagina_sin_resultados(sopa): return []
    
    items = obtener_items_resultado(sopa)
    ofertas: List[OfertaLaptop] = []
    enlaces_vistos = set(enlaces_excluidos)
    rechazos = {"chatarra": 0, "gen_vieja": 0, "sin_ram_ssd": 0, "precio_alto": 0, "duplicado": 0}

    for item in items:
        oferta, razon = extraer_oferta_desde_item(item, config["ebay_site"], categoria, config["max_precio"], enlaces_vistos)
        if oferta:
            enlaces_vistos.add(oferta.enlace)
            ofertas.append(oferta)
        elif razon in rechazos:
            rechazos[razon] += 1

    print(f"  [-] De {len(items)} items analizados (Scraping):")
    print(f"      -> {rechazos['gen_vieja']} descartados (Gen vieja)")
    print(f"      -> {rechazos['sin_ram_ssd']} descartados (Sin RAM/SSD)")
    print(f"      -> {rechazos['chatarra']} descartados (Chatarra)")
    print(f"      -> {len(ofertas)} pasaron TODOS los filtros.")
    if ofertas:
        print("         " + "\n         ".join(f"🟢 {o.titulo} -> {o.precio_texto}" for o in ofertas))

    return ofertas

def dormir_entre_busquedas(config: dict) -> None:
    time.sleep(random.uniform(config["sleep_min_seconds"], config["sleep_max_seconds"]))

# --- VENDEDORES PRIORITARIOS ---
VENDEDORES_PRIORITARIOS = ["regencytechnologies"]

def buscar_vendedores_prioritarios(config: dict, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    """Busca directamente en las tiendas de vendedores prioritarios.
    Esto asegura que atrapemos TODAS sus publicaciones, no solo las que
    eBay decide mostrar en búsquedas genéricas."""
    todas_ofertas: List[OfertaLaptop] = []

    for vendedor in VENDEDORES_PRIORITARIOS:
        print(f"\n[⭐] Monitoreando tienda de vendedor prioritario: {vendedor}...")
        try:
            token = obtener_token_ebay_app(config)
            headers = {
                "Authorization": f"Bearer {token}", "Accept": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
            }
            # Buscar laptops del vendedor en la categoría Laptops & Netbooks
            filtros = (
                f"conditionIds:{{1000|1500|2000|2501|2502|2500|3000}},"
                f"buyingOptions:{{FIXED_PRICE|BEST_OFFER|AUCTION}},"
                f"sellers:{{{vendedor}}}"
            )
            items_vistos = set()
            items = []
            for sort_method in ["newlyListed", "price"]:
                for offset in ["0", "200"]:
                    params = {
                        "q": "laptop",
                        "category_ids": "175672",
                        "limit": "200",
                        "offset": offset,
                        "sort": sort_method,
                        "filter": filtros,
                    }
                    resp = requests.get(
                        "https://api.ebay.com/buy/browse/v1/item_summary/search",
                        headers=headers, params=params, timeout=30
                    )
                    data = resp.json()
                    summaries = data.get("itemSummaries") or []
                    for it in summaries:
                        item_id = it.get("itemId", "")
                        if item_id and item_id not in items_vistos:
                            items_vistos.add(item_id)
                            items.append(it)
                    time.sleep(0.3)
                    if len(summaries) < 200:
                        break

            aceptados = 0
            rechazados_total = 0
            for it in items:
                titulo = (it.get("title") or "").strip()
                if not titulo or not es_titulo_valido(titulo):
                    rechazados_total += 1
                    continue

                # Precio (con soporte para subastas sin precio)
                price_obj = it.get("price") or {}
                currency = price_obj.get("currency") or config["ebay_currency"]
                precio_raw = price_obj.get("value")
                if precio_raw is None:
                    bid_price = it.get("currentBidPrice", {}).get("value")
                    precio_raw = bid_price
                try: precio = float(precio_raw)
                except: precio = 0.01
                precio_texto = f"{currency} {precio:.2f}" if precio > 0.01 else f"{currency} (subasta)"

                enlace = normalizar_enlace_ebay((it.get("itemWebUrl") or "").strip(), config["ebay_site"])
                if not enlace or enlace in enlaces_excluidos:
                    continue

                # Verificar generación en CUALQUIER categoría
                gen_ok = False
                cat_match = None
                for cat in CATEGORIAS_BUSQUEDA:
                    ok, explicita = es_generacion_valida(titulo, cat)
                    if ok:
                        gen_ok = True
                        cat_match = cat
                        break
                    elif explicita:
                        break  # Explícitamente vieja, no seguir

                if not gen_ok:
                    rechazados_total += 1
                    continue

                if not cumple_especificaciones_almacenamiento(titulo):
                    rechazados_total += 1
                    continue

                es_subasta = "AUCTION" in it.get("buyingOptions", [])
                tiempo_restante = calcular_tiempo_restante(it.get("itemEndDate", "")) if es_subasta else ""
                seller = it.get("seller", {}).get("username", vendedor)

                todas_ofertas.append(OfertaLaptop(
                    cat_match["nombre"] if cat_match else "?",
                    (it.get("condition") or "Used").strip(),
                    titulo, precio, precio_texto, enlace,
                    it.get("image", {}).get("imageUrl", ""),
                    es_subasta, tiempo_restante, seller
                ))
                aceptados += 1

            print(f"  [⭐] {vendedor}: {len(items)} items encontrados, {aceptados} pasaron filtros, {rechazados_total} rechazados.")

        except Exception as e:
            print(f"  [!] Error monitoreando {vendedor}: {e}")

    return todas_ofertas

# --- LÓGICA PRINCIPAL AGRUPADA ---
def ejecutar_ciclo(config: dict, browser: Optional[EbayBrowser]) -> bool:
    enviadas = cargar_ofertas_enviadas()
    reportadas_en_ciclo: Set[str] = set()
    hubo_ofertas = False

    print("Iniciando busqueda agrupada por marca hacia Telegram...")

    # ═══════════════════════════════════════════════════════════════
    # PASO 0: Monitorear vendedores prioritarios (ej: regencytechnologies)
    # ═══════════════════════════════════════════════════════════════
    ofertas_prioritarias = buscar_vendedores_prioritarios(config, enviadas | reportadas_en_ciclo)
    if ofertas_prioritarias:
        ofertas_prioritarias.sort(key=lambda x: x.precio)
        print(f"\n  [⭐] {len(ofertas_prioritarias)} ofertas de vendedores prioritarios. Enviando a Telegram...")

        if not config["dry_run"]:
            encabezado = f"⭐ <b>VENDEDORES PRIORITARIOS | {len(ofertas_prioritarias)} OFERTAS</b> ⭐"
            for tok, cid in _todos_los_destinos(config):
                enviar_telegram_texto(tok, cid, encabezado)
            time.sleep(1)

            for oferta in ofertas_prioritarias:
                for tok, cid in _todos_los_destinos(config):
                    enviar_telegram_foto(tok, cid, oferta)
                reportadas_en_ciclo.add(oferta.enlace)
                time.sleep(1.5)

            enviadas.update(reportadas_en_ciclo)
            hubo_ofertas = True

    # ═══════════════════════════════════════════════════════════════
    # PASO 1: Búsqueda normal por marca + categoría
    # ═══════════════════════════════════════════════════════════════
    for marca in config["marcas"]:
        print(f"\n[*] Recolectando ofertas para la marca: {marca.upper()}...")
        ofertas_marca_acumuladas = []

        for categoria in CATEGORIAS_BUSQUEDA:
            try:
                if config.get("use_ebay_api"):
                    ofertas = buscar_ofertas_categoria_api(config, categoria, marca, enviadas | reportadas_en_ciclo)
                else:
                    ofertas = buscar_ofertas_categoria_scraping(browser, config, categoria, marca, enviadas | reportadas_en_ciclo)
                    
                if ofertas: ofertas_marca_acumuladas.extend(ofertas)
                dormir_entre_busquedas(config)
            except EbayChallengeError as error:
                print(f"  [!] El proceso se detiene por bloqueo de eBay: {error}")
                return False
            except Exception as error:
                print(f"  [!] Error inesperado en {marca} {categoria['nombre']}: {error}")
                time.sleep(5)

        if ofertas_marca_acumuladas:
            # Ordenar primero por vendedor (regencytechnologies), luego por precio
            ofertas_marca_acumuladas.sort(key=lambda x: (x.vendedor.lower() != "regencytechnologies", x.precio))
            
            print(f"  [+] {len(ofertas_marca_acumuladas)} oferta(s) encontradas. Enviando a Telegram...")
            
            if not config["dry_run"]:
                encabezado = f"🔥 <b>TOP {len(ofertas_marca_acumuladas)} ENCONTRADAS | {marca.upper()}</b> 🔥"
                for tok, cid in _todos_los_destinos(config):
                    enviar_telegram_texto(tok, cid, encabezado)
                time.sleep(1)
                
                for oferta in ofertas_marca_acumuladas:
                    for tok, cid in _todos_los_destinos(config):
                        enviar_telegram_foto(tok, cid, oferta)
                    reportadas_en_ciclo.add(oferta.enlace)
                    time.sleep(1.5) 
                
                enviadas.update(reportadas_en_ciclo)
                hubo_ofertas = True

    if hubo_ofertas and not config["dry_run"]:
        guardar_ofertas_enviadas(enviadas)

    if not hubo_ofertas: print("\nCiclo completado sin ofertas nuevas.")
    return True

def main() -> None:
    config = obtener_configuracion()
    if not config["telegram_token"] or not config["telegram_chat_ids"]:
        print("❌ Error: Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el archivo .env")
        return

    # Usar 8 horas por defecto si no se especifica
    horas = float(os.getenv("INTERVALO_HORAS", "8.0"))
    intervalo_segundos = max(1, int(horas * 3600))
    if config["dry_run"]: print("DRY_RUN activo: no se enviaran mensajes reales.")

    browser: Optional[EbayBrowser] = None
    if config.get("use_ebay_api") and config.get("ebay_client_id"):
        print("Modo API activo: usando eBay Browse API.")
    elif config["use_browser_fallback"]:
        browser = EbayBrowser(config)
    else:
        print("Modo publico activo.")

    try:
        if config["run_once"]:
            ejecutar_ciclo(config, browser)
            return
            
        print(f"Bot iniciado. Ejecutando cada {horas} horas. La base de datos se reseteará cada 24 horas.")
        ultimo_reseteo = time.time()
        
        while True:
            # Reseteo de la BD cada 24 horas
            if time.time() - ultimo_reseteo >= 24 * 3600:
                print("🔄 Han pasado 24 horas. Reseteando la base de datos de envíos para permitir repeticiones...")
                if os.path.exists("enlaces_enviados.json"):
                    try:
                        os.remove("enlaces_enviados.json")
                    except Exception as e:
                        print(f"No se pudo borrar la BD: {e}")
                ultimo_reseteo = time.time()
                
            continuar = ejecutar_ciclo(config, browser)
            if not continuar: return
            time.sleep(intervalo_segundos)
    finally:
        if browser is not None: browser.close()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nProceso interrumpido.")