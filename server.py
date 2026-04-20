import os
import sys
import json
import asyncio
import requests
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import concurrent.futures

# Importar módulos de nuestro backend refactorizado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import obtener_configuracion, todos_los_destinos
from ebay_client import obtener_token_ebay_app
from supabase_integration import AnalizadorRentabilidad, AnalizadorVisual, SupabaseClient
from telegram_utils import enviar_telegram_foto, enviar_telegram_texto

load_dotenv()
config = obtener_configuracion()

app = FastAPI(title="eBay AI Finder API")

# Habilitar CORS para que la Web App pueda comunicarse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str

class CartSendRequest(BaseModel):
    items: List[Dict[str, Any]]

class ImageAnalysisRequest(BaseModel):
    imagenes: List[str]
    titulo: str
    seller_notes: str = ""

# Inicializar analyzers
groq_key = config.get("groq_api_key")
sb_url = config.get("supabase_url")
sb_key = config.get("supabase_service_key")

sb_client = SupabaseClient(sb_url, sb_key) if sb_url and sb_key else None
analizador_rent = AnalizadorRentabilidad(groq_key, sb_client) if groq_key else None
analizador_vis = AnalizadorVisual(groq_key) if groq_key else None

def parse_query_with_ia(query: str) -> Dict[str, Any]:
    """Usa IA para convertir lenguaje natural a parámetros de búsqueda de eBay."""
    prompt = f"""Convierte esta búsqueda del usuario en parámetros para la API de eBay: "{query}"
    
Reglas de categoría: 
- Laptops: 175672
- Celulares: 9355
- SSDs: 175669
- RAM: 170083

Responde en JSON exacto sin markdown:
{{
  "q": "palabras clave para buscar en eBay en inglés",
  "categoryId": "175672",
  "maxPrice": "precio maximo si menciona, o vacio",
  "minPrice": "precio minimo si menciona, o vacio",
  "seller": "nombre de usuario del vendedor si lo menciona, o vacio"
}}"""

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150, "temperature": 0.1
            },
            timeout=10
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
    except Exception as e:
        print(f"Error IA Parse: {e}")
        
    # Fallback básico
    return {"q": query, "categoryId": "175672", "maxPrice": "250", "minPrice": "10"}

@app.post("/api/search")
async def search_ebay(req: SearchRequest):
    """Búsqueda en tiempo real usando eBay Browse API y Rentabilidad IA."""
    token = obtener_token_ebay_app(config)
    if not token:
        raise HTTPException(status_code=500, detail="No se pudo obtener token de eBay")

    # 1. Parsear intención con IA
    params = parse_query_with_ia(req.query)
    print(f"🔎 Búsqueda procesada: {params}")

    # 2. Construir llamada a eBay
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    query_params = {
        "q": params.get("q"),
        "category_ids": params.get("categoryId"),
        "filter": "buyingOptions:{FIXED_PRICE}", # Solo precio fijo para calcular rentabilidad real
        "limit": 50
    }
    
    filters = []
    if params.get("maxPrice") and str(params.get("maxPrice")).isdigit():
        filters.append(f"price:[{params.get('minPrice', '0')}..{params['maxPrice']}]")
    if params.get("seller"):
        filters.append(f"sellers:{{ {params['seller']} }}")
        
    if filters:
        query_params["filter"] += "," + ",".join(filters)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": config["ebay_marketplace_id"]
    }

    resp = requests.get(url, headers=headers, params=query_params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Error de eBay: {resp.text}")

    data = resp.json()
    items = data.get("itemSummaries", [])
    
    resultados = []
    
    # 3. Analizar resultados en paralelo
    def process_item(item):
        price_val = float(item["price"]["value"])
        title = item["title"]
        item_url = item["itemWebUrl"]
        image_url = item.get("image", {}).get("imageUrl")
        
        # Extraer TODAS las imágenes disponibles
        todas_las_imagenes = []
        if image_url: todas_las_imagenes.append(image_url)
        for add_img in item.get("additionalImages", []):
            if add_img.get("imageUrl"):
                todas_las_imagenes.append(add_img.get("imageUrl"))
                
        condicion = item.get("condition", "Used")
        seller_notes = item.get("conditionDescription", "")
        
        # Determinar tipo para importación
        cat_id = item.get("categories", [{}])[0].get("categoryId")
        tipo = "laptop"
        if cat_id == "9355": tipo = "phone"
        elif cat_id == "175669": tipo = "ssd"
        elif cat_id == "170083": tipo = "ram"

        rentabilidad = None
        if analizador_rent:
            rentabilidad = analizador_rent.analizar(title, price_val, {}, tipo, False)

        return {
            "id": item["itemId"],
            "titulo": title,
            "precio": price_val,
            "precio_texto": f"${price_val}",
            "enlace": item_url,
            "imagen_url": image_url,
            "todas_las_imagenes": todas_las_imagenes[:6], # Limitar a 6 fotos para no saturar la IA
            "condicion": condicion,
            "seller_notes": seller_notes,
            "es_subasta": False,
            "rentabilidad": rentabilidad
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(process_item, items))

    # Ordenar por mejor margen si hay rentabilidad
    resultados.sort(key=lambda x: (x.get("rentabilidad", {}).get("margen_estimado") or -9999), reverse=True)

    return {"query_ia": params, "results": resultados}

@app.post("/api/cart/send-telegram")
async def send_cart_to_telegram(req: CartSendRequest):
    """Envía los productos del carrito a Telegram con una etiqueta especial."""
    if not req.items:
        raise HTTPException(status_code=400, detail="Carrito vacío")
        
    enviados = 0
    encabezado = f"🛒 <b>RECOMENDACIÓN DE MELTYDEAYS | {len(req.items)} PRODUCTOS</b> 🛒"
    
    # Enviar encabezado a todos los destinos
    for tok, cid in todos_los_destinos(config):
        enviar_telegram_texto(tok, cid, encabezado)
    
    # Enviar cada producto
    for item in req.items:
        # Convertir a formato compatible con telegram_utils
        oferta_dict = {
            "titulo": item.get("titulo"),
            "condicion": item.get("condicion"),
            "precio_texto": item.get("precio_texto") or f"${item.get('precio')}",
            "vendedor": item.get("vendedor", "Recomendado"),
            "enlace": item.get("enlace"),
            "imagen_url": item.get("imagen_url"),
            "es_subasta": item.get("es_subasta", False),
            "procesador": item.get("procesador", "")
        }
        
        rentabilidad = item.get("rentabilidad")
        if not rentabilidad and item.get("precio_estimado_nic"):
            # Si viene directo de la DB (Supabase) pero sin el objeto rentabilidad, lo reconstruimos
            rentabilidad = {
                "tiene_referencias": True,
                "margen_estimado": item.get("margen_estimado", 0),
                "porcentaje_ganancia": item.get("porcentaje_ganancia", 0),
                "precio_estimado_nic": item.get("precio_estimado_nic", 0)
            }

        for tok, cid in todos_los_destinos(config):
            enviar_telegram_foto(
                token=tok, 
                chat_id=cid, 
                oferta=oferta_dict, 
                rentabilidad=rentabilidad,
                etiqueta_especial="Recomendación Manual"
            )
        enviados += 1
        
    return {"status": "success", "enviados": enviados}

@app.post("/api/analyze-image")
async def analyze_image(req: ImageAnalysisRequest):
    """Analiza TODAS las imágenes bajo demanda usando Few-Shot Vision."""
    if not analizador_vis:
        raise HTTPException(status_code=500, detail="Analizador Visual no configurado (falta GROQ_KEY)")
    
    if not req.imagenes or len(req.imagenes) == 0:
        raise HTTPException(status_code=400, detail="URL de imagen vacía")
        
    resultado = analizador_vis.analizar_imagen(req.imagenes, req.titulo, req.seller_notes)
    return resultado

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
