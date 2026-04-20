import os
import sys
import time
from typing import Optional

# Forzar UTF-8 en Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import obtener_configuracion, CATEGORIAS_BUSQUEDA, todos_los_destinos
from utils import cargar_ofertas_enviadas, guardar_ofertas_enviadas
from ebay_client import (
    buscar_vendedores_prioritarios, 
    buscar_ofertas_categoria_api, 
    buscar_ofertas_categoria_scraping, 
    dormir_entre_busquedas,
    EbayChallengeError,
    EbayBrowser
)
from supabase_integration import SupabaseClient, AnalizadorRentabilidad, AnalizadorVisual, guardar_producto_supabase
from telegram_utils import enviar_telegram_texto, enviar_telegram_foto

def ejecutar_ciclo(config: dict, browser: Optional[EbayBrowser]) -> bool:
    enviadas = cargar_ofertas_enviadas()
    reportadas_en_ciclo = set()
    hubo_ofertas = False

    # Inicializar Supabase y Analizadores
    sb_client = None
    analizador_rent = None
    analizador_vis = None
    if config.get("supabase_url") and config.get("supabase_service_key"):
        sb_client = SupabaseClient(config["supabase_url"], config["supabase_service_key"])
        if config.get("groq_api_key"):
            analizador_rent = AnalizadorRentabilidad(config.get("groq_api_key"), sb_client)
            analizador_vis = AnalizadorVisual(config.get("groq_api_key"))

    print("Iniciando búsqueda agrupada por marca hacia Telegram...")

    # PASO 0: Vendedores prioritarios
    ofertas_prioritarias = buscar_vendedores_prioritarios(config, enviadas | reportadas_en_ciclo)
    if ofertas_prioritarias:
        ofertas_prioritarias.sort(key=lambda x: x.precio)
        print(f"\n  [⭐] {len(ofertas_prioritarias)} ofertas de vendedores prioritarios. Procesando...")

        if not config["dry_run"]:
            encabezado = f"⭐ <b>VENDEDORES PRIORITARIOS | {len(ofertas_prioritarias)} OFERTAS</b> ⭐"
            for tok, cid in todos_los_destinos(config):
                enviar_telegram_texto(tok, cid, encabezado)
            time.sleep(1)

            for oferta in ofertas_prioritarias:
                rentabilidad = None
                visual = None
                if analizador_rent:
                    rentabilidad = analizador_rent.analizar(oferta.titulo, oferta.precio, {}, "laptop", oferta.es_subasta)
                if analizador_vis and getattr(oferta, 'imagen', None):
                    visual = analizador_vis.analizar_imagen(oferta.imagen, oferta.titulo)

                for tok, cid in todos_los_destinos(config):
                    enviar_telegram_foto(tok, cid, oferta, rentabilidad)
                
                if sb_client:
                    guardar_producto_supabase(sb_client, oferta, rentabilidad, visual, "regencytechnologies")

                reportadas_en_ciclo.add(oferta.enlace)
                time.sleep(1.5)

            enviadas.update(reportadas_en_ciclo)
            hubo_ofertas = True

    # PASO 1: Búsqueda normal por marca
    for marca in config["marcas"]:
        print(f"\n[*] Recolectando ofertas para la marca: {marca.upper()}...")
        ofertas_marca_acumuladas = []

        for categoria in CATEGORIAS_BUSQUEDA:
            try:
                if config.get("use_ebay_api"):
                    ofertas = buscar_ofertas_categoria_api(config, categoria, marca, enviadas | reportadas_en_ciclo)
                else:
                    ofertas = buscar_ofertas_categoria_scraping(browser, config, categoria, marca, enviadas | reportadas_en_ciclo)
                    
                if ofertas: ofertas_marca_acumuladas.extend(ofertas)
                dormir_entre_busquedas(config)
            except EbayChallengeError as error:
                print(f"  [!] El proceso se detiene por bloqueo de eBay: {error}")
                return False
            except Exception as error:
                print(f"  [!] Error inesperado en {marca} {categoria['nombre']}: {error}")
                time.sleep(5)

        if ofertas_marca_acumuladas:
            ofertas_marca_acumuladas.sort(key=lambda x: (x.vendedor.lower() != "regencytechnologies", x.precio))
            print(f"  [+] {len(ofertas_marca_acumuladas)} oferta(s) encontradas. Procesando...")
            
            if not config["dry_run"]:
                encabezado = f"🔥 <b>TOP {len(ofertas_marca_acumuladas)} ENCONTRADAS | {marca.upper()}</b> 🔥"
                for tok, cid in todos_los_destinos(config):
                    enviar_telegram_texto(tok, cid, encabezado)
                time.sleep(1)
                
                for oferta in ofertas_marca_acumuladas:
                    rentabilidad = None
                    visual = None
                    if analizador_rent:
                        rentabilidad = analizador_rent.analizar(oferta.titulo, oferta.precio, {}, "laptop", oferta.es_subasta)
                    if analizador_vis and getattr(oferta, 'imagen', None):
                        visual = analizador_vis.analizar_imagen(oferta.imagen, oferta.titulo)

                    for tok, cid in todos_los_destinos(config):
                        enviar_telegram_foto(tok, cid, oferta, rentabilidad)
                        
                    if sb_client:
                        guardar_producto_supabase(sb_client, oferta, rentabilidad, visual, marca)

                    reportadas_en_ciclo.add(oferta.enlace)
                    time.sleep(1.5) 
                
                enviadas.update(reportadas_en_ciclo)
                hubo_ofertas = True

    if hubo_ofertas and not config["dry_run"]:
        guardar_ofertas_enviadas(enviadas)

    if not hubo_ofertas: print("\nCiclo completado sin ofertas nuevas.")
    return True

def main() -> None:
    config = obtener_configuracion()
    if not config["telegram_token"] or not config["telegram_chat_ids"]:
        print("❌ Error: Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el archivo .env")
        return

    horas = float(os.getenv("INTERVALO_HORAS", "8.0"))
    intervalo_segundos = max(1, int(horas * 3600))
    if config["dry_run"]: print("DRY_RUN activo: no se enviaran mensajes reales.")

    browser: Optional[EbayBrowser] = None
    if config.get("use_ebay_api") and config.get("ebay_client_id"):
        print("Modo API activo: usando eBay Browse API.")
    elif config["use_browser_fallback"]:
        browser = EbayBrowser(config)
    else:
        print("Modo público activo.")

    try:
        if config["run_once"]:
            print(f"Ejecución única de búsqueda de ofertas...")
            if browser: browser.iniciar()
            ejecutar_ciclo(config, browser)
        else:
            print(f"Bot iniciado. Monitoreando ofertas cada {horas} horas...")
            if browser: browser.iniciar()
            while True:
                continuar = ejecutar_ciclo(config, browser)
                if not continuar:
                    print("Se requiere intervención manual (ej: resolver CAPTCHA).")
                    break
                print(f"Esperando {horas} horas hasta el siguiente ciclo...")
                time.sleep(intervalo_segundos)
    except KeyboardInterrupt:
        print("\nBot detenido por el usuario.")
    finally:
        if browser: browser.cerrar()

if __name__ == "__main__":
    main()
