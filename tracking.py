"""
Módulo de rastreo universal de paquetes.
Detecta el carrier a partir del tracking number y consulta el estado real.
Soporta: USPS, FedEx, UPS, DHL, Amazon Logistics.
"""
import re
import time
from typing import Any, Dict, Optional

import requests

# ─── Patrones de detección de carrier ─────────────────────
CARRIER_PATTERNS = [
    {
        "carrier": "usps",
        "name": "USPS",
        "patterns": [
            r"^(94|93|92|95)\d{20,}$",
            r"^\d{20,30}$",
            r"^[A-Z]{2}\d{9}US$",
        ],
        "url": "https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
    },
    {
        "carrier": "fedex",
        "name": "FedEx",
        "patterns": [r"^\d{12}$", r"^\d{15}$", r"^\d{20}$", r"^[0-9]{22}$"],
        "url": "https://www.fedex.com/fedextrack/?trknbr={tracking}",
    },
    {
        "carrier": "ups",
        "name": "UPS",
        "patterns": [r"^1Z[A-Z0-9]{16}$", r"^T\d{10}$"],
        "url": "https://www.ups.com/track?tracknum={tracking}",
    },
    {
        "carrier": "dhl",
        "name": "DHL",
        "patterns": [r"^\d{10}$", r"^[A-Z]{3}\d{7,}$", r"^JD\d{18}$"],
        "url": "https://www.dhl.com/us-en/home/tracking.html?tracking-id={tracking}",
    },
    {
        "carrier": "amazon",
        "name": "Amazon Logistics",
        "patterns": [r"^TBA\d{12,}$"],
        "url": "https://track.amazon.com/tracking/{tracking}",
    },
]

UNIVERSAL_TRACK_URL = "https://t.17track.net/en#nums={tracking}"

STATUS_DISPLAY = {
    "delivered": {"label": "✅ Entregado", "color": "#2ed573"},
    "out_for_delivery": {"label": "🚚 En reparto", "color": "#ffa502"},
    "in_transit": {"label": "✈️ En tránsito", "color": "#3742fa"},
    "label_created": {"label": "🏷️ Etiqueta creada", "color": "#a4b0be"},
    "exception": {"label": "⚠️ Excepción", "color": "#ff4757"},
    "unknown": {"label": "❓ Desconocido", "color": "#747d8c"},
}


def detect_carrier(tracking_number: str) -> Dict[str, str]:
    """Detecta el carrier a partir del tracking number."""
    cleaned = tracking_number.strip().upper().replace(" ", "")
    if not cleaned:
        return {"carrier": "unknown", "name": "Desconocido", "tracking_url": "", "universal_url": ""}

    for carrier_info in CARRIER_PATTERNS:
        for pattern in carrier_info["patterns"]:
            if re.match(pattern, cleaned, re.IGNORECASE):
                return {
                    "carrier": carrier_info["carrier"],
                    "name": carrier_info["name"],
                    "tracking_url": carrier_info["url"].format(tracking=cleaned),
                    "universal_url": UNIVERSAL_TRACK_URL.format(tracking=cleaned),
                }

    return {
        "carrier": "unknown",
        "name": "Carrier no identificado",
        "tracking_url": UNIVERSAL_TRACK_URL.format(tracking=cleaned),
        "universal_url": UNIVERSAL_TRACK_URL.format(tracking=cleaned),
    }


def _normalize_status(raw_status: str) -> str:
    """Normaliza el status del carrier a un valor estándar."""
    s = raw_status.lower()
    if any(w in s for w in ("delivered", "entregado", "your item was delivered")):
        return "delivered"
    if any(w in s for w in ("out for delivery", "en camino")):
        return "out_for_delivery"
    if any(w in s for w in ("in transit", "en tránsito", "transit", "departed", "arrived", "on its way", "processed")):
        return "in_transit"
    if any(w in s for w in ("picked up", "accepted", "shipping label", "label created", "origin post")):
        return "label_created"
    if any(w in s for w in ("exception", "alert", "held", "return")):
        return "exception"
    return "unknown"


def _fetch_usps_status(tracking_number: str) -> Optional[Dict[str, Any]]:
    """Intenta obtener estado de USPS."""
    try:
        url = f"https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking_number}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return None

        text = resp.text
        status_text = None

        # Intentar múltiples patrones
        for pattern in [
            r'class="tb-status[^"]*"[^>]*>\s*<[^>]+>\s*([^<]+)',
            r'class="delivery_status"[^>]*>([^<]+)',
            r'"statusCategory"\s*:\s*"([^"]+)"',
            r'"statusSummary"\s*:\s*"([^"]+)"',
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                status_text = match.group(1).strip()
                break

        # Fallback: buscar palabras clave
        if not status_text:
            if "Your item was delivered" in text or "Delivered" in text[:5000]:
                status_text = "Delivered"
            elif "In Transit" in text[:5000]:
                status_text = "In Transit"
            elif "Out for Delivery" in text[:5000]:
                status_text = "Out for Delivery"

        if status_text:
            return {
                "status": _normalize_status(status_text),
                "status_text": status_text,
                "location": None,
                "date": None,
                "source": "usps",
            }
        return None
    except Exception:
        return None


def _fetch_ups_status(tracking_number: str) -> Optional[Dict[str, Any]]:
    """Intenta obtener estado de UPS vía su endpoint público."""
    try:
        url = "https://www.ups.com/track/api/Track/GetStatus?loc=en_US"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"Locale": "en_US", "TrackingNumber": [tracking_number]}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        details = data.get("trackDetails", [])
        if details:
            detail = details[0] if isinstance(details, list) else details
            status_text = detail.get("packageStatus", "")
            if status_text:
                return {
                    "status": _normalize_status(status_text),
                    "status_text": status_text,
                    "location": detail.get("deliveredTo") or None,
                    "date": detail.get("deliveredDate") or detail.get("lastScanDate") or None,
                    "source": "ups",
                }
        return None
    except Exception:
        return None


def lookup_tracking(tracking_number: str) -> Dict[str, Any]:
    """Consulta el estado real del paquete."""
    cleaned = tracking_number.strip().upper().replace(" ", "")
    carrier = detect_carrier(cleaned)

    result = {
        "tracking_number": cleaned,
        **carrier,
        "status": None,
        "status_text": None,
        "status_display": STATUS_DISPLAY["unknown"],
        "location": None,
        "last_update": None,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    tracking_data = None
    if carrier["carrier"] == "usps":
        tracking_data = _fetch_usps_status(cleaned)
    elif carrier["carrier"] == "ups":
        tracking_data = _fetch_ups_status(cleaned)

    if tracking_data:
        result["status"] = tracking_data["status"]
        result["status_text"] = tracking_data["status_text"]
        result["status_display"] = STATUS_DISPLAY.get(tracking_data["status"], STATUS_DISPLAY["unknown"])
        result["location"] = tracking_data.get("location")
        result["last_update"] = tracking_data.get("date")

    return result
