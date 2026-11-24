"""
Modulo de integracion con Supabase y analisis de rentabilidad Nicaragua.
Usa solo datos reales del usuario para precios de Nicaragua.
"""
import base64
import json
import mimetypes
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests

import math
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODELS = [
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview"
]
REFERENCIAS_CACHE_TTL_SECONDS = 300
VISION_MAX_PRODUCT_IMAGES = 9
VISION_MAX_TOTAL_IMAGES = 4
VISION_FEW_SHOT_LIMIT = 3
VISION_PHYSICAL_SIGNAL_RULES = (
    {
        "pattern": r"\bpress marks?\b|\blcd marks?\b|\bscreen blemish(?:es)?\b",
        "label": "marcas de presion en pantalla",
        "penalty": 18,
    },
    {
        "pattern": r"\bcrack(?:ed|s)?\b|\bbroken\b|\bshattered\b|\bfracture(?:d)?\b",
        "label": "grietas o roturas",
        "penalty": 28,
    },
    {
        "pattern": r"\bdents?\b|\bdings?\b|\bcorner damage\b|\bcorner wear\b",
        "label": "golpes o abolladuras",
        "penalty": 12,
    },
    {
        "pattern": r"\bedge wear\b|\bside wear\b|\bchipped\b|\bplastic damage\b",
        "label": "desgaste en bordes o carcasa",
        "penalty": 8,
    },
    {
        "pattern": r"\bscuff(?:ing|s)?\b|\bscratch(?:es)?\b",
        "label": "marcas cosmeticas visibles",
        "penalty": 5,
    },
    {
        "pattern": r"\brub wear\b|\bkey wear\b|\bkeyboard wear\b|\bpalm rest wear\b|\btouchpad wear\b",
        "label": "desgaste por uso en teclado o apoyo",
        "penalty": 7,
    },
    {
        "pattern": r"\bmissing piece\b|\bmissing key(?:s)?\b",
        "label": "piezas faltantes",
        "penalty": 20,
    },
    {
        "pattern": r"\bhinge damage\b|\bhinge issue(?:s)?\b|\bloose hinge(?:s)?\b",
        "label": "problemas de bisagra",
        "penalty": 18,
    },
    {
        "pattern": r"\bbattery\b.*\b(?:not hold|not holding|poor|bad|weak|unknown|cannot warranty|can't warranty|not warranty)\b",
        "label": "bateria de estado incierto",
        "penalty": 8,
    },
)
VISION_SOFTWARE_SIGNAL_RULES = (
    {
        "pattern": r"\bno os\b|\bwithout os\b|\bno operating system\b|\bos not included\b",
        "label": "sin sistema operativo",
    },
    {
        "pattern": r"\boperating system not included\b|\bwindows not included\b|\bwindows not installed\b",
        "label": "sistema operativo no incluido",
    },
    {
        "pattern": r"\bneeds windows\b|\bneeds os\b|\bfresh install\b|\bdriver(?:s)? missing\b",
        "label": "requiere instalacion de software",
    },
)


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
            session.trust_env = False
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

    def update(self, table: str, data: dict, filters: str) -> Optional[dict]:
        """Actualiza un registro."""
        try:
            response = self._session().patch(
                f"{self.url}/rest/v1/{table}?{filters}",
                headers={**self.headers, "Prefer": "return=representation"},
                json=data,
                timeout=15,
            )
            if response.status_code in (200, 204):
                result = response.json() if response.text else []
                return result[0] if isinstance(result, list) and result else result
            _log("DB", f"Update {table} fallo con status {response.status_code}: {_truncate_text(response.text)}")
            return None
        except Exception as error:
            _log("DB", f"Error actualizando en {table}: {error}")
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
                    "model": "llama-3.3-70b-versatile",
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

        score = self._coerce_score(data.get("score", 50))
        calidad_visual = data.get("calidad_visual") or self._score_to_quality(score)

        return {
            "status": "success",
            "error_code": None,
            "provider_status": 200,
            "es_producto_real": bool(data.get("es_producto_real", True)),
            "calidad_visual": calidad_visual,
            "defectos": defectos,
            "score": score,
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
                os.path.join(base_dir, "examples", "bad_laptop_dirty.png"),
                "Ejemplo de estado inaceptable por suciedad/desgaste extremo (reposamanos manchado, trackpad desgastado, aspecto vulgar):",
                "Entendido. Este ejemplo se penaliza fuerte con un score bajo por ser estéticamente asqueroso y requerir demasiada limpieza o reemplazo de chasis.",
            ),
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

        # Cargar reportes dinámicos del usuario directamente desde la Base de Datos Supabase
        db_items = []
        if self.supabase:
            try:
                db_items = self.supabase.query("ejemplos_equivocados", limit=5) or []
            except Exception as e:
                _log("ML", f"Consulta Supabase ejemplos_equivocados: {e}")

        if not db_items:
            user_wrong_path = os.path.join(base_dir, "ejemplos_equivocados.json")
            if os.path.exists(user_wrong_path):
                try:
                    with open(user_wrong_path, "r", encoding="utf-8") as f:
                        db_items = json.load(f)
                except Exception:
                    db_items = []

        for item in reversed(db_items):
            if len(examples) >= VISION_FEW_SHOT_LIMIT + 3:
                break
            img_url = item.get("imagen_url")
            img_path = item.get("imagen_local_path")
            
            target_url = None
            if img_url and str(img_url).startswith("http"):
                target_url = str(img_url)
            elif img_path:
                full_p = img_path if os.path.isabs(img_path) else os.path.join(base_dir, img_path)
                if os.path.exists(full_p):
                    mime_type = mimetypes.guess_type(full_p)[0] or "image/jpeg"
                    with open(full_p, "rb") as fh:
                        target_url = f"data:{mime_type};base64,{base64.b64encode(fh.read()).decode('utf-8')}"

            if target_url:
                motivo = item.get("motivo_error", "Producto incorrecto / accesorio")
                tit = item.get("titulo", "Producto")
                examples.append(
                    {
                        "prompt": f"Ejemplo RECHAZADO EN BASE DE DATOS por el usuario (Motivo: {motivo}) para: '{tit[:60]}':",
                        "assistant": f"Entendido. Registro verificado en BD. Este producto fue marcado como equivocado por el usuario debido a '{motivo}'. Si el producto analizado es un accesorio, mica, protector de pantalla o no corresponde a una laptop real, asigno score 10 y es_producto_real=false.",
                        "url": target_url,
                    }
                )

        self._few_shot_examples = examples[:VISION_FEW_SHOT_LIMIT + 3]
        return self._few_shot_examples

    def _coerce_score(self, value: Any, default: int = 50) -> int:
        try:
            score = int(round(float(value)))
        except (TypeError, ValueError):
            score = default
        return max(0, min(100, score))

    def _score_to_quality(self, score: int) -> str:
        if score >= 90:
            return "excelente"
        if score >= 80:
            return "buena"
        if score >= 65:
            return "aceptable"
        if score >= 45:
            return "mala"
        return "terrible"

    def _detect_signal_rules(
        self,
        text: str,
        rules: tuple[Dict[str, Any], ...],
    ) -> List[Dict[str, Any]]:
        normalized = str(text or "").lower()
        hits: List[Dict[str, Any]] = []
        seen = set()

        for rule in rules:
            label = rule["label"]
            if label in seen:
                continue
            if re.search(rule["pattern"], normalized, re.IGNORECASE):
                hits.append(rule)
                seen.add(label)

        return hits

    def _merge_defects(self, *defect_groups: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()

        for group in defect_groups:
            for defect in group:
                label = str(defect or "").strip()
                if not label:
                    continue
                normalized = label.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(label)

        return merged

    def _post_process_visual_result(
        self,
        data: Dict[str, Any],
        titulo: str,
        seller_notes: str,
        condicion: str = "",
    ) -> Dict[str, Any]:
        score = self._coerce_score(data.get("score", 50))
        note = str(data.get("nota", "") or "").strip()
        source_text = " ".join(part for part in [titulo, seller_notes] if part)
        software_context = " ".join(part for part in [source_text, note] if part)
        normalized_condition = str(condicion or "").strip().lower()

        physical_hits = self._detect_signal_rules(source_text, VISION_PHYSICAL_SIGNAL_RULES)
        software_hits = self._detect_signal_rules(software_context, VISION_SOFTWARE_SIGNAL_RULES)
        physical_labels = [hit["label"] for hit in physical_hits]

        total_penalty = sum(int(hit.get("penalty", 0)) for hit in physical_hits)
        if total_penalty >= 35:
            score = min(score, 58)
        elif total_penalty >= 22:
            score = min(score, 68)
        elif total_penalty >= 12:
            score = min(score, 78)
        elif total_penalty > 0:
            score = min(score, 86)

        note_lower = note.lower()
        software_only_note = (
            ("sistema operativo" in note_lower or "operating system" in note_lower or "windows" in note_lower)
            and not physical_hits
        )
        if software_hits and software_only_note:
            score = max(score, 82)

        if normalized_condition == "used" and not physical_hits and score > 88:
            score = 88
            if not note:
                note = "Listing usado sin evidencias claras de estado premium; se reservo el rango 90+ para equipos excepcionalmente limpios."

        if physical_hits:
            score = max(score, 25)
            destacados = ", ".join(physical_labels[:3])
            note = (
                f"Seller Notes reportan {destacados}. "
                "Se bajo la nota por desgaste o riesgos fisicos reales."
            )
        elif software_hits and software_only_note:
            note = (
                "No se observan danos fisicos relevantes. "
                "La falta de sistema operativo es facil de resolver y casi no penaliza la nota."
            )

        current_defects = data.get("defectos", [])
        if not isinstance(current_defects, list):
            current_defects = [str(current_defects)]

        return {
            **data,
            "score": score,
            "calidad_visual": self._score_to_quality(score),
            "defectos": self._merge_defects(current_defects, physical_labels),
            "nota": note or "Analisis visual completado.",
        }

    def _sample_evenly_spaced_urls(self, urls: List[str], limit: int) -> List[str]:
        if limit <= 0:
            return []
        if len(urls) <= limit:
            return list(urls)

        selected_indices = set()
        max_index = len(urls) - 1

        for slot in range(limit):
            if limit == 1:
                index = 0
            else:
                index = round(slot * max_index / (limit - 1))
            selected_indices.add(index)

        selected_urls = [urls[index] for index in sorted(selected_indices)]

        for url in urls:
            if len(selected_urls) >= limit:
                break
            if url in selected_urls:
                continue
            selected_urls.append(url)

        return selected_urls[:limit]

    def prepare_product_image_urls(self, imagenes_urls: Any, limit: int = VISION_MAX_PRODUCT_IMAGES) -> List[str]:
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
        return self._sample_evenly_spaced_urls(cleaned_urls, limit)

    def _download_single_image(self, url: str, timeout: int = 5) -> Optional[Any]:
        try:
            resp = self._session().get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception:
            pass
        return None

    def _build_collage(self, image_urls: List[str], max_images: int = 9) -> Optional[str]:
        urls = image_urls[:max_images]
        if len(urls) < 2:
            return None

        with ThreadPoolExecutor(max_workers=min(len(urls), 6)) as pool:
            results = list(pool.map(self._download_single_image, urls))

        images = [img for img in results if img is not None]
        if len(images) < 2:
            return None

        n = len(images)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        cell_w, cell_h = (400, 300)

        canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (18, 18, 24))
        draw = ImageDraw.Draw(canvas)

        for idx, img in enumerate(images):
            img_copy = img.copy()
            img_copy.thumbnail((cell_w, cell_h), Image.LANCZOS)
            x_offset = (idx % cols) * cell_w + (cell_w - img_copy.width) // 2
            y_offset = (idx // cols) * cell_h + (cell_h - img_copy.height) // 2
            canvas.paste(img_copy, (x_offset, y_offset))

            # Estampar etiqueta de número de foto (#1, #2, ...) en la esquina de la celda
            badge_text = f" #{idx + 1} "
            badge_x = (idx % cols) * cell_w + 10
            badge_y = (idx // cols) * cell_h + 10
            draw.rectangle([badge_x, badge_y, badge_x + 36, badge_y + 20], fill=(0, 0, 0, 200))
            draw.text((badge_x + 4, badge_y + 2), badge_text, fill=(255, 255, 255))

        buffer = BytesIO()
        canvas.save(buffer, format="JPEG", quality=82, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        _log("VISION", f"Collage generado exitosamente con etiquetas numeradas: {n} fotos en grid {cols}x{rows} ({len(buffer.getvalue()) // 1024} KB).")
        return f"data:image/jpeg;base64,{b64}"

    def _analysis_prompt(self, titulo: str, seller_notes: str, condicion: str = "") -> str:
        seller_notes_text = seller_notes or "Ninguna proporcionada"
        condicion_text = condicion or "No especificada"
        return f"""Analiza las imagenes de este listing de eBay: "{titulo}"

Condicion declarada: "{condicion_text}"
Notas del vendedor: "{seller_notes_text}"

NOTA SOBRE EL FORMATO: Si la imagen recibida es un COLLAGE/GRID de varias fotos, cada casilla representa una foto distinta del producto. Examina CADA casilla minuciosamente buscando cualquier falla.

Evalua sobre todo la condicion fisica, cosmetica y riesgos duros de hardware.
No castigues fuerte cosas faciles de resolver como falta de sistema operativo, Windows sin instalar, drivers faltantes o una instalacion limpia pendiente.
Si las notas mencionan press marks, dents, edge wear, scratches, rub wear, hinge damage, plastic damage, piezas faltantes o bateria dudosa, penaliza el score aunque las fotos no lo muestren del todo claro.
Mira el conjunto completo de fotos (o la cuadricula entera del collage) y toma en cuenta el peor desgaste creible que aparezca en cualquiera de ellas, no solo la imagen mas favorable.
Si la condicion es simplemente "Used", evita dar 90+ salvo que el equipo se vea excepcionalmente limpio y consistente en toda la galeria.

Prioridades:
1. Dano critico visible o producto FALSO/ACCESORIO (ej: protector de pantalla, mica, funda, sticker, repuesto) -> marcar es_producto_real: false y score 10.
2. Dano critico o fallas severas reportadas -> score 10-30.
2. Multiples defectos reales en Seller Notes -> score 35-70 segun severidad.
3. Desgaste cosmetico menor pero revendible -> score 75-89.
4. Equipo limpio con detalles minimos -> score 90-100.
5. Confirma si parece el producto real y no una foto generica.

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
        condicion: str = "",
    ) -> tuple[Dict[str, Any], Dict[str, int]]:
        few_shot_examples = self._load_few_shot_examples()
        
        # Extraer todas las URLs disponibles (hasta 9 para collage)
        all_product_urls = self.prepare_product_image_urls(imagenes_urls, VISION_MAX_PRODUCT_IMAGES)

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
            {"type": "text", "text": self._analysis_prompt(titulo, seller_notes, condicion)}
        ]

        # Intentar construir collage si hay más de 1 imagen
        collage_url = self._build_collage(all_product_urls) if len(all_product_urls) >= 2 else None
        
        if collage_url:
            user_content.append({"type": "image_url", "image_url": {"url": collage_url}})
            used_images_count = len(all_product_urls)
        else:
            # Fallback a imágenes directas (máximo 1 slot para reservar espacio para pocos pocos shots)
            for url in all_product_urls[:1]:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
            used_images_count = min(len(all_product_urls), 1)

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": "WILL_BE_REPLACED",
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 200,
            "temperature": 0.1,
        }
        metadata = {
            "few_shot_example_count": len(few_shot_examples),
            "product_image_count": used_images_count,
            "total_image_count": len(few_shot_examples) + (1 if collage_url else used_images_count),
            "collage_url": collage_url,
        }
        return payload, metadata

    def analizar_imagen(
        self,
        imagenes_urls: Any,
        titulo: str,
        seller_notes: str = "",
        condicion: str = "",
    ) -> Dict[str, Any]:
        """Analiza multiples imagenes con Groq Vision respetando los limites del proveedor."""
        if not self.groq_key:
            return self._error_result(
                status="unavailable",
                error_code="missing_api_key",
                calidad_visual="desconocida",
                nota="El analisis visual no esta configurado en el backend.",
            )

        payload, metadata = self.build_request_payload(imagenes_urls, titulo, seller_notes, condicion)
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
                f"con {metadata['few_shot_example_count']} ejemplo(s) few-shot. "
                f"Condicion={condicion or 'n/a'}."
            ),
        )

        started_at = time.perf_counter()
        for model_name in GROQ_VISION_MODELS:
            payload["model"] = model_name
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

                if response.status_code == 200:
                    break  # Exito, salimos del bucle de modelos
                    
                if response.status_code in (429, 400, 404):
                    _log(
                        "VISION",
                        f"Modelo {model_name} fallo ({response.status_code}), intentando con el siguiente..."
                    )
                    continue  # Intentar con el siguiente modelo
                    
                # Si es otro error (no 429), fallamos inmediatamente
                _log(
                    "VISION",
                    (
                        f"Groq devolvio {response.status_code} con {model_name} en {elapsed_ms} ms. "
                        f"Respuesta: {_truncate_text(response.text)}"
                    ),
                )
                return self._error_result(
                    status="error",
                    error_code="provider_http_error",
                    provider_status=response.status_code,
                    nota="Groq Vision rechazo el analisis en este momento. Puedes reintentar.",
                )
                
            except requests.RequestException as error:
                _log("VISION", f"Error de red al analizar imagenes con {model_name}: {error}")
                return self._error_result(
                    status="error",
                    error_code="provider_request_error",
                    provider_status=None,
                    nota="No se pudo conectar con Groq Vision. Intenta de nuevo en un momento.",
                )
                
        # Si llegamos aqui, significa que todos los modelos fallaron (probablemente todos con 429)
        if response.status_code != 200:
            return self._error_result(
                status="error",
                error_code="provider_rate_limit",
                provider_status=429,
                nota="Todos los modelos visuales estan agotados por ahora. Intenta de nuevo mas tarde.",
            )

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = _extract_json_object(content)
            data = self._post_process_visual_result(data, titulo, seller_notes, condicion)
            if metadata.get("collage_url"):
                data["collage_url"] = metadata["collage_url"]
            _log("VISION", f"Analisis completado en {elapsed_ms} ms con score {data.get('score', 50)}.")
            return self._success_result(data)
        except Exception as error:
            _log("VISION", f"Error procesando la respuesta visual: {error}")
            return self._error_result(
                status="error",
                error_code="invalid_provider_payload",
                provider_status=200,
                nota="Groq Vision respondio, pero el formato no fue valido. Puedes reintentar.",
            )

    def extraer_titulo_local(self, image_url: str = None, base64_image: str = None, original_title: str = None, extra_specs: dict = None) -> Dict[str, Any]:
        """Extrae el modelo y titulo de una imagen de Marketplace o eBay."""
        if not self.groq_key:
            return {"status": "error", "titulo": ""}

        prompt = (
            "Eres un experto analista de hardware y electronica. Tu tarea es generar un titulo CANONICO, "
            "LIMPIO y NORMALIZADO para el producto que se muestra en la imagen y/o el texto de referencia.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. NO copies y pegues el titulo original. Debes reescribirlo usando un formato profesional y limpio.\n"
            "2. Analiza la IMAGEN con mucho cuidado. A veces las cajas, etiquetas o pantallas muestran especificaciones vitales (RAM, Almacenamiento, Procesador, Color, Modelo exacto) que NO estan en el texto original.\n"
            "3. El formato DEBE ser: [Marca] [Linea/Familia] [Modelo Específico] | [Procesador/Chip] | [RAM] | [Almacenamiento] | [Specs Extra].\n"
            "4. Si es un telefono (como iPhone), el formato DEBE ser: [Marca] [Modelo] - [Almacenamiento] - [Color/Compania si aplica].\n"
            "5. NO des explicaciones. Solo devuelve JSON valido.\n\n"
            "Ejemplos de salida esperada:\n"
            "{\"titulo\": \"Lenovo Thinkpad T14 Gen 2 | Intel Core i5-1145G7 | 16GB RAM | 512GB SSD\"}\n"
            "{\"titulo\": \"Apple iPhone 16 Pro Max - 256GB - Titanium (Unlocked)\"}\n"
        )
        context_parts = []
        if original_title:
            context_parts.append(f"Titulo original: {original_title}")
        if extra_specs:
            specs_str = ", ".join([f"{k}: {v}" for k, v in extra_specs.items() if v])
            if specs_str:
                context_parts.append(f"Especificaciones extraídas de la base de datos: {specs_str}")
        
        if context_parts:
            prompt += "\n\nContexto como pistas complementarias (USA ESTA INFORMACION PARA ARMAR EL TITULO):\n- " + "\n- ".join(context_parts)

        img_obj = {"url": image_url} if image_url else {"url": base64_image}

        payload = {
            "model": "WILL_BE_REPLACED",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": img_obj},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 100,
            "temperature": 0.1,
        }

        started_at = time.perf_counter()
        for model_name in GROQ_VISION_MODELS:
            payload["model"] = model_name
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
                if response.status_code == 200:
                    body = response.json()
                    content = body["choices"][0]["message"]["content"]
                    data = _extract_json_object(content)
                    return {"status": "success", "titulo": data.get("titulo", "")}
                
                if response.status_code in (429, 400, 404):
                    continue
                break
            except Exception as e:
                _log("VISION", f"Error extrayendo titulo local con {model_name}: {e}")
                
        return {"status": "error", "titulo": ""}


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
