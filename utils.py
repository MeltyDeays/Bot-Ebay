import re
import json
import os
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse
from datetime import datetime, timezone
from typing import Optional, Set, Any, Tuple

DB_LOCAL = 'ofertas_enviadas.json'

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

def normalizar_enlace_ebay(enlace: str, base_url: str) -> str:
    enlace = enlace.strip()
    if not enlace: return ""
    enlace_absoluto = urljoin(f"{base_url}/", enlace)
    match = re.search(r"/itm/(?:[^/]+/)?(\d+)", enlace_absoluto)
    if match: return f"{base_url}/itm/{match.group(1)}"
    url = urlparse(enlace_absoluto)
    return urlunparse(url._replace(query="", fragment=""))

