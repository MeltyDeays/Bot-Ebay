import os
import json
import base64
import time
import requests
import random
from typing import Set, List, Optional, Tuple, Dict, Any
from bs4 import BeautifulSoup, Tag
from models import OfertaLaptop
from utils import calcular_tiempo_restante, extraer_precio, limpiar_texto, es_titulo_valido, es_generacion_valida, cumple_especificaciones_almacenamiento, normalizar_enlace_ebay
from config import CATEGORIAS_BUSQUEDA, ESTADOS_BUSQUEDA, MARCAS_SOPORTADAS

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, Playwright, sync_playwright
except (ImportError, ModuleNotFoundError):
    sync_playwright = None
    PlaywrightError = Exception
    Page = None
    Playwright = None

_EBAY_TOKEN_CACHE: dict = {}

class EbayChallengeError(Exception):
    pass

class EbayBrowser:
    def __init__(self, config: dict):
        pass

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

