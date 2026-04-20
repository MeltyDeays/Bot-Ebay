"""Test del análisis de rentabilidad HONESTO."""
import sys, os, time
os.chdir('c:/Users/everd/Documents/Ofertas eBay')
sys.path.insert(0, '.')
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from supabase_integration import AnalizadorRentabilidad
from dotenv import load_dotenv
load_dotenv()

groq_key = os.getenv("GROQ_API_KEY", "")
analizador = AnalizadorRentabilidad(groq_key)  # Sin Supabase = sin referencias

print("=" * 70)
print("  TEST DE RENTABILIDAD — Versión honesta")
print("=" * 70)

tests = [
    # Subasta (NO debe calcular rentabilidad)
    {"titulo": "HP ELITEBOOK 845 G7 | RYZEN 5 PRO 4650U | 512GB | 16GB",
     "precio": 33.0, "specs": {}, "tipo": "laptop", "subasta": True},

    # Precio fijo pero SIN referencias de Nicaragua
    {"titulo": "Dell Latitude 5420 i5-1145G7 16GB 256GB SSD Win11",
     "precio": 165.0, "specs": {}, "tipo": "laptop", "subasta": False},

    # Precio fijo (el costo de importación SÍ es calculable)
    {"titulo": "HP ProBook 455 G8 Ryzen 5 5600U 16GB 512GB",
     "precio": 189.0, "specs": {}, "tipo": "laptop", "subasta": False},

    # Subasta barata
    {"titulo": "Lenovo ThinkPad L14 Gen 1 Ryzen 3 PRO 4450U",
     "precio": 0.01, "specs": {}, "tipo": "laptop", "subasta": True},
]

for t in tests:
    r = analizador.analizar(t["titulo"], t["precio"], t["specs"], t["tipo"], t["subasta"])
    print(f"\n{'─' * 70}")
    tipo_precio = "🏷️ SUBASTA" if t["subasta"] else "💵 PRECIO FIJO"
    print(f"  {tipo_precio} — ${t['precio']:.2f}")
    print(f"  📦 {t['titulo'][:55]}")
    
    if t["subasta"]:
        print(f"  ⚠️  {r['analisis_rentabilidad']}")
    else:
        costo = r.get("costo_importacion", 0)
        tiene_refs = r.get("tiene_referencias", False)
        print(f"  📦 Costo importación: ${costo:.2f}")
        if tiene_refs:
            print(f"  🏷️  Venta NIC: ${r.get('precio_estimado_nic', 0):.2f}")
            print(f"  💰 Margen: ${r.get('margen_estimado', 0):.2f}")
        else:
            print(f"  ❓ Sin datos de Nicaragua — necesitas agregar precios de FB Marketplace")
        print(f"  💡 {r['analisis_rentabilidad']}")
    time.sleep(0.3)

print(f"\n{'=' * 70}")
print(f"\n📋 NOTA: Para ver rentabilidad real, necesitas:")
print(f"   1. Crear las tablas en Supabase (ejecutar schema.sql)")
print(f"   2. Agregar precios reales de FB Marketplace Nicaragua")
print(f"   3. Con datos reales, la IA comparará automáticamente")
