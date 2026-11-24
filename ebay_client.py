import os
import json
import base64
import time
import requests
import random
from typing import Set, List, Optional, Tuple, Dict, Any
from bs4 import BeautifulSoup, Tag
from models import OfertaLaptop
from utils import calcular_tiempo_restante, extraer_precio, limpiar_texto, es_titulo_valido, es_generacion_valida, cumple_especificaciones_almacenamiento, normalizar_enlace_ebay, EXCLUSION_PATTERN, cumple_specs_detalladas, extraer_texto_enriquecido, DESCRIPTION_RED_FLAGS
from config import CATEGORIAS_BUSQUEDA, ESTADOS_BUSQUEDA, MARCAS_SOPORTADAS, MAX_VERIFY_CHECKS, MAX_RESCUE_CHECKS, MAX_WORKERS_AI, MAX_EJEMPLOS
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, Playwright, sync_playwright
except (ImportError, ModuleNotFoundError):
    sync_playwright = None
    PlaywrightError = Exception
    Page = None
    Playwright = None

_EBAY_TOKEN_CACHE: dict = {}
_DIRECT_HTTP_SESSION = requests.Session()
_DIRECT_HTTP_SESSION.trust_env = False

# Vendedores que el bot monitorea directamente (búsqueda por tienda)
VENDEDORES_PRIORITARIOS = [
    "regencytechnologies",
]

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
            respuesta = _DIRECT_HTTP_SESSION.get(url, headers=obtener_headers_publicos(), timeout=30)
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

def analizar_con_ia(config: dict, titulo: str, detalle: dict, precio: float) -> str:
    """Implementación base para analizar rescate usando IA (Gemini o Groq Llama 3)."""
    try:
        import requests
        
        texto = extraer_texto_enriquecido(detalle)

        # Cargar base de conocimiento de ejemplos rechazados ("Equivocado")
        ejemplos_negativos_str = ""
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplos_equivocados.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    bad_list = json.load(f)[-5:]
                    if bad_list:
                        ejemplos_negativos_str = "\nEJEMPLOS INCORRECTOS RECHAZADOS ANTERIORMENTE (NO ACEPTAR SIMILARES):\n"
                        for item in bad_list:
                            ejemplos_negativos_str += f"- Título: '{item.get('titulo')}' | Motivo error: {item.get('motivo_error')}\n"
            except Exception:
                pass

        prompt = f"""
        Actúa como un experto en hardware comprando laptops usadas en eBay.
        Título: {titulo}
        Precio: ${precio}
        Descripción completa y specs:
        {texto[:1000]}
        {ejemplos_negativos_str}
        
        ¿Esta laptop tiene un procesador BUENO (Core i5/i7 gen 11 o superior, o Ryzen 5/7 serie 4000 o superior), al menos 16GB RAM y al menos 256GB SSD, y NO tiene daños severos descritos en la descripción, ni coincide con los ejemplos incorrectos?
        Responde estrictamente con "ACEPTAR" si cumple todo, o "RECHAZAR" si es basura/vieja/dañada/falta ram/ssd.
        """

        
        # 1. Intentar Gemini
        api_key_gemini = config.get("gemini_api_key")
        if api_key_gemini:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key_gemini}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                res = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip().upper()
                return "ACEPTAR" if "ACEPTAR" in res else "RECHAZAR"
                
        # 2. Fallback a Groq
        api_key_groq = config.get("groq_api_key")
        if api_key_groq:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key_groq}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 5
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                res = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
                return "ACEPTAR" if "ACEPTAR" in res else "RECHAZAR"
                
        return "RECHAZAR"
    except Exception as e:
        print(f"Error en IA fallback: {e}")
        return "RECHAZAR"

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
    resp = _DIRECT_HTTP_SESSION.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers=headers,
        data=data,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _EBAY_TOKEN_CACHE["access_token"] = payload["access_token"]
    _EBAY_TOKEN_CACHE["expires_at"] = ahora + int(payload.get("expires_in", 7200))
    return _EBAY_TOKEN_CACHE["access_token"]

def obtener_detalle_item_api(config: dict, item_id: str) -> dict:
    try:
        token = obtener_token_ebay_app(config)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
        }
        from urllib.parse import quote
        safe_item_id = quote(item_id)
        url = f"https://api.ebay.com/buy/browse/v1/item/{safe_item_id}"
        resp = _DIRECT_HTTP_SESSION.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error obteniendo detalle item API {item_id}: {e}")
    return {}

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

def buscar_ofertas_categoria_api(config: dict, categoria: dict, marca: str, enlaces_excluidos: Set[str]) -> List[OfertaLaptop]:
    nombre_limpio = categoria['nombre'].replace("Intel ", "").strip()
    encabezado = f"{marca} {categoria['nombre']}"
    q = f"{marca} {nombre_limpio}"
    print(f"\n[API] Buscando: {encabezado}... Q: {q}")


    try:
        token = obtener_token_ebay_app(config)
        estados = config.get("estados_busqueda", ESTADOS_BUSQUEDA)
        cond_ids = "|".join([str(est["id"]) for est in estados]) if estados else "1000|1500|2000|2010|2020|2030|3000"
        filtros = f"conditionIds:{{{cond_ids}}},price:[..{config['max_precio']}],priceCurrency:{config['ebay_currency']},buyingOptions:{{FIXED_PRICE|BEST_OFFER|AUCTION}}"
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
                resp = _DIRECT_HTTP_SESSION.get(
                    "https://api.ebay.com/buy/browse/v1/item_summary/search",
                    headers=headers,
                    params=params,
                    timeout=30,
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
    from config import BLOCKED_SELLERS
    
    min_vendedor_ventas = config.get("min_vendedor_ventas", 1000)

    for it in items:
        seller_data = it.get("seller", {})
        vendedor = seller_data.get("username", "").strip().lower()
        feedback_score = int(seller_data.get("feedbackScore") or 0)

        if vendedor in [s.lower() for s in BLOCKED_SELLERS]:
            continue

        if min_vendedor_ventas > 0 and feedback_score > 0 and feedback_score < min_vendedor_ventas:
            continue

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
                ejemplos_rechazo["precio_alto"].append(f'"{titulo[:60]}" -> ${precio:.0f}')
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
                ejemplos_rechazo["gen_vieja"].append(f'"{titulo[:70]}" -> [titulo: gen_vieja]')
            continue



        main_img = it.get("image", {}).get("imageUrl", "")
        add_imgs = [img.get("imageUrl") for img in it.get("additionalImages", []) if isinstance(img, dict) and img.get("imageUrl")]
        all_imgs = ([main_img] if main_img else []) + [i for i in add_imgs if i != main_img]

        item_data = {
            "item_id": it.get("itemId", ""),
            "titulo": titulo, "precio": precio, "precio_texto": precio_texto,
            "enlace": enlace,
            "estado": (it.get("condition") or "No especificado").strip() or "No especificado",
            "imagen_url": main_img,
            "imagenes": all_imgs,
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
        print(f"  [Verificacion] Verificando descripcion de {max_verificar} items que pasaron titulo...")


    for cand in candidatos_verificar[:MAX_VERIFY_CHECKS]:
        es_subasta = "AUCTION" in cand["buying_options"]
        tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
        if es_subasta and (tiempo_restante == "Terminada" or "terminad" in tiempo_restante.lower()):
            rechazos["subasta_finalizada"] = rechazos.get("subasta_finalizada", 0) + 1
            continue

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
            cand.get("seller", ""), "", "eBay", cand.get("imagenes", [])
        ))

    # Items que no se pudieron verificar (exceso de límite) -> aceptar por título
    for cand in candidatos_verificar[MAX_VERIFY_CHECKS:]:
        es_subasta = "AUCTION" in cand["buying_options"]
        tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
        if es_subasta and (tiempo_restante == "Terminada" or "terminad" in tiempo_restante.lower()):
            rechazos["subasta_finalizada"] = rechazos.get("subasta_finalizada", 0) + 1
            continue

        ofertas.append(OfertaLaptop(
            categoria["nombre"], cand["estado"], cand["titulo"],
            cand["precio"], cand["precio_texto"], cand["enlace"],
            cand["imagen_url"], es_subasta, tiempo_restante,
            cand.get("seller", ""), "", "eBay", cand.get("imagenes", [])
        ))



    # ══════════════════════════════════════════════════════════════════════
    # PASE 3: Rescatar items que FALLARON título (verificación completa)
    #         Con Gemini AI como segundo filtro inteligente
    # ══════════════════════════════════════════════════════════════════════
    rescatados = 0
    verificados_rescate = 0
    max_rescatar = min(len(candidatos_rescatar), MAX_RESCUE_CHECKS)
    if candidatos_rescatar:
        print(f"  [Rescate] {len(candidatos_rescatar)} candidatos para rescate (revisando {max_rescatar})...")

    def procesar_candidato(cand):
        item_id = cand["item_id"]
        if not item_id:
            return cand, False, cand["razon_titulo"], "sin item_id", None, False
        
        detalle = obtener_detalle_item_api(config, item_id)
        if not detalle:
            return cand, False, cand["razon_titulo"], "sin detalle API", None, False
            
        pasa, razon = cumple_specs_detalladas(detalle, categoria)
        rescate_ia = False
        
        # Si el regex lo rechaza pero tiene IA disponible, pedir segunda opinión
        if not pasa and (config.get("gemini_api_key") or config.get("groq_api_key")):
            veredicto_ia = analizar_con_ia(config, cand["titulo"], detalle, cand["precio"])
            if veredicto_ia == "ACEPTAR":
                pasa = True
                razon = "ok"
                rescate_ia = True
                
        return cand, pasa, razon, "", detalle, rescate_ia

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_AI) as executor:
        futures = {executor.submit(procesar_candidato, cand): cand for cand in candidatos_rescatar[:MAX_RESCUE_CHECKS]}
        for future in as_completed(futures):
            cand, pasa, razon, msg, detalle, rescate_ia = future.result()
            verificados_rescate += 1
            
            if rescate_ia:
                print(f"    [IA] IA RESCATO: {cand['titulo'][:60]}")

                
            if pasa:
                es_subasta = "AUCTION" in cand["buying_options"]
                tiempo_restante = calcular_tiempo_restante(cand["item_end_date"]) if es_subasta else ""
                titulo_det = (detalle.get("title") or cand["titulo"]).strip() if detalle else cand["titulo"].strip()
                ofertas.append(OfertaLaptop(
                    categoria["nombre"], cand["estado"], titulo_det,
                    cand["precio"], cand["precio_texto"], cand["enlace"],
                    cand["imagen_url"], es_subasta, tiempo_restante,
                    cand.get("seller", ""), "", "eBay", cand.get("imagenes", [])
                ))

                rescatados += 1
            else:
                rechazos[razon] += 1
                if len(ejemplos_rechazo[razon]) < MAX_EJEMPLOS:
                    txt = msg if msg else f"detalle: {razon}"
                    ejemplos_rechazo[razon].append(f'"{cand["titulo"][:70]}" -> [{txt}]')
    # Los que no se verificaron en rescate -> contar como rechazo
    for cand in candidatos_rescatar[MAX_RESCUE_CHECKS:]:
        rechazos[cand["razon_titulo"]] += 1
        if len(ejemplos_rechazo[cand["razon_titulo"]]) < MAX_EJEMPLOS:
            ejemplos_rechazo[cand["razon_titulo"]].append(f'"{cand["titulo"][:70]}" -> [no verificado]')


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
            ej_safe = str(ej).encode('ascii', 'replace').decode('ascii')
            print(f"         . {ej_safe}")

    if rechazados_desc > 0:
        print(f"      -> {rechazados_desc} eliminados por descripción sospechosa")
    if rescatados > 0:
        print(f"      -> [RESCATE] {rescatados} RESCATADOS gracias a descripción/specs ({verificados_rescate} verificados)")
    print(f"      -> [OK] {len(ofertas)} pasaron TODOS los filtros.")
    if ofertas:
        for o in ofertas:
            seller_tag = f" [{o.vendedor}]" if o.vendedor else ""
            t_safe = str(o.titulo).encode('ascii', 'replace').decode('ascii')
            print(f"         + {t_safe} -> {o.precio_texto}{seller_tag}")



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
            estados = config.get("estados_busqueda", ESTADOS_BUSQUEDA)
            cond_ids = "|".join([str(est["id"]) for est in estados]) if estados else "1000|1500|2000|2010|2020|2030|3000"
            filtros = (
                f"conditionIds:{{{cond_ids}}},"
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

