import concurrent.futures
import json
import os
import sys
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import obtener_configuracion, todos_los_destinos
from ebay_client import obtener_token_ebay_app
from supabase_integration import AnalizadorRentabilidad, AnalizadorVisual, SupabaseClient
from telegram_utils import enviar_telegram_foto, enviar_telegram_texto

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
SEARCH_THREAD_WORKERS = 8

load_dotenv()
config = obtener_configuracion()

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


class SearchRequest(BaseModel):
    query: str


class CartSendRequest(BaseModel):
    items: List[Dict[str, Any]]


class ImageAnalysisRequest(BaseModel):
    imagenes: List[str]
    titulo: str
    seller_notes: str = ""


groq_key = config.get("groq_api_key")
sb_url = config.get("supabase_url")
sb_key = config.get("supabase_service_key")

sb_client = SupabaseClient(sb_url, sb_key) if sb_url and sb_key else None
analizador_rent = AnalizadorRentabilidad(groq_key or "", sb_client) if sb_client else None
analizador_vis = AnalizadorVisual(groq_key) if groq_key else None


def parse_query_with_ia(query: str) -> Dict[str, Any]:
    """Usa IA para convertir lenguaje natural en parametros de busqueda de eBay."""
    if not groq_key:
        return {"q": query, "categoryId": "175672", "maxPrice": "250", "minPrice": "10", "seller": ""}

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
  "seller": "nombre del vendedor si lo menciona, o vacio"
}}"""

    started_at = time.perf_counter()
    try:
        response = GROQ_SESSION.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
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
            parsed = _extract_json_object(content)
            _log("SEARCH", f"Parse IA completado en {elapsed_ms} ms: {_truncate_text(parsed)}")
            return parsed

        _log(
            "SEARCH",
            f"Parse IA devolvio {response.status_code} en {elapsed_ms} ms: {_truncate_text(response.text)}",
        )
    except Exception as error:
        _log("SEARCH", f"Error parseando consulta con IA: {error}")

    return {"q": query, "categoryId": "175672", "maxPrice": "250", "minPrice": "10", "seller": ""}


@app.post("/api/search")
async def search_ebay(req: SearchRequest):
    """Busqueda en tiempo real usando eBay Browse API y Rentabilidad IA."""
    started_at = time.perf_counter()
    token = obtener_token_ebay_app(config)
    if not token:
        raise HTTPException(status_code=500, detail="No se pudo obtener token de eBay")

    params = parse_query_with_ia(req.query)
    _log("SEARCH", f"Busqueda procesada para '{req.query}': {_truncate_text(params)}")

    query_params = {
        "q": params.get("q"),
        "category_ids": params.get("categoryId"),
        "filter": "buyingOptions:{FIXED_PRICE}",
        "limit": 50,
    }

    filters = []
    if params.get("maxPrice") and str(params.get("maxPrice")).isdigit():
        filters.append(f"price:[{params.get('minPrice', '0')}..{params['maxPrice']}]")
    if params.get("seller"):
        filters.append(f"sellers:{{ {params['seller']} }}")
    if filters:
        query_params["filter"] += "," + ",".join(filters)

    response = EBAY_SESSION.get(
        "https://api.ebay.com/buy/browse/v1/item_summary/search",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"],
        },
        params=query_params,
        timeout=30,
    )
    if response.status_code != 200:
        _log("SEARCH", f"eBay devolvio {response.status_code}: {_truncate_text(response.text)}")
        raise HTTPException(status_code=response.status_code, detail=f"Error de eBay: {response.text}")

    items = response.json().get("itemSummaries", [])
    _log("SEARCH", f"eBay devolvio {len(items)} item(s). Procesando con {SEARCH_THREAD_WORKERS} worker(s).")

    def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
        price_val = float(item["price"]["value"])
        title = item["title"]
        item_url = item["itemWebUrl"]
        image_url = item.get("image", {}).get("imageUrl")
        all_images = _collect_item_images(item)
        condition = item.get("condition", "Used")
        seller_notes = item.get("conditionDescription", "")

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
            "todas_las_imagenes": all_images,
            "condicion": condition,
            "seller_notes": seller_notes,
            "es_subasta": False,
            "rentabilidad": rentabilidad,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=SEARCH_THREAD_WORKERS) as executor:
        resultados = list(executor.map(process_item, items))

    resultados.sort(
        key=lambda item: (item.get("rentabilidad", {}).get("margen_estimado") or -9999),
        reverse=True,
    )

    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    _log("SEARCH", f"Busqueda completada en {elapsed_ms} ms con {len(resultados)} resultado(s).")
    return {"query_ia": params, "results": resultados}


@app.post("/api/cart/send-telegram")
async def send_cart_to_telegram(req: CartSendRequest):
    """Envia los productos del carrito a Telegram con una etiqueta especial."""
    if not req.items:
        raise HTTPException(status_code=400, detail="Carrito vacio")

    enviados = 0
    encabezado = f"🛒 <b>RECOMENDACION DE MELTYDEAYS | {len(req.items)} PRODUCTOS</b> 🛒"
    _log("SEARCH", f"Enviando {len(req.items)} producto(s) del carrito a Telegram.")

    for token, chat_id in todos_los_destinos(config):
        enviar_telegram_texto(token, chat_id, encabezado)

    for item in req.items:
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

        for token, chat_id in todos_los_destinos(config):
            enviar_telegram_foto(
                token=token,
                chat_id=chat_id,
                oferta=oferta_dict,
                rentabilidad=rentabilidad,
                etiqueta_especial="Recomendacion Manual",
            )
        enviados += 1

    return {"status": "success", "enviados": enviados}


@app.post("/api/analyze-image")
async def analyze_image(req: ImageAnalysisRequest):
    """Analiza imagenes bajo demanda usando Groq Vision."""
    if not analizador_vis:
        raise HTTPException(status_code=500, detail="Analizador visual no configurado (falta GROQ_KEY)")
    if not req.imagenes:
        raise HTTPException(status_code=400, detail="URL de imagen vacia")

    _log("VISION", f"Solicitud de analisis para '{req.titulo}' con {len(req.imagenes)} imagen(es).")
    return analizador_vis.analizar_imagen(req.imagenes, req.titulo, req.seller_notes)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
