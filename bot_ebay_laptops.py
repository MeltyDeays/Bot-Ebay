import base64
import html
import json
import os
import random
import re
import sys
import time
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

ESTADOS_BUSQUEDA = [
    {"nombre": "Nuevo", "condition_id": "1000"},
    {"nombre": "Open Box", "condition_id": "1500"},
    {"nombre": "Certificado - Renovado", "condition_id": "2000"},
    {"nombre": "Excelente - Renovado", "condition_id": "2501"},
    {"nombre": "Muy Bueno - Renovado", "condition_id": "2502"},
    {"nombre": "Bueno - Renovado", "condition_id": "2503"},
    {"nombre": "Vendedor - Renovado", "condition_id": "2500"},
    {"nombre": "Usado", "condition_id": "3000"},
]

FILTROS_CPU = [
    {"nombre": "Ryzen 3 4300U", "query": "ryzen 3 4300u"},
    {"nombre": "Ryzen 3 5300U", "query": "ryzen 3 5300u"},
    {"nombre": "Ryzen 3 5425U", "query": "ryzen 3 5425u"},
    {"nombre": "Ryzen 3 7320U", "query": "ryzen 3 7320u"},
    {"nombre": "Ryzen 3 7330U", "query": "ryzen 3 7330u"},
    {"nombre": "Ryzen 3 8340U", "query": "ryzen 3 8340u"},
    {"nombre": "Ryzen 5 4500U", "query": "ryzen 5 4500u"},
    {"nombre": "Ryzen 5 4600H", "query": "ryzen 5 4600h"},
    {"nombre": "Ryzen 5 5500U", "query": "ryzen 5 5500u"},
    {"nombre": "Ryzen 5 5600H", "query": "ryzen 5 5600h"},
    {"nombre": "Ryzen 5 5625U", "query": "ryzen 5 5625u"},
    {"nombre": "Ryzen 5 6600U", "query": "ryzen 5 6600u"},
    {"nombre": "Ryzen 5 6600H", "query": "ryzen 5 6600h"},
    {"nombre": "Ryzen 5 7520U", "query": "ryzen 5 7520u"},
    {"nombre": "Ryzen 5 7530U", "query": "ryzen 5 7530u"},
    {"nombre": "Ryzen 5 7640HS", "query": "ryzen 5 7640hs"},
    {"nombre": "Ryzen 5 8540U", "query": "ryzen 5 8540u"},
    {"nombre": "Ryzen 5 8640HS", "query": "ryzen 5 8640hs"},
    {"nombre": "Ryzen 7 4700U", "query": "ryzen 7 4700u"},
    {"nombre": "Ryzen 7 4800H", "query": "ryzen 7 4800h"},
    {"nombre": "Ryzen 7 5700U", "query": "ryzen 7 5700u"},
    {"nombre": "Ryzen 7 5800H", "query": "ryzen 7 5800h"},
    {"nombre": "Ryzen 7 5825U", "query": "ryzen 7 5825u"},
    {"nombre": "Ryzen 7 6800U", "query": "ryzen 7 6800u"},
    {"nombre": "Ryzen 7 6800H", "query": "ryzen 7 6800h"},
    {"nombre": "Ryzen 7 7730U", "query": "ryzen 7 7730u"},
    {"nombre": "Ryzen 7 7840U", "query": "ryzen 7 7840u"},
    {"nombre": "Ryzen 7 7840HS", "query": "ryzen 7 7840hs"},
    {"nombre": "Ryzen 7 8840HS", "query": "ryzen 7 8840hs"},
    {"nombre": "Ryzen 7 8845HS", "query": "ryzen 7 8845hs"},
    {"nombre": "Ryzen 9 5900HX", "query": "ryzen 9 5900hx"},
    {"nombre": "Ryzen 9 6900HX", "query": "ryzen 9 6900hx"},
    {"nombre": "Ryzen 9 7940HS", "query": "ryzen 9 7940hs"},
    {"nombre": "Ryzen 9 7945HX", "query": "ryzen 9 7945hx"},
    {"nombre": "Ryzen 9 8945HS", "query": "ryzen 9 8945hs"},
    {"nombre": "i3-1115G4", "query": "i3-1115g4"},
    {"nombre": "i3-1215U", "query": "i3-1215u"},
    {"nombre": "i3-1315U", "query": "i3-1315u"},
    {"nombre": "i5-1135G7", "query": "i5-1135g7"},
    {"nombre": "i5-11400H", "query": "i5-11400h"},
    {"nombre": "i5-1235U", "query": "i5-1235u"},
    {"nombre": "i5-12450H", "query": "i5-12450h"},
    {"nombre": "i5-12500H", "query": "i5-12500h"},
    {"nombre": "i5-1335U", "query": "i5-1335u"},
    {"nombre": "i5-13420H", "query": "i5-13420h"},
    {"nombre": "i5-13500H", "query": "i5-13500h"},
    {"nombre": "Ultra 5 125H", "query": "ultra 5 125h"},
    {"nombre": "i7-1165G7", "query": "i7-1165g7"},
    {"nombre": "i7-11800H", "query": "i7-11800h"},
    {"nombre": "i7-1255U", "query": "i7-1255u"},
    {"nombre": "i7-1260P", "query": "i7-1260p"},
    {"nombre": "i7-12700H", "query": "i7-12700h"},
    {"nombre": "i7-1355U", "query": "i7-1355u"},
    {"nombre": "i7-13620H", "query": "i7-13620h"},
    {"nombre": "i7-13700H", "query": "i7-13700h"},
    {"nombre": "Ultra 7 155H", "query": "ultra 7 155h"},
    {"nombre": "i9-11900H", "query": "i9-11900h"},
    {"nombre": "i9-12900H", "query": "i9-12900h"},
    {"nombre": "i9-13900H", "query": "i9-13900h"},
    {"nombre": "i9-13980HX", "query": "i9-13980hx"},
    {"nombre": "i9-14900HX", "query": "i9-14900hx"},
    {"nombre": "Ultra 9 185H", "query": "ultra 9 185h"},
]

CATEGORIAS_BUSQUEDA = [
    {"nombre": "Ryzen 3", "terminos": ["ryzen 3 4", "ryzen 3 5", "ryzen 3 7", "ryzen 3 8"]},
    {"nombre": "Ryzen 5", "terminos": ["ryzen 5 4", "ryzen 5 5", "ryzen 5 6", "ryzen 5 7", "ryzen 5 8"]},
    {"nombre": "Ryzen 7", "terminos": ["ryzen 7 4", "ryzen 7 5", "ryzen 7 6", "ryzen 7 7", "ryzen 7 8"]},
    {"nombre": "Ryzen 9", "terminos": ["ryzen 9 5", "ryzen 9 6", "ryzen 9 7", "ryzen 9 8"]},
    {"nombre": "Intel i3", "terminos": ["i3-11", "i3-12", "i3-13"]},
    {"nombre": "Intel i5", "terminos": ["i5-11", "i5-12", "i5-13", "i5-14", "ultra 5"]},
    {"nombre": "Intel i7", "terminos": ["i7-11", "i7-12", "i7-13", "i7-14", "ultra 7"]},
    {"nombre": "Intel i9", "terminos": ["i9-11", "i9-12", "i9-13", "i9-14", "ultra 9"]},
]

DB_LOCAL = "ofertas_enviadas.json"
MARCAS = ["HP", "Dell", "Lenovo", "Asus", "Acer", "MSI"]
INVALID_TITLE_TOKENS = [
    "for parts", "not working", "parts only", "broken", "read description", "motherboard",
    "screen", "battery", "keyboard", "fan", "cable", "adapter", "charger", "housing",
    "palmrest", "bezel", "replacement", "placa base", "pantalla", "bateria", "teclado"
]
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

def obtener_configuracion() -> dict:
    cargar_env()
    return {
        "telegram_token": os.getenv("TELEGRAM_TOKEN", "").strip(),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "dry_run": valor_env_bool("DRY_RUN", False),
        "run_once": valor_env_bool("RUN_ONCE", False),
        "use_browser_fallback": valor_env_bool("USE_BROWSER_FALLBACK", False),
        "ebay_site": os.getenv("EBAY_SITE", "https://www.ebay.com").strip().rstrip("/"),
        "marcas": lista_env("MARCAS", MARCAS),
        "use_ebay_api": valor_env_bool("USE_EBAY_API", True),
        "ebay_client_id": os.getenv("EBAY_CLIENT_ID", "").strip(),
        "ebay_client_secret": os.getenv("EBAY_CLIENT_SECRET", "").strip(),
        "ebay_marketplace_id": os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip() or "EBAY_US",
        "ebay_currency": os.getenv("EBAY_CURRENCY", "USD").strip() or "USD",
        "max_precio": float(os.getenv("MAX_PRECIO", "200")),
        "intervalo_horas": float(os.getenv("INTERVALO_HORAS", "8")),
        "top_por_mensaje": max(1, int(os.getenv("TOP_POR_MENSAJE", "3"))),
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
    }

def cargar_ofertas_enviadas() -> Set[str]:
    if not os.path.exists(DB_LOCAL): return set()
    try:
        with open(DB_LOCAL, "r", encoding="utf-8") as archivo: return set(json.load(archivo))
    except (json.JSONDecodeError, IOError): return set()

def guardar_ofertas_enviadas(enlaces: Set[str]) -> None:
    with open(DB_LOCAL, "w", encoding="utf-8") as archivo:
        json.dump(sorted(enlaces), archivo, indent=4)

def construir_url_busqueda(base_url: str, consulta_cpu: str, marca: str, max_precio: float) -> str:
    condiciones = "1000%7C1500%7C2000%7C2500%7C2501%7C2502%7C2503%7C3000%7C4000%7C5000%7C6000"
    query = f"{marca} {consulta_cpu} laptop"
    return f"{base_url}/sch/i.html?_nkw={quote_plus(query)}&_sacat=0&LH_BIN=1&LH_ItemCondition={condiciones}&_ipg=240&_sop=15"

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

def recortar_texto(texto: str, limite: int = 110) -> str:
    if len(texto) <= limite: return texto
    return texto[: limite - 3].rstrip() + "..."

def es_titulo_valido(titulo: str) -> bool:
    titulo_lower = titulo.lower()
    return not any(token in titulo_lower for token in INVALID_TITLE_TOKENS)

def es_generacion_valida(titulo: str, terminos_generacion: List[str]) -> bool:
    titulo_lower = titulo.lower()
    return any(termino in titulo_lower for termino in terminos_generacion)

def normalizar_enlace_ebay(enlace: str, base_url: str) -> str:
    enlace = enlace.strip()
    if not enlace: return ""
    enlace_absoluto = urljoin(f"{base_url}/", enlace)
    match = re.search(r"/itm/(?:[^/]+/)?(\d+)", enlace_absoluto)
    if match: return f"{base_url}/itm/{match.group(1)}"
    url = urlparse(enlace_absoluto)
    return urlunparse(url._replace(query="", fragment=""))

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

_EBAY_TOKEN_CACHE: dict = {}

def _ebay_basic_auth_header(client_id: str, client_secret: str) -> str:
    cred = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(cred).decode("ascii")

def obtener_token_ebay_app(config: dict) -> str:
    ahora = int(time.time())
    token = _EBAY_TOKEN_CACHE.get("access_token")
    expira_en = int(_EBAY_TOKEN_CACHE.get("expires_at", 0))
    if token and ahora < expira_en - 60: return token

    client_id, client_secret = config["ebay_client_id"], config["ebay_client_secret"]
    if not client_id or not client_secret: raise RuntimeError("Faltan credenciales API eBay")

    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _ebay_basic_auth_header(client_id, client_secret),
    }
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    resp = requests.post(url, headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    _EBAY_TOKEN_CACHE["access_token"] = payload["access_token"]
    _EBAY_TOKEN_CACHE["expires_at"] = ahora + int(payload.get("expires_in", 7200))
    return _EBAY_TOKEN_CACHE["access_token"]

def _buscar_browse_api(config: dict, q: str, limit: int) -> dict:
    token = obtener_token_ebay_app(config)
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    condition_ids = "1000|1500|2000|2501|2502|2503|2500|3000|4000|5000|6000"
    filtros = [
        f"conditionIds:{{{condition_ids}}}",
        f"price:[..{config['max_precio']}]",
        f"priceCurrency:{config['ebay_currency']}",
        "buyingOptions:{FIXED_PRICE|BEST_OFFER}",
    ]
    params = {"q": q, "limit": str(max(1, min(limit, 200))), "sort": "newlyListed", "filter": ",".join(filtros)}
    headers = {
        "Authorization": f"Bearer {token}", "Accept": "application/json",
        "Accept-Language": "en-US", "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def buscar_ofertas_categoria_api(config: dict, categoria: dict, marca: str, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    encabezado = f"{marca} {categoria['nombre']}"
    q = f"{marca} {categoria['nombre']} laptop"
    print(f"\n[?] (API) Buscando: {encabezado}... Q: {q}")

    data = _buscar_browse_api(config, q=q, limit=50)
    items = data.get("itemSummaries") or []
    descartes = {"sin_datos": 0, "titulo": 0, "procesador": 0, "precio": 0, "enlace": 0, "duplicado": 0}
    ofertas: List[OfertaLaptop] = []

    for it in items:
        titulo = (it.get("title") or "").strip()
        if not titulo or not es_titulo_valido(titulo):
            descartes["titulo"] += 1; continue
        if not es_generacion_valida(titulo, categoria["terminos"]):
            descartes["procesador"] += 1; continue

        price_obj = it.get("price") or {}
        currency = price_obj.get("currency") or config["ebay_currency"]
        try: precio = float(price_obj.get("value"))
        except (TypeError, ValueError): descartes["precio"] += 1; continue
        if precio > config["max_precio"]: descartes["precio"] += 1; continue

        enlace = (it.get("itemWebUrl") or it.get("itemAffiliateWebUrl") or "").strip()
        if not enlace: descartes["enlace"] += 1; continue
        enlace = normalizar_enlace_ebay(enlace, config["ebay_site"])
        if enlace in enlaces_excluidos: descartes["duplicado"] += 1; continue

        estado = (it.get("condition") or "No especificado").strip() or "No especificado"
        precio_texto = f"{currency} {precio:.2f}"
        ofertas.append(OfertaLaptop(categoria["nombre"], estado, titulo, precio, precio_texto, enlace))

    ofertas.sort(key=lambda x: x.precio)
    return ofertas

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

def obtener_precio_referencia(sopa: BeautifulSoup) -> str:
    tag = sopa.select_one(".s-card__price") or sopa.select_one(".s-item__price")
    return limpiar_texto(tag.get_text(" ", strip=True)) if tag else ""

def extraer_oferta_desde_item(item: Tag, base_url: str, procesador: str, terminos_generacion: List[str], max_precio: float, enlaces_excluidos: Set[str]) -> Tuple[Optional[OfertaLaptop], str]:
    titulo_tag = item.select_one(".s-item__title") or item.select_one(".s-card__title")
    precio_tag = item.select_one(".s-item__price") or item.select_one(".s-card__price")
    enlace_tag = item.select_one(".s-item__link") or item.select_one("a.s-card__link")

    if not titulo_tag or not precio_tag or not enlace_tag: return None, "sin_datos"

    titulo = limpiar_texto(titulo_tag.get_text(" ", strip=True)).replace("Se abre en una ventana nueva", "").strip()
    if not titulo or titulo.lower() == "shop on ebay" or not es_titulo_valido(titulo): return None, "titulo"
    if not es_generacion_valida(titulo, terminos_generacion): return None, "procesador"

    precio_texto = limpiar_texto(precio_tag.get_text(" ", strip=True))
    precio = extraer_precio(precio_texto)
    if precio is None or precio > max_precio: return None, "precio"

    enlace = normalizar_enlace_ebay(enlace_tag.get("href", ""), base_url)
    if not enlace: return None, "enlace"
    if enlace in enlaces_excluidos: return None, "duplicado"

    estado_tag = item.select_one(".SECONDARY_INFO") or item.select_one(".s-item__subtitle")
    estado = limpiar_texto(estado_tag.get_text(" ", strip=True)) if estado_tag else "No especificado"

    return OfertaLaptop(procesador, estado, titulo, precio, precio_texto, enlace), "ok"

def buscar_ofertas_categoria(browser: Optional[EbayBrowser], config: dict, categoria: dict, marca: str, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    if config.get("use_ebay_api") and config.get("ebay_client_id"):
        return buscar_ofertas_categoria_api(config, categoria, marca, enlaces_excluidos)

    url = construir_url_busqueda(config["ebay_site"], categoria["nombre"], marca, config["max_precio"])
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

    for item in items:
        oferta, _ = extraer_oferta_desde_item(item, config["ebay_site"], categoria["nombre"], categoria["terminos"], config["max_precio"], enlaces_vistos)
        if oferta:
            enlaces_vistos.add(oferta.enlace)
            ofertas.append(oferta)

    ofertas.sort(key=lambda item: item.precio)
    return ofertas

def generar_bloque_mensaje_telegram(ofertas: List[OfertaLaptop], encabezado: str) -> str:
    if not ofertas: return ""
    lineas = [f"<b>🔥 Top {len(ofertas)} | {encabezado}</b>\n"]
    for oferta in ofertas:
        lineas.extend([
            f"💻 <b>Modelo:</b> {html.escape(recortar_texto(oferta.titulo))}",
            f"✨ <b>Estado:</b> {html.escape(oferta.estado)}",
            f"💰 <b>Precio:</b> <code>{html.escape(oferta.precio_texto)}</code>",
            f"🔗 <a href='{oferta.enlace}'>VER EN EBAY</a>",
            "━━━━━━━━━━━━━━━━━━"
        ])
    return "\n".join(lineas).strip()

def enviar_telegram(token: str, chat_id: str, mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML", "disable_web_page_preview": False}
    try: requests.post(url, json=payload, timeout=30)
    except Exception as e: print(f"Error Telegram: {e}")

def notificar_ofertas(config: dict, encabezado: str, ofertas: List[OfertaLaptop]) -> None:
    mensaje = generar_bloque_mensaje_telegram(ofertas, encabezado)
    if not mensaje: return
    if config["dry_run"]:
        print(f"    [DRY_RUN] Mensaje a Telegram:\n{mensaje}")
        return
    enviar_telegram(config["telegram_token"], config["telegram_chat_id"], mensaje)

def dormir_entre_busquedas(config: dict) -> None:
    time.sleep(random.uniform(config["sleep_min_seconds"], config["sleep_max_seconds"]))

def ejecutar_ciclo(config: dict, browser: Optional[EbayBrowser]) -> bool:
    enviadas = cargar_ofertas_enviadas()
    reportadas_en_ciclo: Set[str] = set()
    hubo_ofertas = False

    print("Iniciando busqueda con motor avanzado hacia Telegram...")

    for categoria in CATEGORIAS_BUSQUEDA:
        for marca in config["marcas"]:
            try:
                ofertas = buscar_ofertas_categoria(browser, config, categoria, marca, enviadas | reportadas_en_ciclo)
                if not ofertas:
                    dormir_entre_busquedas(config)
                    continue

                encabezado = f"{marca} {categoria['nombre']}"
                ofertas_a_notificar = ofertas[: config["top_por_mensaje"]]
                print(f"  [+] {len(ofertas_a_notificar)} oferta(s) notificadas a Telegram para {encabezado}.")
                
                notificar_ofertas(config, encabezado, ofertas_a_notificar)
                hubo_ofertas = True

                for oferta in ofertas_a_notificar:
                    reportadas_en_ciclo.add(oferta.enlace)

                if not config["dry_run"]:
                    enviadas.update(oferta.enlace for oferta in ofertas_a_notificar)
                    guardar_ofertas_enviadas(enviadas)

                dormir_entre_busquedas(config)
            except EbayChallengeError as error:
                print(f"  [!] El proceso se detiene: {error}")
                return False
            except Exception as error:
                print(f"  [!] Error en {marca} {categoria['nombre']}: {error}")
                time.sleep(5)

    if not hubo_ofertas: print("Ciclo completado sin ofertas nuevas.")
    return True

def main() -> None:
    config = obtener_configuracion()
    if not config["telegram_token"] or not config["telegram_chat_id"]:
        print("❌ Error: Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el archivo .env")
        return

    intervalo_segundos = max(1, int(config["intervalo_horas"] * 3600))
    if config["dry_run"]: print("DRY_RUN activo: no se enviaran mensajes reales.")

    browser: Optional[EbayBrowser] = None
    if config.get("use_ebay_api") and config.get("ebay_client_id"): print("Modo API activo: usando eBay Browse API.")
    elif config["use_browser_fallback"]: browser = EbayBrowser(config)
    else: print("Modo publico activo.")

    try:
        if config["run_once"]:
            ejecutar_ciclo(config, browser)
            return
        print(f"Bot iniciado. Ejecutando cada {config['intervalo_horas']} horas.")
        while True:
            continuar = ejecutar_ciclo(config, browser)
            if not continuar: return
            time.sleep(intervalo_segundos)
    finally:
        if browser is not None: browser.close()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nProceso interrumpido.")