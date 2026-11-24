import os
import json
import datetime
from dotenv import load_dotenv
from supabase_integration import SupabaseClient
from config import obtener_configuracion

def backup_table(sb_client, table_name, output_dir):
    print(f"Respaldando tabla: {table_name}...")
    try:
        # Paginación para descargar todos los registros si hay más de 1000
        all_data = []
        limit = 1000
        offset = 0
        while True:
            # Usando la API REST directamente desde el cliente para paginar
            response = sb_client._session().get(
                f"{sb_client.url}/rest/v1/{table_name}",
                headers=sb_client.headers,
                params={"limit": limit, "offset": offset},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                all_data.extend(data)
                if len(data) < limit:
                    break
                offset += limit
            else:
                print(f"Error descargando {table_name}: {response.text}")
                break

        if all_data:
            file_path = os.path.join(output_dir, f"{table_name}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            print(f"✓ {len(all_data)} registros guardados en {file_path}")
        else:
            print(f"La tabla {table_name} está vacía o no existe.")
            
    except Exception as e:
        print(f"Error al respaldar {table_name}: {e}")

def main():
    load_dotenv()
    config = obtener_configuracion()
    
    url = config.get("supabase_url")
    key = config.get("supabase_service_key")
    
    if not url or not key:
        print("Error: No se encontró supabase_url o supabase_service_key en .env")
        return
        
    sb_client = SupabaseClient(url, key)
    
    # Crear carpeta de backups
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups", f"backup_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"\nIniciando respaldo local en: {backup_dir}")
    print("-" * 50)
    
    tables_to_backup = [
        "productos",
        "precios_nicaragua",
        "busquedas",
        "alertas",
        "bot_settings",
        "inventario"
    ]
    
    for table in tables_to_backup:
        backup_table(sb_client, table, backup_dir)
        
    print("-" * 50)
    print("Respaldo completado exitosamente.\n")

if __name__ == "__main__":
    main()
