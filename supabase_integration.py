"""
Modulo de integracion con Supabase y analisis de rentabilidad Nicaragua.
Usa solo datos reales del usuario para precios de Nicaragua.
"""
import base64
import json
import mimetypes
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
REFERENCIAS_CACHE_TTL_SECONDS = 300
VISION_MAX_PRODUCT_IMAGES = 3
VISION_MAX_TOTAL_IMAGES = 5
VISION_FEW_SHOT_LIMIT = 2


def _log(prefix: str, message: str) -> None:
    print(f"[{prefix}] {message}")


def _truncate_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def _extract_json_object(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("La respuesta no contiene un objeto JSON valido.")
    return json.loads(text[start:end])


class ThreadLocalSessionProvider:
    """Reusa una requests.Session por hilo para mantener conexiones vivas."""

    def __init__(self, default_headers: Optional[Dict[str, str]] = None):
        self.default_headers = default_headers or {}
        self._local = threading.local()

    def get(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            if self.default_headers:
                session.headers.update(self.default_headers)
            self._local.session = session
        return session


class SupabaseClient:
    """Cliente ligero para Supabase REST API."""

    def __init__(
        self,
        url: str,
        service_key: str,
        session_provider: Optional[ThreadLocalSessionProvider] = None,
    ):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.session_provider = session_provider or ThreadLocalSessionProvider()

    def _session(self) -> requests.Session:
        return self.session_provider.get()

    def insert(self, table: str, data: dict) -> Optional[dict]:
        """Inserta un registro."""
        try:
            response = self._session().post(
                f"{self.url}/rest/v1/{table}",
                headers={**self.headers, "Prefer": "return=representation"},
                json=data,
                timeout=15,
            )
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) and result else result
            _log("DB", f"Insert {table} fallo con status {response.status_code}: {_truncate_text(response.text)}")
            return None
        except Exception as error:
            _log("DB", f"Error insertando en {table}: {error}")
            return None

    def upsert(self, table: str, data: dict, conflict_col: str = "ebay_item_id") -> Optional[dict]:
        """Inserta o actualiza (on conflict)."""
        try:
            response = self._session().post(
                f"{self.url}/rest/v1/{table}",
                headers={
                    **self.headers,
                    "Prefer": "return=representation,resolution=merge-duplicates",
                },
                json=data,
                timeout=15,
            )
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) and result else result
            _log(
                "DB",
                f"Upsert {table} fallo con status {response.status_code}: {_truncate_text(response.text)}",
            )
            return None
        except Exception as error:
            _log("DB", f"Error haciendo upsert en {table}: {error}")
            return None

    def select(self, table: str, filters: str = "", limit: int = 100) -> List[dict]:
        """Consulta registros con filtros PostgREST."""
        try:
            separator = "&" if filters else ""
            url = f"{self.url}/rest/v1/{table}?{filters}{separator}limit={limit}"
            response = self._session().get(url, headers=self.headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            _log("DB", f"Select {table} fallo con status {response.status_code}: {_truncate_text(response.text)}")
            return []
        except Exception as error:
            _log("DB", f"Error consultando {table}: {error}")
            return []

    def count(self, table: str) -> int:
        """Cuenta registros en una tabla."""
        try:
            response = self._session().get(
                f"{self.url}/rest/v1/{table}?select=id",
                headers={**self.headers, "Prefer": "count=exact", "Range-Unit": "items"},
                timeout=10,
            )
            count_header = response.headers.get("content-range", "*/0")
            return int(count_header.split("/")[-1])
        except Exception as error:
            _log("DB", f"Error contando registros en {table}: {error}")
            return 0

    def test_connection(self) -> bool:
        """Verifica que la conexion funcione."""
        try:
            response = self._session().get(f"{self.url}/rest/v1/", headers=self.headers, timeout=10)
            return response.status_code == 200
        except Exception as error:
            _log("DB", f"Error probando conexion a Supabase: {error}")
            return False


class AnalizadorRentabilidad:
    """Analiza la rentabilidad de revender productos de eBay en Nicaragua."""

    COSTO_ENVIO_EBAY = 15
    COSTO_COURIER_LB = 8
    PESO_ESTIMADO = {
        "laptop": 5,
        "phone": 0.5,
        "ssd": 0.3,
        "ram": 0.2,
        "accesorio": 1,
    }
    IMPUESTOS_NIC = 0.15

    def __init__(
        self,
        groq_api_key: str,
        supabase: Optional[SupabaseClient] = None,
        session_provider: Optional[ThreadLocalSessionProvider] = None,
        cache_ttl_seconds: int = REFERENCIAS_CACHE_TTL_SECONDS,
        time_fn: Callable[[], float] = time.time,
    ):
        self.groq_key = groq_api_key
        self.supabase = supabase
        self.session_provider = session_provider or ThreadLocalSessionProvider()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.time_fn = time_fn
        self._referencias_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    def _session(self) -> requests.Session:
        return self.session_provider.get()

    def estimar_costo_importacion(self, precio_ebay: float, tipo: str = "laptop") -> float:
        """Estima el costo total de importar el producto a Nicaragua."""
        if tipo.lower() == "laptop":
            return precio_ebay + 60.0

        peso = self.PESO_ESTIMADO.get(tipo, 1)
        envio = self.COSTO_ENVIO_EBAY
        courier = self.COSTO_COURIER_LB * peso
        subtotal = precio_ebay + envio + courier
        impuestos = subtotal * self.IMPUESTOS_NIC
        return round(subtotal + impuestos, 2)

    def buscar_referencias_reales(self, titulo: str, tipo: str = "laptop") -> List[dict]:
        """Busca precios reales del usuario usando cache por tipo."""
        if not self.supabase:
            return []

        cache_key = (tipo or "laptop").strip().lower()
        now = self.time_fn()

        with self._cache_lock:
            cached = self._referencias_cache.get(cache_key)
            if cached and now - cached["timestamp"] < self.cache_ttl_seconds:
                _log("RENT", f"Cache hit de referencias para tipo={cache_key} ({len(cached['value'])} items).")
                return list(cached["value"])

        _log("RENT", f"Cache miss de referencias para tipo={cache_key}.")
        references = self.supabase.select(
            "precios_nicaragua",
            f"tipo=eq.{cache_key}&order=registrado_en.desc",
            limit=30,
        )

        with self._cache_lock:
            self._referencias_cache[cache_key] = {
                "timestamp": now,
                "value": list(references),
            }

        return references

    def analizar(
        self,
        titulo: str,
        precio_ebay: float,
        specs: dict,
        tipo: str = "laptop",
        es_subasta: bool = False,
    ) -> Dict[str, Any]:
        """Analiza la rentabilidad. Honesto sobre lo que sabe y lo que no."""
        if es_subasta:
            return {
                "precio_estimado_nic": None,
                "margen_estimado": None,
                "porcentaje_ganancia": None,
                "costo_importacion": None,
                "demanda": None,
                "tiene_referencias": False,
                "num_referencias": 0,
                "analisis_rentabilidad": "SUBASTA: el precio actual es solo la puja, no el precio final.",
            }

        costo_total = self.estimar_costo_importacion(precio_ebay, tipo)
        referencias = self.buscar_referencias_reales(titulo, tipo)

        if not referencias:
            return {
                "precio_estimado_nic": None,
                "margen_estimado": None,
                "porcentaje_ganancia": None,
                "costo_importacion": costo_total,
                "demanda": None,
                "tiene_referencias": False,
                "num_referencias": 0,
                "analisis_rentabilidad": (
                    f"Costo puesto en Nicaragua: ~${costo_total:.2f}. "
                    "Sin datos de precio en Nicaragua aun; agrega precios reales para ver rentabilidad."
                ),
            }

        return self._analizar_con_referencias(titulo, precio_ebay, costo_total, specs, tipo, referencias)

    def _analizar_con_referencias(
        self,
        titulo: str,
        precio_ebay: float,
        costo_total: float,
        specs: dict,
        tipo: str,
        referencias: List[dict],
    ) -> Dict[str, Any]:
        """Analiza con IA usando precios reales de Nicaragua como base."""
        if not self.groq_key:
            return self._analisis_por_referencias(costo_total, referencias)

        refs_text = "\n".join(
            f"  - {item.get('titulo_marketplace', item.get('modelo', '?'))}: "
            f"${item.get('precio_nic_usd', 0)} ({item.get('condicion', '?')}) - {item.get('ciudad', '?')}"
            for item in referencias[:15]
        )

        prompt = f"""Eres un experto en reventa de electronica en Nicaragua.
Tienes datos reales de precios del Facebook Marketplace de Nicaragua.

PRODUCTO DE EBAY:
  Titulo: {titulo}
  Precio eBay (compra): ${precio_ebay:.2f}
  Costo puesto en Nicaragua: ~${costo_total:.2f}
  Specs: {json.dumps(specs, ensure_ascii=False)}

PRECIOS REALES EN NICARAGUA (datos del usuario):
{refs_text}

Basandote solo en los precios reales de arriba, estima:
1. A cuanto se podria vender este producto en Nicaragua.
2. Cual seria el margen de ganancia.
3. Que tan rapido se venderia.

Responde solo con JSON:
{{
  "precio_venta_nic": 999,
  "margen_usd": 999,
  "porcentaje_ganancia": 99,
  "demanda": "alta|media|baja",
  "confianza": "alta|media|baja",
  "resumen": "Explicacion breve basada en los precios reales"
}}"""

        started_at = time.perf_counter()
        try:
            response = self._session().post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self.groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 250,
                    "temperature": 0.2,
                },
                timeout=15,
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)

            if response.status_code != 200:
                _log(
                    "RENT",
                    f"Groq devolvio {response.status_code} en {elapsed_ms} ms: {_truncate_text(response.text)}",
                )
                return self._analisis_por_referencias(costo_total, referencias)

            content = response.json()["choices"][0]["message"]["content"]
            data = _extract_json_object(content)
            _log("RENT", f"Analisis IA completado en {elapsed_ms} ms para {len(referencias)} referencias.")
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
        except Exception as error:
            _log("RENT", f"Error consultando Groq para rentabilidad: {error}")

        return self._analisis_por_referencias(costo_total, referencias)

    def _analisis_por_referencias(self, costo_total: float, referencias: List[dict]) -> Dict[str, Any]:
        """Fallback: calcula usando el promedio de las referencias reales."""
        precios = [float(item.get("precio_nic_usd", 0)) for item in referencias if item.get("precio_nic_usd")]
        if not precios:
            return {
                "precio_estimado_nic": None,
                "margen_estimado": None,
                "porcentaje_ganancia": None,
                "costo_importacion": costo_total,
                "tiene_referencias": False,
                "num_referencias": 0,
                "analisis_rentabilidad": f"Costo importacion: ~${costo_total:.2f}. Sin referencias.",
            }

        promedio = sum(precios) / len(precios)
        margen = round(promedio - costo_total, 2)
        porcentaje = round((margen / costo_total) * 100, 1) if costo_total > 0 else 0
        return {
            "precio_estimado_nic": round(promedio, 2),
            "margen_estimado": margen,
            "porcentaje_ganancia": porcentaje,
            "costo_importacion": costo_total,
            "tiene_referencias": True,
            "num_referencias": len(precios),
            "analisis_rentabilidad": (
                f"Basado en {len(precios)} precios reales (prom: ${promedio:.0f}). "
                f"Margen: ${margen:.0f} ({porcentaje:.0f}%)."
            ),
        }


class AnalizadorVisual:
    """Analiza imagenes de productos con Groq Vision."""

    def __init__(
        self,
        groq_api_key: str,
        session_provider: Optional[ThreadLocalSessionProvider] = None,
        few_shot_examples: Optional[List[Dict[str, str]]] = None,
    ):
        self.groq_key = groq_api_key
        self.session_provider = session_provider or ThreadLocalSessionProvider()
        self._few_shot_examples = few_shot_examples

    def _session(self) -> requests.Session:
        return self.session_provider.get()

    def _success_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        defectos = data.get("defectos", [])
        if not isinstance(defectos, list):
            defectos = [str(defectos)]

        return {
            "status": "success",
            "error_code": None,
            "provider_status": 200,
            "es_producto_real": bool(data.get("es_producto_real", True)),
            "calidad_visual": data.get("calidad_visual", "aceptable"),
            "defectos": defectos,
            "score": int(data.get("score", 50)),
            "nota": data.get("nota", "Analisis visual completado."),
        }

    def _error_result(
        self,
        *,
        status: str,
        error_code: str,
        provider_status: Optional[int] = None,
        calidad_visual: str = "error_api",
        nota: str,
        score: int = 50,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "error_code": error_code,
            "provider_status": provider_status,
            "es_producto_real": None,
            "calidad_visual": calidad_visual,
            "defectos": [],
            "score": score,
            "nota": nota,
        }

    def _load_few_shot_examples(self) -> List[Dict[str, str]]:
        if self._few_shot_examples is not None:
            return self._few_shot_examples[:VISION_FEW_SHOT_LIMIT]

        examples: List[Dict[str, str]] = []
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            (
                os.path.join(base_dir, "examples", "bad_example.png"),
                "Ejemplo de dano grave (pantalla rota o dano estructural inaceptable):",
                "Entendido. Este ejemplo debe penalizarse fuerte con score bajo por dano estructural visible.",
            ),
            (
                os.path.join(base_dir, "examples", "good_example.png"),
                "Ejemplo de estado aceptable (equipo limpio y revendible):",
                "Entendido. Este ejemplo es cosmeticamente saludable y merece un score alto.",
            ),
        ]

        for path, prompt, answer in candidates:
            if not os.path.exists(path):
                continue
            mime_type = mimetypes.guess_type(path)[0] or "image/png"
            with open(path, "rb") as file_handle:
                encoded = base64.b64encode(file_handle.read()).decode("utf-8")
            examples.append(
                {
                    "prompt": prompt,
                    "assistant": answer,
                    "url": f"data:{mime_type};base64,{encoded}",
                }
            )

        self._few_shot_examples = examples[:VISION_FEW_SHOT_LIMIT]
        return self._few_shot_examples

    def prepare_product_image_urls(self, imagenes_urls: Any) -> List[str]:
        if isinstance(imagenes_urls, str):
            imagenes_urls = [imagenes_urls]

        cleaned_urls: List[str] = []
        seen = set()
        for raw_url in imagenes_urls or []:
            url = str(raw_url or "").strip()
            if not url or url in seen:
                continue
            if not url.startswith(("http://", "https://")):
                continue
            seen.add(url)
            cleaned_urls.append(url)
            if len(cleaned_urls) >= VISION_MAX_PRODUCT_IMAGES:
                break
        return cleaned_urls

    def _analysis_prompt(self, titulo: str, seller_notes: str) -> str:
        seller_notes_text = seller_notes or "Ninguna proporcionada"
        return f"""Analiza estas imagenes de un listing de eBay: "{titulo}"

Notas del vendedor: "{seller_notes_text}"

Evalua la condicion fisica visible y lo descrito en las notas.
Si las notas mencionan cracked corner, missing piece, dents, scratches, hinge damage o plastic damage, penaliza el score aunque las fotos no lo muestren del todo claro.

Prioridades:
1. Dano critico visible o reportado -> score 10-30.
2. Desgaste cosmetico menor -> score alto si sigue siendo revendible.
3. Confirma si parece el producto real y no una foto generica.

Responde solo con JSON:
{{
  "es_producto_real": true,
  "calidad_visual": "excelente|buena|aceptable|mala|terrible",
  "defectos": ["lista", "de", "defectos"],
  "score": 85,
  "nota": "Observacion breve"
}}"""

    def build_request_payload(
        self,
        imagenes_urls: Any,
        titulo: str,
        seller_notes: str = "",
    ) -> tuple[Dict[str, Any], Dict[str, int]]:
        product_urls = self.prepare_product_image_urls(imagenes_urls)
        few_shot_examples = self._load_few_shot_examples()
        available_product_slots = max(0, VISION_MAX_TOTAL_IMAGES - len(few_shot_examples))
        product_urls = product_urls[:available_product_slots]

        messages: List[Dict[str, Any]] = []
        for example in few_shot_examples:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": example["prompt"]},
                        {"type": "image_url", "image_url": {"url": example["url"]}},
                    ],
                }
            )
            messages.append({"role": "assistant", "content": example["assistant"]})

        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": self._analysis_prompt(titulo, seller_notes)}
        ]
        for url in product_urls:
            user_content.append({"type": "image_url", "image_url": {"url": url}})

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 200,
            "temperature": 0.1,
        }
        metadata = {
            "few_shot_example_count": len(few_shot_examples),
            "product_image_count": len(product_urls),
            "total_image_count": len(few_shot_examples) + len(product_urls),
        }
        return payload, metadata

    def analizar_imagen(self, imagenes_urls: Any, titulo: str, seller_notes: str = "") -> Dict[str, Any]:
        """Analiza multiples imagenes con Groq Vision respetando los limites del proveedor."""
        if not self.groq_key:
            return self._error_result(
                status="unavailable",
                error_code="missing_api_key",
                calidad_visual="desconocida",
                nota="El analisis visual no esta configurado en el backend.",
            )

        payload, metadata = self.build_request_payload(imagenes_urls, titulo, seller_notes)
        if metadata["product_image_count"] == 0:
            return self._error_result(
                status="no_images",
                error_code="no_images",
                provider_status=None,
                calidad_visual="no_disponible",
                nota="No hay imagenes validas para analizar en este producto.",
            )

        _log(
            "VISION",
            (
                f"Analizando {metadata['product_image_count']} imagen(es) del producto "
                f"con {metadata['few_shot_example_count']} ejemplo(s) few-shot."
            ),
        )

        started_at = time.perf_counter()
        try:
            response = self._session().post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self.groq_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)

            if response.status_code != 200:
                _log(
                    "VISION",
                    (
                        f"Groq devolvio {response.status_code} en {elapsed_ms} ms. "
                        f"Payload con {metadata['total_image_count']} imagen(es). "
                        f"Respuesta: {_truncate_text(response.text)}"
                    ),
                )
                return self._error_result(
                    status="error",
                    error_code="provider_http_error",
                    provider_status=response.status_code,
                    nota="Groq Vision rechazo el analisis en este momento. Puedes reintentar.",
                )

            body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = _extract_json_object(content)
            _log("VISION", f"Analisis completado en {elapsed_ms} ms con score {data.get('score', 50)}.")
            return self._success_result(data)
        except requests.RequestException as error:
            _log("VISION", f"Error de red al analizar imagenes: {error}")
            return self._error_result(
                status="error",
                error_code="provider_request_error",
                provider_status=None,
                nota="No se pudo conectar con Groq Vision. Intenta de nuevo en un momento.",
            )
        except Exception as error:
            _log("VISION", f"Error procesando la respuesta visual: {error}")
            return self._error_result(
                status="error",
                error_code="invalid_provider_payload",
                provider_status=200,
                nota="Groq Vision respondio, pero el formato no fue valido. Puedes reintentar.",
            )


def guardar_producto_supabase(
    supabase: SupabaseClient,
    oferta,
    rentabilidad: Dict[str, Any] = None,
    visual: Dict[str, Any] = None,
    marca: str = "",
) -> bool:
    """Guarda un producto en Supabase con todos sus analisis."""
    data = {
        "ebay_item_id": getattr(oferta, "enlace", "").split("/")[-1] or None,
        "titulo": oferta.titulo,
        "precio": float(oferta.precio),
        "precio_texto": oferta.precio_texto,
        "condicion": oferta.estado,
        "categoria": "laptop",
        "procesador": getattr(oferta, "procesador", ""),
        "marca": marca,
        "vendedor": oferta.vendedor,
        "enlace": oferta.enlace,
        "imagen_url": getattr(oferta, "imagen", ""),
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
