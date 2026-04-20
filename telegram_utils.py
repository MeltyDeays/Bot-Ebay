import html
import requests
from typing import Dict, Any

def enviar_telegram_texto(token: str, chat_id: str, mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: 
        requests.post(url, json=payload, timeout=30)
    except Exception as e: 
        print(f"Error enviando telegram texto: {e}")

def enviar_telegram_foto(token: str, chat_id: str, oferta: Any, rentabilidad: Dict = None, etiqueta_especial: str = None) -> None:
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    # Soporta OfertaLaptop (dataclass) o dict
    is_dict = isinstance(oferta, dict)
    
    titulo = oferta.get("titulo", "") if is_dict else oferta.titulo
    estado = oferta.get("condicion", "") if is_dict else oferta.estado
    procesador = oferta.get("procesador", "") if is_dict else getattr(oferta, "procesador", "")
    precio_texto = oferta.get("precio_texto", "") if is_dict else oferta.precio_texto
    vendedor = oferta.get("vendedor", "") if is_dict else getattr(oferta, "vendedor", "")
    es_subasta = oferta.get("es_subasta", False) if is_dict else oferta.es_subasta
    tiempo_restante = oferta.get("tiempo_restante", "") if is_dict else getattr(oferta, "tiempo_restante", "")
    enlace = oferta.get("enlace", "") if is_dict else oferta.enlace
    imagen = oferta.get("imagen_url", "") if is_dict else getattr(oferta, "imagen", "")
    
    titulo_limpio = html.escape(titulo)
    
    caption = ""
    if etiqueta_especial:
        caption += f"💎 <b>{etiqueta_especial}</b> 💎\n\n"
        
    caption += (
        f"💻 <b>{titulo_limpio}</b>\n\n"
        f"✨ <b>Estado:</b> {html.escape(estado)}\n"
    )
    if procesador:
        caption += f"⚙️ <b>CPU:</b> {procesador}\n"
        
    caption += f"💰 <b>Precio:</b> {html.escape(precio_texto)}\n"
    
    vendedor_limpio = vendedor.strip() if vendedor else ""
    if vendedor_limpio:
        if vendedor_limpio.lower() == "regencytechnologies":
            caption += f"⭐ <b>Vendedor:</b> {html.escape(vendedor_limpio)} (¡Prioridad!)\n"
        else:
            caption += f"🏢 <b>Vendedor:</b> {html.escape(vendedor_limpio)}\n"
    
    if es_subasta:
        caption += f"⏳ <b>SUBASTA:</b> {tiempo_restante} restantes\n"
        
    if rentabilidad and rentabilidad.get("tiene_referencias"):
        margen = rentabilidad.get("margen_estimado", 0)
        pct = rentabilidad.get("porcentaje_ganancia", 0)
        venta = rentabilidad.get("precio_estimado_nic", 0)
        emoji = "🟢" if pct > 40 else ("🟡" if pct > 20 else "🔴")
        caption += f"\n{emoji} <b>Margen est. (NIC):</b> ${margen} ({pct}%)\n"
        caption += f"🏷️ <b>Venta en NIC:</b> ~${venta}\n"
        
    caption += f"\n🔗 <a href='{enlace}'>COMPRAR EN EBAY</a>"
    
    if not imagen:
        enviar_telegram_texto(token, chat_id, caption)
        return

    payload = {"chat_id": chat_id, "photo": imagen, "caption": caption, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error enviando foto a telegram, enviando como texto. Error: {e}")
        enviar_telegram_texto(token, chat_id, caption)
