"""Test masivo de IA (Llama 4 Scout via Groq) — 40 listings variados."""
import sys, os, time
os.chdir('c:/Users/everd/Documents/Ofertas eBay')
sys.path.insert(0, '.')
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from bot_ebay_laptops import analizar_con_gemini, obtener_configuracion
config = obtener_configuracion()

# ═══════════════════════════════════════════════════════════════
# 40 CASOS DE PRUEBA: Laptops buenas, basura, edge cases
# ═══════════════════════════════════════════════════════════════
TESTS = [
    # ── DEBEN SER ACEPTADAS (laptops válidas) ──
    {"titulo": "HP ELITEBOOK 845 G7 | AMD RYZEN 5 PRO 4650U | 512GB | 16GB | WIN11",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Fully tested, good working condition, minor cosmetic wear", "cond": "Used", "precio": 33.0, "esperado": "ACEPTAR"},

    {"titulo": "HP ELITEBOOK 845 G7 | AMD RYZEN 3 PRO 4450U | 256GB | 16GB | WINDOWS 11 PRO",
     "specs": [("Processor","AMD Ryzen 3 PRO 4450U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Clean laptop, Windows 11 Pro installed", "cond": "Used", "precio": 45.0, "esperado": "ACEPTAR"},

    {"titulo": "Lenovo ThinkPad T14 Gen 1 Ryzen 5 PRO 4650U 16GB 512GB SSD",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","16 GB"),("SSD Capacity","512 GB"),("Brand","Lenovo")],
     "desc": "Business laptop, excellent condition", "cond": "Certified Refurbished", "precio": 179.0, "esperado": "ACEPTAR"},

    {"titulo": "Dell Latitude 5420 Intel Core i5-1145G7 16GB 256GB SSD Win11 Pro",
     "specs": [("Processor","Intel Core i5-1145G7"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Corporate off-lease, wiped and ready", "cond": "Seller Refurbished", "precio": 165.0, "esperado": "ACEPTAR"},

    {"titulo": "HP ProBook 455 G8 AMD Ryzen 5 5600U 16GB 512GB SSD 15.6\" FHD",
     "specs": [("Processor","AMD Ryzen 5 5600U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Like new condition, barely used", "cond": "Open Box", "precio": 189.0, "esperado": "ACEPTAR"},

    {"titulo": "Lenovo ThinkPad L14 Gen 2 i5-1135G7 16GB RAM 256GB SSD Win 11",
     "specs": [("Processor","Intel Core i5-1135G7"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Small scratch on lid, fully functional", "cond": "Used", "precio": 155.0, "esperado": "ACEPTAR"},

    {"titulo": "ASUS VivoBook 15 Ryzen 7 5700U 16GB 512GB SSD FHD",
     "specs": [("Processor","AMD Ryzen 7 5700U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Great laptop for students and professionals", "cond": "Refurbished", "precio": 195.0, "esperado": "ACEPTAR"},

    {"titulo": "Acer Aspire 5 A515-56 i7-1165G7 16GB 512GB SSD 15.6\"",
     "specs": [("Processor","Intel Core i7-1165G7"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Excellent performance laptop, minor wear on palmrest", "cond": "Used", "precio": 185.0, "esperado": "ACEPTAR"},

    {"titulo": "HP 255 G10 15.6\" Ryzen 3 7330U 16GB RAM 1TB SSD NO OS",
     "specs": [("Processor","AMD Ryzen 3 7330U"),("RAM Size","16 GB"),("SSD Capacity","1 TB")],
     "desc": "No operating system installed, hardware fully functional", "cond": "Used", "precio": 175.0, "esperado": "ACEPTAR"},

    {"titulo": "Dell Inspiron 15 5515 Ryzen 5 5500U 16GB 256GB SSD FHD Touch",
     "specs": [("Processor","AMD Ryzen 5 5500U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Touch screen, good battery life", "cond": "Used", "precio": 155.0, "esperado": "ACEPTAR"},

    # Subasta sin precio claro
    {"titulo": "HP ELITEBOOK 845 G7 | RYZEN 5 PRO 4650U | 512GB | 32GB | WIN11PRO",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","32 GB"),("SSD Capacity","512 GB")],
     "desc": "Auction listing, ships fast", "cond": "Used", "precio": 0.01, "esperado": "ACEPTAR"},

    # Con cosmetic wear menor (debería aceptar)
    {"titulo": "Lenovo ThinkPad T14s Gen 1 Ryzen 7 PRO 4750U 16GB 512GB",
     "specs": [("Processor","AMD Ryzen 7 PRO 4750U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Small dent on corner, light scratches on lid, fully functional. All ports tested.", "cond": "Used", "precio": 150.0, "esperado": "ACEPTAR"},

    # MSI gaming laptop
    {"titulo": "MSI GF65 Thin 10UE i5-10500H 16GB 512GB RTX 3060 15.6\" 144Hz",
     "specs": [("Processor","Intel Core i5-10500H"),("RAM Size","16 GB"),("SSD Capacity","512 GB"),("GPU","NVIDIA RTX 3060")],
     "desc": "Gaming laptop, runs all modern games", "cond": "Used", "precio": 199.0, "esperado": "ACEPTAR"},

    # Laptop con NO OS está ok
    {"titulo": "LENOVO THINKPAD L14 GEN 1 | RYZEN 3 PRO 4450U | 512GB | 16GB | NO OS",
     "specs": [("Processor","AMD Ryzen 3 PRO 4450U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "No operating system, charger included", "cond": "Used", "precio": 89.0, "esperado": "ACEPTAR"},

    # Intel 12th gen
    {"titulo": "Dell Latitude 5430 i5-1245U 16GB 256GB SSD 14\" FHD Win11",
     "specs": [("Processor","Intel Core i5-1245U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "12th gen Intel, fast and reliable", "cond": "Refurbished", "precio": 199.0, "esperado": "ACEPTAR"},

    # ── DEBEN SER RECHAZADAS (basura/piezas/accesorios) ──

    # Motherboard suelta
    {"titulo": "HP 15-EF MOTHERBOARD DA0P5JMB6B0 RYZEN 3 5300 AMD RADEON",
     "specs": [("Type","Motherboard"),("Compatible Brand","HP")],
     "desc": "Motherboard only, pulled from working laptop", "cond": "Used", "precio": 45.0, "esperado": "RECHAZAR"},

    # Screen protector (accesorio)
    {"titulo": "15.6\" Anti Glare Screen Protector For Lenovo ideapad 3, 5/5i, Legion",
     "specs": [("Type","Screen Protector"),("Size","15.6 inches")],
     "desc": "Anti-glare screen protector for laptops", "cond": "New", "precio": 25.0, "esperado": "RECHAZAR"},

    # Charger (accesorio)
    {"titulo": "330W Gaming Charger Compatible with Lenovo Legion Pro 7i 9i Gen 10",
     "specs": [("Type","AC Adapter/Charger"),("Compatible Brand","Lenovo")],
     "desc": "High wattage charger for gaming laptops", "cond": "New", "precio": 100.0, "esperado": "RECHAZAR"},

    # For parts
    {"titulo": "HP EliteBook 840 G7 i5-10310U - FOR PARTS - No Power",
     "specs": [("Processor","Intel Core i5-10310U"),("RAM Size","16 GB")],
     "desc": "For parts only, does not power on, sold as is", "cond": "For parts", "precio": 55.0, "esperado": "RECHAZAR"},

    # Sin cargador
    {"titulo": "HP ELITEBOOK 845 G7 | AMD RYZEN 5 PRO 4650U | 512GB | 16GB | NO OS/POWER ADAPTER",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "No operating system and no power adapter included", "cond": "Used", "precio": 29.0, "esperado": "RECHAZAR"},

    # RAM insuficiente
    {"titulo": "HP EliteBook 845 G8 Ryzen 3 Pro 5450U 4GB RAM 256GB SSD",
     "specs": [("Processor","AMD Ryzen 3 Pro 5450U"),("RAM Size","4 GB"),("SSD Capacity","256 GB")],
     "desc": "Working laptop with 4GB RAM", "cond": "Used", "precio": 189.0, "esperado": "RECHAZAR"},

    # Generación vieja
    {"titulo": "HP EliteBook 840 G5 Intel Core i5-8350U 16GB 256GB SSD",
     "specs": [("Processor","Intel Core i5-8350U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "8th gen Intel laptop", "cond": "Used", "precio": 120.0, "esperado": "RECHAZAR"},

    # Chromebook
    {"titulo": "HP 14b-na Chromebook 14.0\" FHD AMD Ryzen 3 3250C 4GB 128GB",
     "specs": [("Processor","AMD Ryzen 3 3250C"),("RAM Size","4 GB"),("Storage","128 GB eMMC"),("Operating System","Chrome OS")],
     "desc": "Chromebook, Chrome OS only", "cond": "Refurbished", "precio": 99.0, "esperado": "RECHAZAR"},

    # SSD faltante
    {"titulo": "HP Laptop 15-EF1020NR AMD Ryzen 3 3250U 16GB RAM NO SSD",
     "specs": [("Processor","AMD Ryzen 3 3250U"),("RAM Size","16 GB")],
     "desc": "No SSD included, storage bay is empty", "cond": "Used", "precio": 75.0, "esperado": "RECHAZAR"},

    # Broken screen
    {"titulo": "Dell Latitude 5410 i5-10310U 16GB 256GB CRACKED SCREEN",
     "specs": [("Processor","Intel Core i5-10310U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Screen is cracked but laptop boots fine", "cond": "Used", "precio": 80.0, "esperado": "RECHAZAR"},

    # BIOS locked
    {"titulo": "Lenovo ThinkPad T14 Ryzen 5 4650U 16GB 512GB BIOS LOCK",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "BIOS password locked, cannot access OS", "cond": "Used", "precio": 45.0, "esperado": "RECHAZAR"},

    # Keyboard (pieza)
    {"titulo": "Keyboard for Lenovo ThinkPad T14 Gen 1 Ryzen 5 backlit US layout",
     "specs": [("Type","Keyboard"),("Compatible Brand","Lenovo"),("Compatible Model","ThinkPad T14")],
     "desc": "Replacement keyboard, brand new", "cond": "New", "precio": 35.0, "esperado": "RECHAZAR"},

    # Battery (pieza)
    {"titulo": "Battery for HP EliteBook 845 G7 G8 L77624-421 3Cell 53Wh",
     "specs": [("Type","Battery"),("Compatible Brand","HP")],
     "desc": "Replacement battery for EliteBook 845", "cond": "New", "precio": 42.0, "esperado": "RECHAZAR"},

    # Heavily damaged
    {"titulo": "Dell Latitude 5420 i5-1145G7 16GB 256GB - Heavy Wear Grade C",
     "specs": [("Processor","Intel Core i5-1145G7"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Grade C condition, heavy scratches, dents on chassis, keyboard worn", "cond": "Used", "precio": 95.0, "esperado": "RECHAZAR"},

    # Circuit breaker (no es laptop)
    {"titulo": "C-Series Single Pole Toggle Circuit Breakers",
     "specs": [("Type","Circuit Breaker")],
     "desc": "Electrical circuit breaker", "cond": "New", "precio": 90.0, "esperado": "RECHAZAR"},

    # ── EDGE CASES (situaciones ambiguas) ──

    # 8GB RAM (bajo pero posiblemente upgradeable)
    {"titulo": "HP ProBook 445 G7 Ryzen 5 4500U 8GB 256GB SSD Win10 Pro",
     "specs": [("Processor","AMD Ryzen 5 4500U"),("RAM Size","8 GB"),("SSD Capacity","256 GB")],
     "desc": "Good condition, RAM is upgradeable", "cond": "Used", "precio": 135.0, "esperado": "RECHAZAR"},

    # Sin specs claros en el título
    {"titulo": "HP laptop model 14-dq0011dx",
     "specs": [],
     "desc": "Laptop in good condition, works fine", "cond": "Used", "precio": 89.0, "esperado": "RECHAZAR"},

    # Ryzen viejo pero con specs buenos
    {"titulo": "Lenovo ThinkPad T495 Ryzen 5 3500U 16GB 512GB SSD",
     "specs": [("Processor","AMD Ryzen 5 3500U"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Older Ryzen but fully functional", "cond": "Used", "precio": 140.0, "esperado": "RECHAZAR"},

    # Título confuso pero laptop buena por specs
    {"titulo": "14-inch Business Laptop Computer Refurbished",
     "specs": [("Processor","AMD Ryzen 5 PRO 4650U"),("RAM Size","16 GB"),("SSD Capacity","256 GB"),("Brand","HP"),("Model","EliteBook 845 G7")],
     "desc": "Refurbished HP EliteBook with modern specs", "cond": "Refurbished", "precio": 169.0, "esperado": "ACEPTAR"},

    # Missing battery
    {"titulo": "Dell Latitude 5520 i5-1145G7 16GB 256GB SSD Missing Battery",
     "specs": [("Processor","Intel Core i5-1145G7"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Battery is missing, runs on AC power only", "cond": "Used", "precio": 110.0, "esperado": "RECHAZAR"},

    # As-is untested
    {"titulo": "HP EliteBook 840 G8 i5-1145G7 16GB 256GB SSD AS IS UNTESTED",
     "specs": [("Processor","Intel Core i5-1145G7"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Sold as-is, untested, no returns", "cond": "For parts", "precio": 65.0, "esperado": "RECHAZAR"},

    # Docking station (no laptop)
    {"titulo": "Lenovo ThinkPad USB-C Dock Gen 2 Docking Station 40AS",
     "specs": [("Type","Docking Station"),("Brand","Lenovo")],
     "desc": "USB-C docking station for ThinkPad laptops", "cond": "Used", "precio": 45.0, "esperado": "RECHAZAR"},

    # Laptop buena con Intel Ultra
    {"titulo": "Dell Latitude 7450 Ultra 7 155H 16GB 512GB SSD 14\" FHD+ Win11",
     "specs": [("Processor","Intel Core Ultra 7 155H"),("RAM Size","16 GB"),("SSD Capacity","512 GB")],
     "desc": "Latest Intel Ultra processor, premium build", "cond": "Open Box", "precio": 199.0, "esperado": "ACEPTAR"},

    # i3 11th gen (bueno)
    {"titulo": "HP ProBook 440 G8 Intel Core i3-1115G4 16GB 256GB SSD Win11",
     "specs": [("Processor","Intel Core i3-1115G4"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Entry level business laptop, great for office work", "cond": "Refurbished", "precio": 145.0, "esperado": "ACEPTAR"},

    # Ryzen 9 gaming
    {"titulo": "ASUS ROG Zephyrus G14 Ryzen 9 5900HS 16GB 1TB RTX 3060",
     "specs": [("Processor","AMD Ryzen 9 5900HS"),("RAM Size","16 GB"),("SSD Capacity","1 TB"),("GPU","NVIDIA RTX 3060")],
     "desc": "High-end gaming laptop, excellent thermals", "cond": "Used", "precio": 199.0, "esperado": "ACEPTAR"},

    # Water damage
    {"titulo": "Lenovo ThinkPad X13 Gen 2 Ryzen 5 5650U 16GB 256GB Water Damage",
     "specs": [("Processor","AMD Ryzen 5 PRO 5650U"),("RAM Size","16 GB"),("SSD Capacity","256 GB")],
     "desc": "Water spill damage, keyboard not working, screen OK", "cond": "For parts", "precio": 50.0, "esperado": "RECHAZAR"},
]

print(f"{'='*80}")
print(f"  TEST MASIVO DE IA — Llama 4 Scout via Groq")
print(f"  {len(TESTS)} listings de prueba")
print(f"{'='*80}\n")

aciertos = 0
errores = []

for i, t in enumerate(TESTS, 1):
    detalle = {
        "localizedAspects": [{"name": k, "value": v} for k, v in t["specs"]],
        "shortDescription": t["desc"],
        "condition": t["cond"],
    }
    resultado = analizar_con_gemini(config, t["titulo"], detalle, t["precio"])
    ok = resultado == t["esperado"]
    aciertos += int(ok)
    icon = "✅" if ok else "❌"
    print(f"  {icon} [{i:02d}/40] {resultado:8s} (esperado: {t['esperado']:8s}) | ${t['precio']:>7.2f} | {t['titulo'][:55]}")
    if not ok:
        errores.append((i, t["titulo"][:50], resultado, t["esperado"]))
    time.sleep(0.5)  # Respetar rate limits de Groq

print(f"\n{'='*80}")
print(f"  RESULTADO: {aciertos}/{len(TESTS)} correctos ({aciertos/len(TESTS)*100:.0f}%)")
if errores:
    print(f"\n  ❌ ERRORES ({len(errores)}):")
    for num, tit, got, exp in errores:
        print(f"     [{num:02d}] Got={got}, Expected={exp} | {tit}")
print(f"{'='*80}")
