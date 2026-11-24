import concurrent.futures
import json
import os
import random
import re
import urllib.parse

import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import obtener_configuracion, todos_los_destinos
from cpu_rules import es_cpu_obsoleta
from ebay_client import obtener_token_ebay_app, obtener_detalle_item_api
from supabase_integration import AnalizadorRentabilidad, AnalizadorVisual, SupabaseClient
from telegram_utils import enviar_telegram_foto, enviar_telegram_texto
from tracking import detect_carrier, lookup_tracking
from utils import es_titulo_valido

class SearchFiltersRequest(BaseModel):
    categorias_activas: List[str]
    estados_activos: List[str]
    tiendas_activas: Optional[List[str]] = None
    combinar_resultados: Optional[bool] = None
    min_vendedor_ventas: Optional[int] = 1000


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct"
]
SEARCH_THREAD_WORKERS = 8
DEFAULT_SEARCH_CONDITION_IDS = ("1000", "1500", "2000", "2010", "2020", "2030", "3000")
CONDITION_PREFERENCE_TO_IDS = {
    "new": ("1000",),
    "open_box": ("1500",),
    "certified_refurbished": ("2000",),
    "excellent": ("1000", "1500", "2000", "2010"),
    "very_good": ("1000", "1500", "2000", "2010", "2020"),
    "good": ("1000", "1500", "2000", "2010", "2020", "2030"),
    "refurbished": ("2000", "2010", "2020", "2030"),
    "used": ("3000",),
    "for_parts": ("7000",),
}
CONDITION_PREFERENCE_ALIASES = (
    ("for_parts", ("for parts", "not working", "para piezas", "repuestos")),
    ("open_box", ("open box", "caja abierta")),
    (
        "certified_refurbished",
        (
            "certified refurbished",
            "certified refurb",
            "reacondicionado certificado",
            "restaurada por ebay",
            "restaurado por ebay",
            "restauradas por ebay",
            "restaurados por ebay",
            "refurbished by ebay",
            "restored by ebay",
            "ebay refurbished",
        ),
    ),
    ("excellent", ("excellent refurbished", "excelente", "en excelente", "excellent condition", "mint", "like new")),
    (
        "very_good",
        (
            "very good refurbished",
            "very good",
            "en very good",
            "very good condition",
            "muy bueno",
            "muy buena",
            "muy buenos",
            "muy buenas",
            "muy buen estado",
        ),
    ),
    ("good", ("good refurbished", "good condition", "en good", "bueno", "buena", "buenos", "buenas", "buen estado")),
    (
        "refurbished",
        (
            "refurbished",
            "renewed",
            "reacondicionado",
            "reacondicionada",
            "reacondicionados",
            "reacondicionadas",
            "remanufactured",
            "restaurado",
            "restaurada",
            "restaurados",
            "restauradas",
            "restored",
        ),
    ),
    ("new", ("brand new", "new", "nuevo", "nueva")),
    ("used", ("used", "usado", "usada", "usados", "usadas")),
)
CONDITION_STRIP_PATTERNS = (
    re.compile(r"\bfor parts(?: only)?\b", re.IGNORECASE),
    re.compile(r"\bnot working\b", re.IGNORECASE),
    re.compile(r"\bopen box\b", re.IGNORECASE),
    re.compile(r"\bcertified refurbished\b", re.IGNORECASE),
    re.compile(r"\bexcellent refurbished\b", re.IGNORECASE),
    re.compile(r"\bvery good refurbished\b", re.IGNORECASE),
    re.compile(r"\bgood refurbished\b", re.IGNORECASE),
    re.compile(r"\brestaurad[oa]s?\s+por\s+ebay\b", re.IGNORECASE),
    re.compile(r"\brestored\s+by\s+ebay\b", re.IGNORECASE),
    re.compile(r"\brefurbished\s+by\s+ebay\b", re.IGNORECASE),
    re.compile(r"\bebay refurbished\b", re.IGNORECASE),
    re.compile(r"\ben\s+very good\b", re.IGNORECASE),
    re.compile(r"\ben\s+good\b", re.IGNORECASE),
    re.compile(r"\ben excelente\b", re.IGNORECASE),
    re.compile(r"\bexcelente\b", re.IGNORECASE),
    re.compile(r"\bexcellent\b", re.IGNORECASE),
    re.compile(r"\bvery good\b", re.IGNORECASE),
    re.compile(r"\bmuy buen(?:o|a)?(?: estado)?\b", re.IGNORECASE),
    re.compile(r"\bgood condition\b", re.IGNORECASE),
    re.compile(r"\bbuen(?:o|a|os|as)?(?: estado)?\b", re.IGNORECASE),
    re.compile(r"\brefurbished\b", re.IGNORECASE),
    re.compile(r"\breacondicionad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\brenewed\b", re.IGNORECASE),
    re.compile(r"\brestored\b", re.IGNORECASE),
    re.compile(r"\brestaurad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bbrand new\b", re.IGNORECASE),
    re.compile(r"\bnew\b", re.IGNORECASE),
    re.compile(r"\bnuevo\b|\bnueva\b", re.IGNORECASE),
    re.compile(r"\bused\b", re.IGNORECASE),
    re.compile(r"\busad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\b(?:por|by)\b", re.IGNORECASE),
)
BRAND_HINT_ALIASES = (
    ("acer", ("acer", "aspire", "swift", "nitro", "predator", "travelmate")),
    ("alienware", ("alienware",)),
    ("apple", ("apple", "macbook")),
    ("asus", ("asus", "rog", "vivobook", "zenbook", "expertbook", "tuf")),
    ("dell", ("dell", "latitude", "precision", "vostro", "inspiron", "xps")),
    ("fujitsu", ("fujitsu", "lifebook")),
    ("gigabyte", ("gigabyte", "aorus")),
    ("hp", ("hp", "elitebook", "probook", "zbook", "omen", "victus", "pavilion", "envy", "spectre", "dragonfly")),
    ("huawei", ("huawei", "matebook")),
    ("lenovo", ("lenovo", "thinkpad", "ideapad", "thinkbook", "yoga", "legion")),
    ("lg", ("lg", "gram")),
    ("microsoft", ("microsoft", "surface")),
    ("msi", ("msi", "stealth", "raider", "katana", "cyborg", "modern")),
    ("panasonic", ("panasonic", "toughbook")),
    ("razer", ("razer", "blade")),
    ("samsung", ("samsung", "galaxy book")),
    ("toshiba", ("toshiba", "dynabook")),
)
OFFICIAL_BRAND_SELLERS = {
    "acer": ("acer",),
    "dell": ("dell-official-store-usa-refurbished",),
    "hp": ("officialhpstore",),
    "lenovo": ("lenovo",),
    "razer": ("therazerstore",),
    "samsung": ("samsung",),
}
OFFICIAL_STORE_QUERY_PATTERNS = (
    re.compile(r"\btienda\s+oficial\b", re.IGNORECASE),
    re.compile(r"\bofficial\s+store\b", re.IGNORECASE),
    re.compile(r"\bdirect(?:amente)?\s+de\b", re.IGNORECASE),
    re.compile(r"\bdirect\s+from\b", re.IGNORECASE),
)

load_dotenv()
config = obtener_configuracion()

supabase_client = None
if config.get("supabase_url") and config.get("supabase_service_key"):
    supabase_client = SupabaseClient(config["supabase_url"], config["supabase_service_key"])

app = FastAPI(title="eBay AI Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_SESSION = requests.Session()
EBAY_SESSION = requests.Session()
GROQ_SESSION.trust_env = False
EBAY_SESSION.trust_env = False


def _log(prefix: str, message: str) -> None:
    print(f"[{prefix}] {message}")


def _truncate_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def _extract_json_object(raw: Any) -> Dict[str, Any]:
    text = str(raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("La respuesta no contiene un JSON valido.")
    return json.loads(text[start:end])


def _collect_item_images(item: Dict[str, Any], limit: int = 6) -> List[str]:
    urls: List[str] = []
    seen = set()

    primary_url = item.get("image", {}).get("imageUrl")
    if primary_url:
        urls.append(primary_url)
        seen.add(primary_url)

    for image in item.get("additionalImages", []):
        image_url = image.get("imageUrl")
        if not image_url or image_url in seen:
            continue
        seen.add(image_url)
        urls.append(image_url)
        if len(urls) >= limit:
            break

    return urls


def _contains_keyword(text: str, keyword: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE))


def _merge_unique_strings(*groups: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()

    for group in groups:
        for value in group:
            normalized = str(value or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)

    return merged


def _normalize_username_list(values: Any) -> List[str]:
    if values is None:
        return []

    if isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    else:
        raw_values = re.split(r"[|,]", str(values or ""))

    normalized: List[str] = []
    seen = set()

    for value in raw_values:
        username = str(value or "").strip().lower()
        if not username or username in seen:
            continue
        seen.add(username)
        normalized.append(username)

    return normalized


def _infer_condition_preference(text: Any) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return ""

    for preference, aliases in CONDITION_PREFERENCE_ALIASES:
        if any(alias in normalized for alias in aliases):
            return preference

    return ""


SPANISH_STOPWORDS_RE = re.compile(
    r"\b(?:con|de|del|para|espacio|espacio de|de espacio|generacion|generación|en|la|el|que|los|las|un|una|memoria|disco|duro|almacenamiento|de ram|de ssd|gb de ram|gb de ssd)\b",
    re.IGNORECASE,
)


def _clean_query_text(query: str) -> str:
    cleaned = str(query or "")
    # Normalizar patrones comunes de español a términos concisos de hardware en inglés
    cleaned = re.sub(r"\bgeneraci[oó]n\s*(\d+)\b", r"Gen \1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d+)\s*(?:de\s*)?ram\b", r"\1GB", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d+)\s*(?:de\s*)?(?:espacio\s*de\s*)?ssd\b", r"\1GB SSD", cleaned, flags=re.IGNORECASE)

    # Remover stop words en español
    cleaned = SPANISH_STOPWORDS_RE.sub(" ", cleaned)

    for pattern in CONDITION_STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned or str(query or "").strip()



def _infer_brand_hints(text: Any) -> List[str]:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return []

    hits: List[str] = []
    for brand, aliases in BRAND_HINT_ALIASES:
        if any(_contains_keyword(normalized, alias) for alias in aliases):
            hits.append(brand)

    return hits


def _infer_refurbisher_hint(text: Any) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return ""

    if not any(token in normalized for token in ("refurb", "reacondicion", "restaurad", "restored", "renewed")):
        return ""

    if re.search(r"\b(?:por|by|from)\s+ebay\b", normalized, re.IGNORECASE):
        return "ebay"

    for brand, aliases in BRAND_HINT_ALIASES:
        for alias in aliases:
            if re.search(rf"\b(?:por|by|from)\s+{re.escape(alias)}\b", normalized, re.IGNORECASE):
                return brand

    return ""


def _wants_official_store(text: Any) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in OFFICIAL_STORE_QUERY_PATTERNS)


def _infer_official_store_sellers(text: Any, brand_hints: List[str], refurbisher_hint: str) -> List[str]:
    if refurbisher_hint and refurbisher_hint != "ebay":
        return list(OFFICIAL_BRAND_SELLERS.get(refurbisher_hint, ()))

    if not _wants_official_store(text):
        return []

    for brand in brand_hints:
        known_sellers = OFFICIAL_BRAND_SELLERS.get(brand)
        if known_sellers:
            return list(known_sellers)

    return []


def _extract_item_seller_info(item: Dict[str, Any]) -> Dict[str, str]:
    seller_info = item.get("seller") or {}
    username = str(seller_info.get("username") or "").strip()
    user_id = str(seller_info.get("userId") or "").strip()
    display_name = username or user_id
    return {"username": username, "user_id": user_id, "display_name": display_name}


def _title_matches_brand_hints(title: str, brand_hints: List[str]) -> bool:
    normalized_title = str(title or "").strip().lower()
    if not normalized_title or not brand_hints:
        return True

    for brand in brand_hints:
        aliases = next((values for candidate, values in BRAND_HINT_ALIASES if candidate == brand), ())
        if any(_contains_keyword(normalized_title, alias) for alias in aliases):
            return True

    return False


def _item_matches_seller_filters(item: Dict[str, Any], seller_usernames: List[str]) -> bool:
    normalized_targets = {value.lower() for value in seller_usernames if value}
    if not normalized_targets:
        return True

    seller_info = _extract_item_seller_info(item)
    seller_candidates = {
        seller_info.get("username", "").lower(),
        seller_info.get("user_id", "").lower(),
    }
    seller_candidates.discard("")
    if not seller_candidates:
        return False

    return not normalized_targets.isdisjoint(seller_candidates)


def _enrich_search_params(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(params or {})
    raw_query = str(query or "").strip()

    if not enriched.get("q"):
        enriched["q"] = raw_query

    q_value = str(enriched.get("q") or "").strip()
    if not q_value or q_value.lower() == raw_query.lower():
        enriched["q"] = _clean_query_text(raw_query)

    brand_hints = _merge_unique_strings(
        _infer_brand_hints(raw_query),
        _infer_brand_hints(enriched.get("q", "")),
    )
    refurbisher_hint = _infer_refurbisher_hint(raw_query)
    official_seller_usernames = _infer_official_store_sellers(raw_query, brand_hints, refurbisher_hint)
    raw_seller_usernames = _normalize_username_list(enriched.get("sellerUsernames") or enriched.get("seller"))

    explicit_condition = _infer_condition_preference(enriched.get("conditionPreference", ""))
    inferred_condition = _infer_condition_preference(raw_query)
    condition_preference = explicit_condition or inferred_condition
    if refurbisher_hint == "ebay":
        condition_preference = "certified_refurbished"
    elif refurbisher_hint and not condition_preference:
        condition_preference = "refurbished"

    if refurbisher_hint and refurbisher_hint != "ebay":
        brand_hints = _merge_unique_strings(brand_hints, [refurbisher_hint])

    seller_usernames = raw_seller_usernames
    if refurbisher_hint == "ebay":
        seller_usernames = []
    elif official_seller_usernames:
        seller_usernames = official_seller_usernames
    elif refurbisher_hint:
        seller_usernames = []

    enriched["conditionPreference"] = condition_preference
    if condition_preference:
        enriched["q"] = _clean_query_text(str(enriched.get("q") or raw_query))
    if brand_hints and not _infer_brand_hints(enriched["q"]):
        enriched["q"] = f"{enriched['q']} {brand_hints[0]}".strip()
    enriched["conditionIds"] = list(CONDITION_PREFERENCE_TO_IDS.get(condition_preference, DEFAULT_SEARCH_CONDITION_IDS))
    enriched["brandHints"] = brand_hints
    enriched["refurbisherHint"] = refurbisher_hint
    enriched["sellerUsernames"] = seller_usernames
    enriched["seller"] = "|".join(seller_usernames)
    enriched["officialStoreBrand"] = (
        refurbisher_hint
        if official_seller_usernames and refurbisher_hint in OFFICIAL_BRAND_SELLERS
        else next((brand for brand in brand_hints if brand in OFFICIAL_BRAND_SELLERS and official_seller_usernames), "")
    )

    return enriched


def _condition_matches_preference(condition_text: str, condition_preference: str) -> bool:
    normalized = str(condition_text or "").strip().lower()
    if not normalized:
        return True

    if "for parts" in normalized or "not working" in normalized:
        return condition_preference == "for_parts"

    if not condition_preference:
        return True

    matchers = {
        "new": ("new",),
        "open_box": ("open box",),
        "certified_refurbished": ("certified refurbished",),
        "excellent": ("new", "open box", "certified refurbished", "excellent"),
        "very_good": ("new", "open box", "certified refurbished", "excellent", "very good"),
        "good": ("new", "open box", "certified refurbished", "excellent", "very good", "good"),
        "refurbished": ("certified refurbished", "excellent", "very good", "good"),
        "used": ("used",),
        "for_parts": ("for parts", "not working"),
    }

    return any(token in normalized for token in matchers.get(condition_preference, ()))


def is_ancient_processor(title: str) -> bool:
    """Verifica si el titulo contiene chasis HP obsoletos o procesadores por debajo del umbral minimo."""
    t = str(title).lower()
    if re.search(r"\b(?:dv[467]|g[467]|cq5[67]|m6|dm4|p6)[-\s]?\d*\b", t):
        return True
    if re.search(r"\bhp\s*envy\s*dv\b|\bhp\s*pavilion\s*dv\b|\benvy\s*dv\b", t):
        return True
    return es_cpu_obsoleta(title)

def resolve_store_from_url(url: str, default_store: str = "eBay") -> str:
    u = str(url or "").lower()
    if "amazon.com" in u:
        return "Amazon"
    if "bestbuy.com" in u:
        return "Best Buy"
    if "walmart.com" in u:
        return "Walmart"
    if "target.com" in u:
        return "Target"
    if "ebay.com" in u:
        return "eBay"
    return default_store


class SearchRequest(BaseModel):
    query: str
    maxPrice: Optional[float] = None
    conditionIds: Optional[List[str]] = None
    buyingOptions: Optional[str] = "ALL"  # "ALL", "FIXED_PRICE", "AUCTION"
    sortOrder: Optional[str] = None       # "endingSoonest", "newlyListed", "price", "-price"
    stores: Optional[List[str]] = None



class CartSendRequest(BaseModel):

    items: List[Dict[str, Any]]


class ImageAnalysisRequest(BaseModel):
    imagenes: List[str]
    titulo: str
    seller_notes: str = ""
    condicion: str = ""


groq_key = config.get("groq_api_key")
sb_url = config.get("supabase_url")
sb_key = config.get("supabase_service_key")

sb_client = SupabaseClient(sb_url, sb_key) if sb_url and sb_key else None
analizador_rent = AnalizadorRentabilidad(None, sb_client) if sb_client else None
analizador_vis = AnalizadorVisual(groq_key) if groq_key else None


def parse_query_with_ia(query: str) -> Dict[str, Any]:
    """Usa IA para convertir lenguaje natural en parametros de busqueda de eBay."""
    if not groq_key:
        return _enrich_search_params(
            query,
            {"q": query, "categoryId": "175672", "maxPrice": "250", "minPrice": "10", "seller": ""},
        )

    prompt = f"""Convierte esta busqueda del usuario en parametros para la API de eBay: "{query}"

Reglas de categoria:
- Laptops: 175672
- Celulares: 9355
- SSDs: 175669
- RAM: 170083

Responde solo con JSON:
{{
  "q": "palabras clave para buscar en eBay en ingles",
  "categoryId": "175672",
  "maxPrice": "precio maximo si menciona, o vacio",
  "minPrice": "precio minimo si menciona, o vacio",
  "seller": "nombre del vendedor si lo menciona, o vacio",
  "conditionPreference": "new|open_box|certified_refurbished|excellent|very_good|good|refurbished|used|for_parts|"
}}"""

    prompt += """

Reglas de condicion:
- Si el usuario pide excelente/excellent, no devuelvas used generico ni for_parts.
- Si el usuario pide open box, good, very good o usadas/usados, respetalo en conditionPreference.
- Si el usuario dice restaurada/restored/refurbished por eBay, usa certified_refurbished.
- Si el usuario dice restaurada/restored/refurbished por una marca o empresa, usa refurbished.
- Si el usuario dice "por HP", "por Lenovo", "por Acer" o marcas similares, no pongas seller con la marca; deja seller vacio y conserva la marca en q.
- Conserva marcas populares de laptops como Acer, Dell, HP, Lenovo, MSI, Asus, Samsung, LG, Microsoft Surface o Razer dentro de q.
- Si el usuario pide refurbished, usa una condicion refurbished.
- Si el usuario no pide condicion, deja conditionPreference vacio.
"""

    started_at = time.perf_counter()
    for model_name in GROQ_TEXT_MODELS:
        try:
            response = GROQ_SESSION.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 150,
                    "temperature": 0.1,
                },
                timeout=10,
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                parsed = _enrich_search_params(query, _extract_json_object(content))
                _log("SEARCH", f"Parse IA completado en {elapsed_ms} ms usando {model_name}: {_truncate_text(parsed)}")
                return parsed
                
            if response.status_code in (429, 400, 404):
                _log("SEARCH", f"Modelo {model_name} fallo ({response.status_code}), intentando con el siguiente...")
                continue
                
            _log(
                "SEARCH",
                f"Parse IA con {model_name} devolvio {response.status_code} en {elapsed_ms} ms: {_truncate_text(response.text)}",
            )
            break # Si es otro error, no seguir intentando
        except Exception as error:
            _log("SEARCH", f"Error parseando consulta con IA ({model_name}): {error}")

    return _enrich_search_params(
        query,
        {"q": query, "categoryId": "175672", "maxPrice": "250", "minPrice": "10", "seller": ""},
    )


@app.post("/api/search")
async def search_ebay(req: SearchRequest):
    """Busqueda en tiempo real usando eBay Browse API y Rentabilidad IA."""
    started_at = time.perf_counter()
    try:
        token = obtener_token_ebay_app(config)
    except requests.RequestException as error:
        _log("SEARCH", f"Fallo obteniendo token de eBay: {error}")
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar con eBay para obtener el token. Revisa tu conexion, proxy o VPN e intenta de nuevo.",
        ) from error
    except RuntimeError as error:
        _log("SEARCH", f"Configuracion invalida de eBay: {error}")
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        _log("SEARCH", f"Error inesperado obteniendo token de eBay: {error}")
        raise HTTPException(status_code=500, detail="No se pudo obtener token de eBay.") from error

    if not token:
        raise HTTPException(status_code=500, detail="No se pudo obtener token de eBay.")

    params = parse_query_with_ia(req.query)
    if req.maxPrice is not None:
        params["maxPrice"] = str(int(req.maxPrice))
        
    _log("SEARCH", f"Busqueda procesada para '{req.query}': {_truncate_text(params)}")

    query_params = {
        "q": params.get("q"),
        "category_ids": params.get("categoryId"),
        "limit": 50,
    }

    filters = []

    # Opciones de compra (Subasta / Precio Fijo / Todos)
    if req.buyingOptions == "FIXED_PRICE":
        filters.append("buyingOptions:{FIXED_PRICE}")
    elif req.buyingOptions == "AUCTION":
        filters.append("buyingOptions:{AUCTION}")

    # Condición por casillas seleccionadas explícitamente o por inferencia
    condition_ids = req.conditionIds if (req.conditionIds and len(req.conditionIds) > 0) else (params.get("conditionIds") or list(DEFAULT_SEARCH_CONDITION_IDS))
    seller_usernames = _normalize_username_list(params.get("sellerUsernames") or params.get("seller"))
    if condition_ids:
        filters.append(f"conditionIds:{{{'|'.join(str(value) for value in condition_ids)}}}")
    if params.get("maxPrice") and str(params.get("maxPrice")).isdigit():
        filters.append(f"price:[{params.get('minPrice', '0')}..{params['maxPrice']}],priceCurrency:USD")
    if seller_usernames:
        filters.append(f"sellers:{{{'|'.join(seller_usernames)}}}")

    if filters:
        query_params["filter"] = ",".join(filters)

    # Ordenamiento (Ending Soonest / Newly Listed / Price)
    if req.sortOrder:
        query_params["sort"] = req.sortOrder


    try:
        response = EBAY_SESSION.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
            },
            params=query_params,
            timeout=30,
        )
    except requests.RequestException as error:
        _log("SEARCH", f"Fallo consultando Browse API de eBay: {error}")
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar con eBay para buscar ofertas en tiempo real. Intenta de nuevo en un momento.",
        ) from error

    if response.status_code != 200:
        _log("SEARCH", f"eBay devolvio {response.status_code}: {_truncate_text(response.text)}")
        raise HTTPException(status_code=response.status_code, detail=f"Error de eBay: {response.text}")

    items = response.json().get("itemSummaries", [])
    
    # ── FALLBACK AUTO-RETRY: Si la consulta estricta da 0 resultados ──
    if not items and params.get("q"):
        simple_q = re.sub(r"\b\d+GB\b|\bSSD\b|\bRAM\b|\bGen\s*\d+\b", "", str(params.get("q")), flags=re.IGNORECASE)
        simple_q = re.sub(r"\s+", " ", simple_q).strip()
        if simple_q and simple_q.lower() != str(params.get("q")).lower():
            _log("SEARCH", f"0 resultados. Reintentando busqueda con query simplificada: '{simple_q}'")
            fallback_params = dict(query_params)
            fallback_params["q"] = simple_q
            try:
                fb_resp = EBAY_SESSION.get(
                    "https://api.ebay.com/buy/browse/v1/item_summary/search",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
                    },
                    params=fallback_params,
                    timeout=30,
                )
                if fb_resp.status_code == 200:
                    items = fb_resp.json().get("itemSummaries", [])
                    _log("SEARCH", f"Reintento simplificado devolvio {len(items)} item(s).")
            except Exception as fb_err:
                _log("SEARCH", f"Error en reintento simplificado: {fb_err}")

    _log("SEARCH", f"eBay devolvio {len(items)} item(s). Procesando con {SEARCH_THREAD_WORKERS} worker(s).")

    def process_item(item: Dict[str, Any]) -> Dict[str, Any] | None:

        try:
            price_val = float(item["price"]["value"])
            title = item["title"]

            if str(params.get("categoryId") or "") == "175672" and not es_titulo_valido(title):
                _log("SEARCH", f"Se descarto pieza/accesorio/chatarra por titulo: {_truncate_text(title)}")
                return None

            # Rechazo estricto de procesadores antiguos (ej. i7-4700MQ)
            if is_ancient_processor(title):
                _log("SEARCH", f"Se descarto item por procesador de vieja generacion: {_truncate_text(title)}")
                return None
            
            # Filtro manual de seguridad
            if req.maxPrice is not None and price_val > req.maxPrice:
                return None

            item_url = item["itemWebUrl"]
            image_url = item.get("image", {}).get("imageUrl")
            all_images = _collect_item_images(item)
            condition = item.get("condition", "Used")
            seller_notes = item.get("conditionDescription", "")
            seller_info = _extract_item_seller_info(item)

            buying_options = item.get("buyingOptions", [])
            es_subasta = "AUCTION" in buying_options
            item_end_date = item.get("itemEndDate", "")
            tiempo_restante = calcular_tiempo_restante(item_end_date) if (es_subasta and item_end_date) else ""

            if es_subasta and (tiempo_restante == "Terminada" or "terminad" in tiempo_restante.lower() or item.get("itemEnded")):
                _log("SEARCH", f"Se descarto subasta finalizada: {_truncate_text(title)}")
                return None

            if not _condition_matches_preference(condition, params.get("conditionPreference", "")):

                _log(
                    "SEARCH",
                    f"Se descarto item por condicion '{condition}' para preferencia '{params.get('conditionPreference', '')}'.",
                )
                return None
            if not _title_matches_brand_hints(title, params.get("brandHints", [])):
                _log(
                    "SEARCH",
                    f"Se descarto item por marca para pistas {params.get('brandHints', [])}: {_truncate_text(title)}",
                )
                return None
            if not _item_matches_seller_filters(item, seller_usernames):
                _log(
                    "SEARCH",
                    f"Se descarto item por seller '{seller_info.get('display_name', '')}' para filtros {seller_usernames}.",
                )
                return None

            category_id = item.get("categories", [{}])[0].get("categoryId")
            product_type = "laptop"
            if category_id == "9355":
                product_type = "phone"
            elif category_id == "175669":
                product_type = "ssd"
            elif category_id == "170083":
                product_type = "ram"

            rentabilidad = None
            if analizador_rent:
                rentabilidad = analizador_rent.analizar(title, price_val, {}, product_type, False)

            return {
                "id": item["itemId"],
                "titulo": title,
                "precio": price_val,
                "precio_texto": f"${price_val}",
                "enlace": item_url,
                "imagen_url": image_url,
                "imagenes": all_images,
                "todas_las_imagenes": all_images,
                "condicion": condition,

                "seller_notes": seller_notes,
                "seller_username": seller_info.get("username"),
                "seller_user_id": seller_info.get("user_id"),
                "vendedor": seller_info.get("display_name") or "eBay",
                "es_subasta": False,
                "rentabilidad": rentabilidad,
            }
        except Exception as error:
            _log("SEARCH", f"Se descarto un item invalido de eBay: {_truncate_text(error)}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=SEARCH_THREAD_WORKERS) as executor:
        resultados = [item for item in executor.map(process_item, items) if item]

    resultados.sort(
        key=lambda item: (item.get("rentabilidad", {}).get("margen_estimado") or -9999),
        reverse=True,
    )

    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    _log("SEARCH", f"Busqueda completada en {elapsed_ms} ms con {len(resultados)} resultado(s).")

    # Guardar items frescos en Supabase para mantener dinamico el catalogo de inicio
    if supabase_client and resultados:
        for res in resultados[:20]:
            try:
                row = {
                    "ebay_item_id": str(res.get("id")),
                    "titulo": res.get("titulo"),
                    "precio": res.get("precio"),
                    "precio_texto": res.get("precio_texto"),
                    "enlace": res.get("enlace"),
                    "imagen_url": res.get("imagen_url"),
                    "condicion": res.get("condicion"),
                    "vendedor": res.get("vendedor"),
                }
                supabase_client.upsert("productos", row, conflict_col="ebay_item_id")
            except Exception as ex:
                _log("DB", f"Error guardando item en productos: {ex}")

    for item in resultados:
        item["tienda"] = resolve_store_from_url(item.get("enlace"), "eBay")

    def _make_serializable(obj):
        if isinstance(obj, dict):
            return {k: _make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_make_serializable(v) for v in obj]
        elif isinstance(obj, (int, float, str, bool)) or obj is None:
            return obj
        return str(obj)

    return {"query_ia": _make_serializable(params), "results": _make_serializable(resultados)}





@app.get("/api/catalog/refresh")
async def refresh_catalog():
    """Genera y devuelve un catalogo dinamico con ofertas reales recién extraidas combinando tiendas."""
    keywords = ["ThinkPad laptop", "Dell Latitude", "MacBook Air", "NVMe SSD 1TB", "Ryzen 7 laptop", "HP EliteBook", "ASUS ROG"]
    selected_query = random.choice(keywords)
    
    try:
        res = await search_ebay(SearchRequest(query=selected_query, buyingOptions="ALL", sortOrder="newlyListed"))
        raw_results = res.get("results", []) if isinstance(res, dict) else []
        clean_results = [it for it in raw_results if not is_ancient_processor(it.get("titulo", ""))]
        
        catalog_items = []
        for item in clean_results:
            item["tienda"] = resolve_store_from_url(item.get("enlace"), "eBay")
            catalog_items.append(item)
            
            if supabase_client:
                try:
                    row = {
                        "ebay_item_id": str(item.get("id")),
                        "titulo": item.get("titulo"),
                        "precio": item.get("precio"),
                        "precio_texto": item.get("precio_texto"),
                        "enlace": item.get("enlace"),
                        "imagen_url": item.get("imagen_url"),
                        "condicion": item.get("condicion"),
                        "vendedor": item.get("vendedor"),
                    }
                    supabase_client.upsert("productos", row, conflict_col="ebay_item_id")
                except Exception as ex:
                    _log("DB", f"Error guardando item de catalogo: {ex}")

        return {"status": "success", "results": catalog_items, "query": selected_query}
    except Exception as err:
        _log("CATALOG", f"Error refrescando catalogo: {err}")
        return {"status": "error", "results": [], "error": str(err)}


ML_FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "ml_feedback.json")

class MLFeedbackRequest(BaseModel):
    producto_id: str
    titulo: str
    precio: float = 0
    imagen_url: Optional[str] = None
    motivo_general: str = ""
    tags: List[str] = []
    anotaciones: List[Dict[str, Any]] = []
    vendedor: str = ""
    marca: str = ""

@app.post("/api/feedback/equivocado")
async def submit_ml_feedback(req: MLFeedbackRequest):
    entry = {
        "id": f"fb_{int(time.time()*1000)}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "producto_id": req.producto_id,
        "titulo": req.titulo,
        "precio": req.precio,
        "imagen_url": req.imagen_url,
        "motivo_general": req.motivo_general,
        "tags": req.tags,
        "anotaciones": req.anotaciones,
        "vendedor": req.vendedor,
        "marca": req.marca,
    }

    try:
        existing = []
        if os.path.exists(ML_FEEDBACK_FILE):
            with open(ML_FEEDBACK_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(entry)
        with open(ML_FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        _log("ML", f"Error guardando feedback: {ex}")

    if sb_client:
        try:
            sb_client.upsert("ml_feedback", {
                "feedback_id": entry["id"],
                "producto_id": req.producto_id,
                "titulo": req.titulo,
                "precio": req.precio,
                "motivo_general": req.motivo_general,
                "tags": json.dumps(req.tags),
                "anotaciones": json.dumps(req.anotaciones),
                "vendedor": req.vendedor,
            }, conflict_col="feedback_id")
        except Exception as ex:
            _log("ML", f"Error guardando feedback en Supabase: {ex}")

    n_fotos = len(req.anotaciones)
    n_shapes = sum(len(a.get("shapes", [])) for a in req.anotaciones)
    _log("ML", f"Feedback recibido: {n_fotos} foto(s) anotada(s), {n_shapes} marcas, tags={req.tags}")
    return {"status": "success", "id": entry["id"]}


@app.get("/api/ml/ejemplos")
async def get_ml_examples():
    try:
        if os.path.exists(ML_FEEDBACK_FILE):
            with open(ML_FEEDBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"status": "success", "ejemplos": data[-50:]}
    except Exception as ex:
        _log("ML", f"Error leyendo ejemplos: {ex}")
    return {"status": "success", "ejemplos": []}



@app.get("/api/item-images")

def get_item_images(item_id: str):
    """Obtiene la coleccion completa de fotos HD de un producto usando la Browse API de eBay."""
    if not item_id:
        return {"status": "error", "imagenes": []}

    try:
        token = obtener_token_ebay_app(config)
        safe_item_id = urllib.parse.quote(item_id)
        url = f"https://api.ebay.com/buy/browse/v1/item/{safe_item_id}"
        resp = EBAY_SESSION.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": config.get("ebay_marketplace_id", "EBAY_US"),
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            images = []
            primary = data.get("image", {}).get("imageUrl")
            if primary:
                images.append(primary)
            for img_obj in data.get("additionalImages", []):
                u = img_obj.get("imageUrl")
                if u and u not in images:
                    images.append(u)
            return {"status": "success", "imagenes": images}
    except Exception as e:
        _log("IMAGES", f"Error obteniendo imagenes para {item_id}: {e}")

    return {"status": "error", "imagenes": []}


@app.post("/api/cart/send-telegram")

async def send_cart_to_telegram(req: CartSendRequest):
    """Envia los productos del carrito a Telegram con una etiqueta especial."""
    if not req.items:
        raise HTTPException(status_code=400, detail="Carrito vacio")

    destinos = todos_los_destinos(config)
    if not destinos:
        _log("TELEGRAM", "No hay destinos de Telegram configurados. Revisa TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en .env")
        raise HTTPException(status_code=500, detail="No hay destinos de Telegram configurados. Revisa tu .env")

    enviados = 0
    encabezado = f"🛒 <b>RECOMENDACION DE MELTYDEAYS | {len(req.items)} PRODUCTOS</b> 🛒"
    _log("TELEGRAM", f"Enviando {len(req.items)} producto(s) del carrito a {len(destinos)} destino(s) de Telegram.")

    for token, chat_id in destinos:
        enviar_telegram_texto(token, chat_id, encabezado)

    for idx, item in enumerate(req.items, 1):
        _log("TELEGRAM", f"  Procesando item {idx}/{len(req.items)}: {_truncate_text(item.get('titulo', '(sin titulo)'), 80)}")

        oferta_dict = {
            "titulo": item.get("titulo"),
            "condicion": item.get("condicion"),
            "precio_texto": item.get("precio_texto") or f"${item.get('precio')}",
            "vendedor": item.get("vendedor", "Recomendado"),
            "enlace": item.get("enlace"),
            "imagen_url": item.get("imagen_url"),
            "es_subasta": item.get("es_subasta", False),
            "procesador": item.get("procesador", ""),
        }

        rentabilidad = item.get("rentabilidad")
        if not rentabilidad and item.get("precio_estimado_nic"):
            rentabilidad = {
                "tiene_referencias": True,
                "margen_estimado": item.get("margen_estimado", 0),
                "porcentaje_ganancia": item.get("porcentaje_ganancia", 0),
                "precio_estimado_nic": item.get("precio_estimado_nic", 0),
            }

        for token, chat_id in destinos:
            enviar_telegram_foto(
                token=token,
                chat_id=chat_id,
                oferta=oferta_dict,
                rentabilidad=rentabilidad,
                etiqueta_especial="Recomendacion Manual",
            )
        enviados += 1

    _log("TELEGRAM", f"Envio completado: {enviados}/{len(req.items)} producto(s) enviados a Telegram.")
    return {"status": "success", "enviados": enviados}


@app.post("/api/analyze-image")
async def analyze_image(req: ImageAnalysisRequest):
    """Analiza imagenes bajo demanda usando Groq Vision."""
    if not analizador_vis:
        raise HTTPException(status_code=500, detail="Analizador visual no configurado (falta GROQ_KEY)")
    if not req.imagenes:
        raise HTTPException(status_code=400, detail="URL de imagen vacia")

    _log("VISION", f"Solicitud de analisis para '{req.titulo}' con {len(req.imagenes)} imagen(es).")
    return analizador_vis.analizar_imagen(req.imagenes, req.titulo, req.seller_notes, req.condicion)


@app.post("/api/build-collage")
async def build_collage_preview(req: ImageAnalysisRequest):
    """Genera la imagen del collage numerado en base64 para vista previa rapida."""
    if not req.imagenes:
        raise HTTPException(status_code=400, detail="Sin imagenes")
    
    if analizador_vis:
        urls = analizador_vis.prepare_product_image_urls(req.imagenes, 9)
        collage_b64 = analizador_vis._build_collage(urls)
        if collage_b64:
            return {"status": "success", "collage_url": collage_b64}
            
    return {"status": "error", "message": "No se pudo componer el collage"}


class ParseLocalImageRequest(BaseModel):
    image_url: str = None
    image_base64: str = None
    original_title: str = None
    extra_specs: dict = None
    item_url: str = None

@app.post("/api/parse-local-image")
async def parse_local_image(req: ParseLocalImageRequest):
    """
    Recibe imagen/URL y pide a la IA extraer el titulo normalizado.
    Si item_url esta presente, extrae el ID y descarga los specs de eBay primero.
    """
    if not req.image_url and not req.image_base64:
        raise HTTPException(status_code=400, detail="Se requiere image_url o image_base64")
    
    specs = req.extra_specs or {}
    
    item_id = None
    if req.item_url:
        import re
        match = re.search(r"/itm/(?:[^/]+/)?(\d+)", req.item_url)
        if match:
            item_id = match.group(1)

    if item_id:
        try:
            # Format requires 'v1|item_id|0'
            formatted_id = f"v1|{item_id}|0"
            detalle = obtener_detalle_item_api(config, formatted_id)
            if not detalle:
                detalle = obtener_detalle_item_api(config, item_id) # fallback raw id
            if detalle:
                aspectos = detalle.get("localizedAspects", [])
                for a in aspectos:
                    name = (a.get("name") or "").strip().lower()
                    value = (a.get("value") or "").strip()
                    if name and value:
                        # Map common names to specs
                        if "processor" in name or "cpu" in name:
                            specs["procesador"] = value
                        elif "ram" in name or "memory" in name:
                            specs["ram"] = value
                        elif "storage" in name or "capacity" in name or "hard drive" in name:
                            specs["ssd"] = value
                        elif "model" in name:
                            specs["modelo"] = value
                        elif "color" in name:
                            specs["color"] = value
                        elif "network" in name:
                            specs["red"] = value
        except Exception as e:
            _log("API", f"Error obteniendo detalles de eBay para {item_id}: {e}")
    
    return analizador_vis.extraer_titulo_local(req.image_url, req.image_base64, req.original_title, specs)


# ═══════════════════════════════════════════════════════════
# CONTROL DEL PROCESO BOT (subprocess)
# ═══════════════════════════════════════════════════════════

import threading

_bot_process: Optional[subprocess.Popen] = None
_bot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_main.py")
_bot_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_output.log")
_python_exe = sys.executable
_bot_should_run = False  # Indica si el usuario quiere que el bot esté corriendo
_bot_watchdog_thread: Optional[threading.Thread] = None


def _is_bot_alive() -> bool:
    """Verifica si el proceso del bot sigue vivo."""
    global _bot_process
    if _bot_process is None:
        return False
    return _bot_process.poll() is None


def _start_bot() -> bool:
    """Lanza bot_main.py como subprocess en segundo plano."""
    global _bot_process, _bot_should_run
    if _is_bot_alive():
        _log("BOT", "El bot ya esta corriendo, ignorando inicio duplicado.")
        return True
    try:
        # Redirigir output a archivo de log (evita que el buffer de PIPE se llene y congele el proceso)
        log_handle = open(_bot_log_file, "a", encoding="utf-8", buffering=1)
        log_handle.write(f"\n{'='*60}\n[BOT] Iniciando bot - {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")
        log_handle.flush()

        _bot_process = subprocess.Popen(
            [_python_exe, "-u", _bot_script],  # -u = unbuffered output
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        _bot_should_run = True
        _log("BOT", f"Bot iniciado (PID={_bot_process.pid}). Logs en: {_bot_log_file}")
        _ensure_watchdog()
        return True
    except Exception as e:
        _log("BOT", f"Error lanzando bot: {e}")
        return False


def _stop_bot() -> bool:
    """Detiene el proceso del bot."""
    global _bot_process, _bot_should_run
    _bot_should_run = False
    if not _is_bot_alive():
        _log("BOT", "El bot no estaba corriendo.")
        _bot_process = None
        return True
    try:
        _bot_process.terminate()
        _bot_process.wait(timeout=10)
        _log("BOT", f"Bot detenido (PID={_bot_process.pid}).")
        _bot_process = None
        return True
    except subprocess.TimeoutExpired:
        _bot_process.kill()
        _bot_process = None
        _log("BOT", "Bot forzado a detenerse (kill).")
        return True
    except Exception as e:
        _log("BOT", f"Error deteniendo bot: {e}")
        return False


def _watchdog_loop():
    """Hilo que vigila el bot y lo reinicia si se cae (mientras _bot_should_run sea True)."""
    global _bot_process
    _log("BOT", "Watchdog iniciado: vigilando proceso del bot.")
    while _bot_should_run:
        time.sleep(15)
        if _bot_should_run and not _is_bot_alive():
            exit_code = _bot_process.returncode if _bot_process else "N/A"
            _log("BOT", f"⚠️ Bot caído (exit code: {exit_code}). Reiniciando en 5s...")
            time.sleep(5)
            if _bot_should_run:
                _start_bot()
    _log("BOT", "Watchdog detenido.")


def _ensure_watchdog():
    """Inicia el watchdog si no está corriendo."""
    global _bot_watchdog_thread
    if _bot_watchdog_thread and _bot_watchdog_thread.is_alive():
        return
    _bot_watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True)
    _bot_watchdog_thread.start()


class BotConfigRequest(BaseModel):
    max_precio: Optional[float] = None
    is_running: Optional[bool] = None
    filters: Optional[dict] = None

@app.get("/api/config/bot")
async def get_bot_config():
    """Obtiene la configuracion actual del bot + estado real del proceso + filtros."""
    process_alive = _is_bot_alive()
    
    default_filters = {
        "categorias_activas": ["Intel Core i5", "Intel Core i7", "Intel Core i9", "Ryzen 3", "Ryzen 5", "Ryzen 7", "Ryzen 9", "Intel Core i3"],
        "estados_activos": ["New", "Open box", "Certified Refurbished", "Excellent Refurbished", "Very Good Refurbished", "Good Refurbished", "Used"]
    }
    
    if not sb_client:
        config_actual = obtener_configuracion()
        return {
            "max_precio": config_actual.get("max_precio", 200),
            "is_running": process_alive,
            "last_seen": None,
            "process_alive": process_alive,
            "filters": default_filters
        }
        
    try:
        data = sb_client.select("bot_settings", "id=eq.1", limit=1)
        if data and len(data) > 0:
            row = data[0]
            # Si no existe la columna filters, devolvera None
            filtros_db = row.get("filters")
            if not filtros_db:
                filtros_db = default_filters
            return {
                "max_precio": float(row.get("budget", 250)),
                "is_running": bool(row.get("is_running", True)),
                "last_seen": row.get("last_seen"),
                "process_alive": process_alive,
                "filters": filtros_db
            }
    except Exception as e:
        _log("CONFIG", f"Error leyendo bot_settings: {e}")
        
    config_actual = obtener_configuracion()
    return {
        "max_precio": config_actual.get("max_precio", 200),
        "is_running": process_alive,
        "last_seen": None,
        "process_alive": process_alive,
        "filters": default_filters
    }

@app.post("/api/config/bot")
async def update_bot_config(req: BotConfigRequest):
    """Actualiza la configuracion del bot en Supabase y arranca/detiene el proceso."""
    update_data = {}
    if req.max_precio is not None:
        update_data["budget"] = req.max_precio
    if req.is_running is not None:
        update_data["is_running"] = req.is_running
    if req.filters is not None:
        update_data["filters"] = req.filters
        
    if not update_data:
        return {"status": "success", "message": "Nothing to update"}
    
    # Guardar en Supabase si esta disponible
    if sb_client:
        try:
            sb_client.update("bot_settings", update_data, "id=eq.1")
        except Exception as e:
            _log("CONFIG", f"Error actualizando bot_settings: {e}")
            if "Could not find the 'filters' column" in str(e):
                _log("CONFIG", "LA COLUMNA 'filters' NO EXISTE EN LA TABLA bot_settings. AÑADELO EN SUPABASE.")
    
    # Guardar también localmente por si la base de datos no está o falló
    if req.filters is not None:
        try:
            with open("user_filters.json", "w", encoding="utf-8") as f:
                json.dump(req.filters, f, indent=2)
        except Exception as e:
            pass
    
    # Arrancar o detener el proceso real
    if req.is_running is True:
        ok = _start_bot()
        if not ok:
            raise HTTPException(status_code=500, detail="No se pudo iniciar el bot")
    elif req.is_running is False:
        _stop_bot()
    
    _log("CONFIG", f"Configuracion del bot actualizada: {update_data} | proceso vivo: {_is_bot_alive()}")
    return {"status": "success", "process_alive": _is_bot_alive(), **update_data}


@app.get("/api/bot/status")
async def bot_status():
    """Estado en vivo del proceso del bot."""
    alive = _is_bot_alive()
    pid = _bot_process.pid if _bot_process and alive else None
    return {"process_alive": alive, "pid": pid, "should_run": _bot_should_run}

@app.get("/api/bot/logs")
async def bot_logs():
    """Últimas líneas del log del bot."""
    try:
        if not os.path.exists(_bot_log_file):
            return {"logs": "No hay logs aún. Inicia el bot primero."}
        with open(_bot_log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # Últimas 80 líneas
        tail = lines[-80:]
        return {"logs": "".join(tail)}
    except Exception as e:
        return {"logs": f"Error leyendo logs: {e}"}


# ═══════════════════════════════════════════════════════════
# INVENTARIO Y FINANZAS
# ═══════════════════════════════════════════════════════════

class InventarioCreateRequest(BaseModel):
    producto_id: Optional[int] = None
    titulo: str
    tipo: str = "laptop"
    costo_total_usd: float
    precio_venta_esperado: Optional[float] = None
    estado: str = "en_transito"
    tracking_number: Optional[str] = None
    notas: Optional[str] = None

class InventarioUpdateRequest(BaseModel):
    titulo: Optional[str] = None
    costo_total_usd: Optional[float] = None
    precio_venta_esperado: Optional[float] = None
    precio_venta_real: Optional[float] = None
    estado: Optional[str] = None
    tracking_number: Optional[str] = None
    notas: Optional[str] = None

@app.get("/api/inventario")
async def get_inventario():
    """Lista todo el inventario."""
    if not sb_client:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        data = sb_client.select("inventario", "order=comprado_en.desc", limit=200)
        return {"items": data}
    except Exception as e:
        _log("INVENTARIO", f"Error listando inventario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inventario")
async def create_inventario(req: InventarioCreateRequest):
    """Registra una nueva compra en el inventario."""
    if not sb_client:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        payload = req.model_dump(exclude_none=True)
        result = sb_client.insert("inventario", payload)
        if not result:
            raise HTTPException(status_code=500, detail="No se pudo insertar en inventario")
        _log("INVENTARIO", f"Nuevo item registrado: {req.titulo} (${req.costo_total_usd})")
        return {"status": "success", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        _log("INVENTARIO", f"Error creando item: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/inventario/{item_id}")
async def update_inventario(item_id: int, req: InventarioUpdateRequest):
    """Actualiza un item del inventario (estado, precio de venta, tracking, etc.)."""
    if not sb_client:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        payload = req.model_dump(exclude_none=True)
        if not payload:
            return {"status": "success", "message": "Nothing to update"}
            
        # Si se marca como vendido y tiene precio de venta real, guardar fecha
        if payload.get("estado") == "vendido" and payload.get("precio_venta_real"):
            import datetime
            payload["vendido_en"] = datetime.datetime.utcnow().isoformat()
            
        result = sb_client.update("inventario", payload, f"id=eq.{item_id}")
        _log("INVENTARIO", f"Item {item_id} actualizado: {payload}")
        return {"status": "success", "item": result}
    except Exception as e:
        _log("INVENTARIO", f"Error actualizando item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/inventario/{item_id}")
async def delete_inventario(item_id: int):
    """Elimina un item del inventario."""
    if not sb_client:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        sb_client._session().delete(
            f"{sb_client.url}/rest/v1/inventario?id=eq.{item_id}",
            headers=sb_client.headers,
            timeout=15,
        )
        _log("INVENTARIO", f"Item {item_id} eliminado del inventario.")
        return {"status": "success"}
    except Exception as e:
        _log("INVENTARIO", f"Error eliminando item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/finanzas")
async def get_finanzas():
    """Dashboard de finanzas: resume inversion, ventas, ganancias."""
    if not sb_client:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        data = sb_client.select("inventario", "", limit=500)
        
        total_invertido = 0.0
        total_vendido = 0.0
        ganancia_neta = 0.0
        en_transito = 0
        en_stock = 0
        vendidos = 0
        items_con_ganancia = []
        
        for item in data:
            costo = float(item.get("costo_total_usd") or 0)
            venta_real = float(item.get("precio_venta_real") or 0)
            estado = item.get("estado", "en_transito")
            
            total_invertido += costo
            
            if estado == "en_transito":
                en_transito += 1
            elif estado == "en_stock":
                en_stock += 1
            elif estado == "vendido":
                vendidos += 1
                total_vendido += venta_real
                ganancia_neta += (venta_real - costo)
                if costo > 0:
                    items_con_ganancia.append({
                        "titulo": item.get("titulo", ""),
                        "costo": costo,
                        "venta": venta_real,
                        "ganancia": round(venta_real - costo, 2),
                        "roi": round(((venta_real - costo) / costo) * 100, 1),
                    })
        
        roi_global = round(((ganancia_neta / total_invertido) * 100), 1) if total_invertido > 0 else 0
        
        # Top 5 ventas más rentables
        items_con_ganancia.sort(key=lambda x: x["ganancia"], reverse=True)
        
        return {
            "total_invertido": round(total_invertido, 2),
            "total_vendido": round(total_vendido, 2),
            "ganancia_neta": round(ganancia_neta, 2),
            "roi_global": roi_global,
            "en_transito": en_transito,
            "en_stock": en_stock,
            "vendidos": vendidos,
            "total_items": len(data),
            "top_ventas": items_con_ganancia[:5],
        }
    except Exception as e:
        _log("FINANZAS", f"Error calculando finanzas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════
# TRACKING DE PAQUETES
# ═══════════════════════════════════════════════════════════

@app.get("/api/tracking/{tracking_number}")
async def track_package(tracking_number: str):
    """Consulta el estado real de un paquete. Si está entregado, actualiza inventario automáticamente."""
    if not tracking_number or len(tracking_number.strip()) < 5:
        raise HTTPException(status_code=400, detail="Tracking number inválido")
    
    _log("TRACKING", f"Consultando tracking: {tracking_number}")
    result = lookup_tracking(tracking_number)
    _log("TRACKING", f"Resultado: carrier={result['name']}, status={result.get('status_text', 'N/A')}")
    
    # Auto-update: si el paquete fue entregado, marcar en inventario como en_stock
    if result.get("status") == "delivered" and sb_client:
        try:
            cleaned = tracking_number.strip().upper().replace(" ", "")
            items = sb_client.select("inventario", f"tracking_number=eq.{cleaned}&estado=eq.en_transito", limit=10)
            if items:
                for item in items:
                    sb_client.update("inventario", {"estado": "en_stock"}, f"id=eq.{item['id']}")
                    _log("TRACKING", f"Auto-actualizado: item #{item['id']} '{item.get('titulo','')}' → en_stock (entregado)")
                result["auto_updated"] = True
                result["auto_updated_count"] = len(items)
        except Exception as e:
            _log("TRACKING", f"Error auto-actualizando inventario: {e}")
    
    return result

@app.get("/api/tracking/{tracking_number}/detect")
async def detect_package_carrier(tracking_number: str):
    """Solo detecta el carrier sin hacer lookup."""
    return detect_carrier(tracking_number)


# ═══════════════════════════════════════════════════════════
# MACHINE LEARNING FEEDBACK ("EQUIVOCADO")
# ═══════════════════════════════════════════════════════════

class EquivocadoFeedbackRequest(BaseModel):
    producto_id: Optional[str] = None
    titulo: str
    precio: Optional[float] = None
    imagen_url: Optional[str] = None
    motivo_error: str
    vendedor: Optional[str] = None
    marca: Optional[str] = None

@app.post("/api/feedback/equivocado")
async def report_wrong_product(req: EquivocadoFeedbackRequest):
    """Registra una oferta marcada como 'Equivocado', guarda su imagen y su motivo de rechazo."""
    if not req.titulo or not req.motivo_error:
        raise HTTPException(status_code=400, detail="Falta título o motivo del error")

    local_img_path = ""
    # Descargar y guardar imagen localmente como referencia para la IA
    if req.imagen_url and req.imagen_url.startswith("http"):
        try:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml_negativos")
            os.makedirs(folder, exist_ok=True)
            file_name = f"neg_{int(time.time())}_{re.sub(r'[^a-zA-Z0-9]', '_', req.titulo[:20])}.jpg"
            full_path = os.path.join(folder, file_name)
            
            res = requests.get(req.imagen_url, timeout=10)
            if res.status_code == 200:
                with open(full_path, "wb") as img_file:
                    img_file.write(res.content)
                local_img_path = f"ml_negativos/{file_name}"
        except Exception as e:
            _log("ML", f"Error descargando imagen negativa: {e}")

    record = {
        "producto_id": req.producto_id or "",
        "titulo": req.titulo,
        "precio": req.precio or 0.0,
        "imagen_url": req.imagen_url or "",
        "imagen_local_path": local_img_path,
        "motivo_error": req.motivo_error,
        "vendedor": req.vendedor or "",
        "marca": req.marca or "",
        "registrado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # 1. Guardar en Supabase
    if sb_client:
        try:
            sb_client.insert("ejemplos_equivocados", record)
        except Exception as e:
            _log("ML", f"Error insertando en Supabase ejemplos_equivocados: {e}")

    # 2. Guardar en archivo local json para respaldo e inyección en IA
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplos_equivocados.json")
    local_data = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                local_data = json.load(f)
        except Exception:
            local_data = []
    
    local_data.append(record)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(local_data, f, indent=2, ensure_ascii=False)

    # 3. Marcar inmediatamente como rechazado/enviado para que no vuelva a salir en la lista
    if req.producto_id or req.imagen_url:
        try:
            from utils import cargar_ofertas_enviadas, guardar_ofertas_enviadas
            enviadas = cargar_ofertas_enviadas()
            if req.producto_id:
                enviadas.add(req.producto_id)
            guardar_ofertas_enviadas(enviadas)
        except Exception as e:
            _log("ML", f"Error agregando item rechazado a lista local: {e}")

    _log("ML", f"Registrado reporte 'Equivocado' para: '{req.titulo[:50]}' | Imagen guardada en: {local_img_path or 'n/a'}")
    return {"status": "success", "record": record}

@app.get("/api/ml/ejemplos")
async def list_wrong_examples():
    """Retorna la lista de ejemplos negativos registrados."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplos_equivocados.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return {"items": json.load(f)}
        except Exception as e:
            pass
    return {"items": []}


# ═══════════════════════════════════════════════════════════
# AUTOCOMPLETADO Y RECOMENDACIÓN DE LÍNEAS DE LAPTOP VÍA IA
# ═══════════════════════════════════════════════════════════

@app.get("/api/ai/laptop-lines")
async def get_laptop_lines(marca: Optional[str] = "", query: Optional[str] = ""):
    """Busca e investiga líneas de laptops en tiempo real vía Gemini e integra el catálogo local."""
    from config import MARCAS_Y_LINEAS
    
    marca_clean = (marca or "").strip().lower()
    query_clean = (query or "").strip().lower()

    base_lines = MARCAS_Y_LINEAS.get(marca_clean, [])
    if not base_lines and not marca_clean:
        # Si no hay marca, aplanar todas las líneas
        for l in MARCAS_Y_LINEAS.values():
            base_lines.extend(l)
        base_lines = list(set(base_lines))

    matching = [line for line in base_lines if query_clean in line.lower()]

    # Si hay query activo y pocas coincidencias locales, consultar Gemini en tiempo real
    api_key_gemini = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key_gemini and query_clean and len(matching) < 3:
        try:
            prompt_lines = f"""
            Devuelve un JSON estrictamente con un array de strings llamado 'lineas' con las 5 líneas/modelos de laptop más populares y reales de la marca '{marca_clean or 'laptop'}' que coincidan o contengan '{query_clean}'.
            Ejemplo output: {{"lineas": ["Predator Helios", "Nitro V", "Nitro 5"]}}
            """
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key_gemini}"
            payload = {"contents": [{"parts": [{"text": prompt_lines}]}], "generationConfig": {"responseMimeType": "application/json"}}
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
            if resp.status_code == 200:
                res_data = resp.json()
                raw_txt = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                parsed = json.loads(raw_txt)
                ai_lines = parsed.get("lineas", [])
                for line in ai_lines:
                    if line and line not in matching:
                        matching.append(line)
        except Exception as e:
            _log("AI_LINES", f"Error consultando líneas con Gemini: {e}")

    return {"marca": marca_clean, "query": query_clean, "lineas": matching}



if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=8000)
