"""
Módulo de integración con Supabase y análisis de rentabilidad Nicaragua.
Usa SOLO datos reales del usuario para precios de Nicaragua.
"""
import os
import sys
import json
import requests
import base64
from typing import Optional, Dict, List, Any

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class SupabaseClient:
    """Cliente ligero para Supabase REST API (sin dependencias extra)."""

    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def insert(self, table: str, data: dict) -> Optional[dict]:
        """Inserta un registro."""
        try:
            r = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers={**self.headers, "Prefer": "return=representation"},
                json=data, timeout=15
            )
            if r.status_code in (200, 201):
                result = r.json()
                return result[0] if isinstance(result, list) and result else result
            return None
        except Exception as e:
            print(f"  [DB] Error insert {table}: {e}")
            return None

    def upsert(self, table: str, data: dict, conflict_col: str = "ebay_item_id") -> Optional[dict]:
        """Inserta o actualiza (on conflict)."""
        try:
            r = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers={
                    **self.headers,
                    "Prefer": "return=representation,resolution=merge-duplicates",
                },
                json=data, timeout=15
            )
            if r.status_code in (200, 201):
                result = r.json()
                return result[0] if isinstance(result, list) and result else result
            else:
                print(f"  [DB] Upsert {table} status {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"  [DB] Error upsert {table}: {e}")
            return None

    def select(self, table: str, filters: str = "", limit: int = 100) -> List[dict]:
        """Consulta registros con filtros PostgREST."""
        try:
            sep = "&" if filters else ""
            url = f"{self.url}/rest/v1/{table}?{filters}{sep}limit={limit}"
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code == 200:
                return r.json()
            return []
        except:
            return []

    def count(self, table: str) -> int:
        """Cuenta registros en una tabla."""
        try:
            r = requests.get(
                f"{self.url}/rest/v1/{table}?select=id",
                headers={**self.headers, "Prefer": "count=exact", "Range-Unit": "items"},
                timeout=10
            )
            count_header = r.headers.get("content-range", "*/0")
            return int(count_header.split("/")[-1])
        except:
            return 0

    def test_connection(self) -> bool:
        """Verifica que la conexión funcione."""
        try:
            r = requests.get(f"{self.url}/rest/v1/", headers=self.headers, timeout=10)
            return r.status_code == 200
        except:
            return False


class AnalizadorRentabilidad:
    """Analiza la rentabilidad de revender productos de eBay en Nicaragua.
    
    USA DATOS REALES: Los precios de referencia vienen de la tabla precios_nicaragua,
    alimentada manualmente por el usuario con precios reales de FB Marketplace Nicaragua.
    Si no hay datos de referencia, lo dice honestamente.
    """

    # Costos estimados de importación (estos SÍ son estimables)
    COSTO_ENVIO_EBAY = 15      # Envío promedio eBay → Miami
    COSTO_COURIER_LB = 8       # Courier Miami → Nicaragua por libra
    PESO_ESTIMADO = {
        "laptop": 5,
        "phone": 0.5,
        "ssd": 0.3,
        "ram": 0.2,
        "accesorio": 1,
    }
    IMPUESTOS_NIC = 0.15

    def __init__(self, groq_api_key: str, supabase: Optional[SupabaseClient] = None):
        self.groq_key = groq_api_key
        self.supabase = supabase

    def estimar_costo_importacion(self, precio_ebay: float, tipo: str = "laptop") -> float:
        """Estima el costo total de importar el producto a Nicaragua."""
        if tipo.lower() == "laptop":
            # El usuario indicó que el costo fijo de envío/importación es $60 para laptops
            return precio_ebay + 60.0
            
        peso = self.PESO_ESTIMADO.get(tipo, 1)
        envio = self.COSTO_ENVIO_EBAY
        courier = self.COSTO_COURIER_LB * peso
        subtotal = precio_ebay + envio + courier
        impuestos = subtotal * self.IMPUESTOS_NIC
        return round(subtotal + impuestos, 2)

    def buscar_referencias_reales(self, titulo: str, tipo: str = "laptop") -> List[dict]:
        """Busca precios REALES que el usuario ha registrado en la BD."""
        if not self.supabase:
            return []
        return self.supabase.select(
            "precios_nicaragua",
            f"tipo=eq.{tipo}&order=registrado_en.desc",
            limit=30
        )

    def analizar(self, titulo: str, precio_ebay: float, specs: dict,
                 tipo: str = "laptop", es_subasta: bool = False) -> Dict:
        """Analiza la rentabilidad. Honesto sobre lo que sabe y lo que no."""

        # Si es subasta, NO calcular rentabilidad (precio no es final)
        if es_subasta:
            return {
                "precio_estimado_nic": None,
                "margen_estimado": None,
                "porcentaje_ganancia": None,
                "costo_importacion": None,
                "demanda": None,
                "tiene_referencias": False,
                "num_referencias": 0,
                "analisis_rentabilidad": "⚠️ SUBASTA: El precio actual es solo la puja, no el precio final. No se puede calcular rentabilidad hasta que termine."
            }

        costo_total = self.estimar_costo_importacion(precio_ebay, tipo)
        referencias = self.buscar_referencias_reales(titulo, tipo)

        # Si NO hay referencias reales, ser honesto
        if not referencias:
            return {
                "precio_estimado_nic": None,
                "margen_estimado": None,
                "porcentaje_ganancia": None,
                "costo_importacion": costo_total,
                "demanda": None,
                "tiene_referencias": False,
                "num_referencias": 0,
                "analisis_rentabilidad": f"📦 Costo puesto en Nicaragua: ~${costo_total:.2f}. Sin datos de precio en Nicaragua aún — agrega precios de FB Marketplace para ver rentabilidad."
            }

        # SÍ hay referencias — usar IA para comparar inteligentemente
        return self._analizar_con_referencias(titulo, precio_ebay, costo_total, specs, tipo, referencias)

    def _analizar_con_referencias(self, titulo: str, precio_ebay: float,
                                   costo_total: float, specs: dict,
                                   tipo: str, referencias: List[dict]) -> Dict:
        """Analiza con IA usando precios REALES de Nicaragua como base."""
        if not self.groq_key:
            return self._analisis_por_referencias(costo_total, referencias)

        refs_text = "\n".join(
            f"  - {r.get('titulo_marketplace', r.get('modelo','?'))}: "
            f"${r.get('precio_nic_usd', 0)} ({r.get('condicion', '?')}) — {r.get('ciudad', '?')}"
            for r in referencias[:15]
        )

        prompt = f"""Eres un experto en reventa de electrónica en Nicaragua. 
Tienes datos REALES de precios del Facebook Marketplace de Nicaragua.

PRODUCTO DE EBAY:
  Título: {titulo}
  Precio eBay (compra): ${precio_ebay:.2f}
  Costo puesto en Nicaragua: ~${costo_total:.2f}
  Specs: {json.dumps(specs, ensure_ascii=False)}

PRECIOS REALES EN NICARAGUA (datos del usuario, FB Marketplace):
{refs_text}

Basándote SOLO en los precios reales de arriba, estima:
1. ¿A cuánto se podría vender este producto en Nicaragua?
2. ¿Cuál sería el margen de ganancia?
3. ¿Qué tan rápido se vendería?

Responde en JSON exacto (sin markdown):
{{
  "precio_venta_nic": 999,
  "margen_usd": 999,
  "porcentaje_ganancia": 99,
  "demanda": "alta|media|baja",
  "confianza": "alta|media|baja",
  "resumen": "Explicación breve basada en los precios reales"
}}"""

        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 250, "temperature": 0.2
                },
                timeout=15
            )
            if resp.status_code != 200:
                return self._analisis_por_referencias(costo_total, referencias)

            text = resp.json()["choices"][0]["message"]["content"].strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return {
                    "precio_estimado_nic": float(data.get("precio_venta_nic", 0)),
                    "margen_estimado": float(data.get("margen_usd", 0)),
                    "porcentaje_ganancia": float(data.get("porcentaje_ganancia", 0)),
                    "costo_importacion": costo_total,
                    "demanda": data.get("demanda", "media"),
                    "confianza": data.get("confianza", "media"),
                    "tiene_referencias": True,
                    "num_referencias": len(referencias),
                    "analisis_rentabilidad": data.get("resumen", ""),
                }
        except Exception as e:
            print(f"  [💰] Error análisis IA: {e}")

        return self._analisis_por_referencias(costo_total, referencias)

    def _analisis_por_referencias(self, costo_total: float, referencias: List[dict]) -> Dict:
        """Fallback: calcula usando el promedio de las referencias reales."""
        precios = [float(r.get("precio_nic_usd", 0)) for r in referencias if r.get("precio_nic_usd")]
        if not precios:
            return {
                "precio_estimado_nic": None, "margen_estimado": None,
                "porcentaje_ganancia": None, "costo_importacion": costo_total,
                "tiene_referencias": False, "num_referencias": 0,
                "analisis_rentabilidad": f"Costo importación: ~${costo_total:.2f}. Sin referencias."
            }
        promedio = sum(precios) / len(precios)
        margen = round(promedio - costo_total, 2)
        pct = round((margen / costo_total) * 100, 1) if costo_total > 0 else 0
        return {
            "precio_estimado_nic": round(promedio, 2),
            "margen_estimado": margen,
            "porcentaje_ganancia": pct,
            "costo_importacion": costo_total,
            "tiene_referencias": True,
            "num_referencias": len(precios),
            "analisis_rentabilidad": f"Basado en {len(precios)} precios reales (prom: ${promedio:.0f}). Margen: ${margen:.0f} ({pct:.0f}%)",
        }


class AnalizadorVisual:
    """Analiza imágenes de productos con Llama 4 Scout (Vision)."""

    def __init__(self, groq_api_key: str):
        self.groq_key = groq_api_key

    def analizar_imagen(self, imagenes_urls: Any, titulo: str, seller_notes: str = "") -> Dict:
        """Descarga múltiples imágenes y las analiza con Llama 4 Scout Vision."""
        if not self.groq_key or not imagenes_urls:
            return {"calidad_visual": "desconocida", "defectos": [], "score": 50}

        if isinstance(imagenes_urls, str):
            imagenes_urls = [imagenes_urls]

        try:
            # Descargar todas las imágenes
            imagenes_b64 = []
            for url in imagenes_urls[:6]: # Máximo 6 para no saturar
                img_resp = requests.get(url, timeout=10)
                if img_resp.status_code == 200:
                    b64 = base64.b64encode(img_resp.content).decode("utf-8")
                    ctype = img_resp.headers.get("content-type", "image/jpeg")
                    imagenes_b64.append({"b64": b64, "type": ctype})
            
            if not imagenes_b64:
                return {"calidad_visual": "no_disponible", "defectos": [], "score": 50}

            prompt = f"""Analiza TODAS estas imágenes de un listing de eBay: "{titulo}"

Notas del vendedor (Seller Notes): "{seller_notes if seller_notes else 'Ninguna proporcionada'}"

Evalúa la condición FÍSICA visible en las imágenes y lo descrito en las "Notas del vendedor" comparándola con los ejemplos dados.
Si las notas del vendedor dicen algo como "cracked corner", "missing piece", "dents", o "scratches", penaliza el score de inmediato aunque las fotos no lo muestren claro:
1. ¿Hay daños críticos? (pantalla rota, bisagras rotas, plásticos faltantes o mencionados en las notas) -> RECHAZAR (score 10-30).
2. ¿Son solo detalles cosméticos menores? -> ACEPTAR (score bueno).
3. ¿Es el producto real descrito o genérico?

Responde en JSON exacto (sin markdown):
{{
  "es_producto_real": true,
  "calidad_visual": "excelente|buena|aceptable|mala|terrible",
  "defectos": ["lista", "de", "defectos"],
  "score": 85,
  "nota": "Observación breve"
}}"""

            messages = []
            # Intentar cargar ejemplos Few-Shot
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                bad_path = os.path.join(base_dir, "examples", "bad_example.png")
                bad_scuffs_path = os.path.join(base_dir, "examples", "bad_example_scuffs.png")
                bad_hinge_path = os.path.join(base_dir, "examples", "bad_example_hinge1.png")
                bad_scratch_path = os.path.join(base_dir, "examples", "bad_example_scratches.jpg")
                good_path = os.path.join(base_dir, "examples", "good_example.png")
                
                if os.path.exists(bad_path) and os.path.exists(good_path):
                    with open(bad_path, "rb") as fb: bad_b64 = base64.b64encode(fb.read()).decode("utf-8")
                    with open(good_path, "rb") as fg: good_b64 = base64.b64encode(fg.read()).decode("utf-8")
                    
                    messages.extend([
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Ejemplo de daño GRAVE 1 (pantalla rota, inaceptable):"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{bad_b64}"}}
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": "Entendido. Esta imagen muestra daño estructural severo en la pantalla. Es inaceptable y tendría un score de 10."
                        }
                    ])
                    
                    if os.path.exists(bad_scuffs_path):
                        with open(bad_scuffs_path, "rb") as fs: scuffs_b64 = base64.b64encode(fs.read()).decode("utf-8")
                        messages.extend([
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Ejemplo de daño GRAVE 2 (rayones profundos/desgaste excesivo, inaceptable para reventa):"},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{scuffs_b64}"}}
                                ]
                            },
                            {
                                "role": "assistant",
                                "content": "Entendido. Esta imagen muestra desgaste cosmético inaceptable y raspones profundos (invendible). Score de 20."
                            }
                        ])

                    if os.path.exists(bad_hinge_path):
                        with open(bad_hinge_path, "rb") as fh: hinge_b64 = base64.b64encode(fh.read()).decode("utf-8")
                        messages.extend([
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Ejemplo de daño GRAVE 3 (bisagras rotas, plásticos partidos en las esquinas, inaceptable):"},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{hinge_b64}"}}
                                ]
                            },
                            {
                                "role": "assistant",
                                "content": "Entendido. Esta imagen muestra la carcasa o la bisagra (hinge) rota en la esquina. Es un daño estructural gravísimo que no se puede arreglar fácilmente. Score de 15."
                            }
                        ])

                    if os.path.exists(bad_scratch_path):
                        with open(bad_scratch_path, "rb") as fsc: scratch_b64 = base64.b64encode(fsc.read()).decode("utf-8")
                        messages.extend([
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Ejemplo de daño GRAVE 4 (rayones extremadamente notables y profundos en la tapa exterior):"},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{scratch_b64}"}}
                                ]
                            },
                            {
                                "role": "assistant",
                                "content": "Entendido. Esta imagen muestra demasiados rayones largos y evidentes en la tapa superior. Esto arruina la estética para reventa. Score de 25."
                            }
                        ])

                    messages.extend([
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Ejemplo de estado ACEPTABLE (muy limpio, desgaste casi nulo):"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{good_b64}"}}
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": "Entendido. Esta imagen muestra un equipo en excelente estado cosmético. Aceptable, score de 95."
                        }
                    ])
            except Exception as e:
                print(f"Error cargando ejemplos visuales: {e}")

            # Agregar las imágenes reales a analizar
            user_content = [{"type": "text", "text": prompt}]
            for img_data in imagenes_b64:
                user_content.append({"type": "image_url", "image_url": {"url": f"data:{img_data['type']};base64,{img_data['b64']}"}})
            
            messages.append({
                "role": "user",
                "content": user_content
            })

            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": messages,
                    "max_tokens": 200, "temperature": 0.1
                },
                timeout=30
            )

            if resp.status_code != 200:
                return {"calidad_visual": "error_api", "defectos": [], "score": 50}

            text = resp.json()["choices"][0]["message"]["content"].strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])

        except Exception as e:
            print(f"  [👁️] Error análisis visual: {e}")

        return {"calidad_visual": "error", "defectos": [], "score": 50}


def guardar_producto_supabase(supabase: SupabaseClient, oferta, rentabilidad: Dict = None,
                               visual: Dict = None, marca: str = "") -> bool:
    """Guarda un producto en Supabase con todos sus análisis."""
    data = {
        "ebay_item_id": getattr(oferta, 'enlace', '').split('/')[-1] or None,
        "titulo": oferta.titulo,
        "precio": float(oferta.precio),
        "precio_texto": oferta.precio_texto,
        "condicion": oferta.estado,
        "categoria": "laptop",
        "procesador": getattr(oferta, 'procesador', ''),
        "marca": marca,
        "vendedor": oferta.vendedor,
        "enlace": oferta.enlace,
        "imagen_url": getattr(oferta, 'imagen', ''),
        "es_subasta": oferta.es_subasta,
        "tiempo_restante": oferta.tiempo_restante or None,
        "enviado_telegram": True,
    }

    if rentabilidad:
        data["precio_estimado_nic"] = rentabilidad.get("precio_estimado_nic")
        data["margen_estimado"] = rentabilidad.get("margen_estimado")
        data["porcentaje_ganancia"] = rentabilidad.get("porcentaje_ganancia")
        data["analisis_rentabilidad"] = rentabilidad.get("analisis_rentabilidad")

    if visual:
        data["ia_calidad_visual"] = visual.get("calidad_visual", "")
        data["ia_defectos_fisicos"] = json.dumps(visual.get("defectos", []), ensure_ascii=False)
        data["ia_score"] = visual.get("score", 50)

    result = supabase.upsert("productos", data)
    return result is not None
