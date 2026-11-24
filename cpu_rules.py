import re
from typing import List

MIN_INTEL_GEN = 11
MIN_RYZEN_SERIE = 4000
SUFIJO_CPU = r'(?:hq|hk|hx|mq|qm|u|y|h|m|t|g\d|x)'

# Familias obsoletas o de gama baja
_RE_OBSOLETAS_FAMILIA = re.compile(r'\b(?:athlon|pentium|celeron|atom|core\s*2\s*duo)\b|\ba\d{1,2}\b')
# Tiers mínimos: rechazar Core i3 y Ryzen 3 en cualquier generación/serie
_RE_TIER_BAJO = re.compile(r'\bi3\b|\bryzen\s*3\b')
# Contexto Intel y expresiones textuales de generación
_RE_INTEL_CTX = re.compile(r'\b(?:intel|core|i[3579]|pentium|celeron)\b')
_RE_GEN_VIEJA_TXT = re.compile(r'\b(?:1st|2nd|3rd|[4-9]th|10th)\s*gen\b|\bgen\s*(?:[1-9]|10)\b')
_RE_GEN_MODERNA_TXT = re.compile(r'\b1[1-9]th\s*gen\b|\bgen\s*1[1-9]\b|\b1[1-9]\s*gen\b')
# Modelos Intel (con prefijo i/m o sufijo de CPU) y series Ryzen
_RE_INTEL_PREFIJO = re.compile(r'\b[im][3579][-\s]?(\d{4,5})[a-z0-9]*\b')
_RE_INTEL_SUFIJO = re.compile(r'\b(\d{4,5})' + SUFIJO_CPU + r'\b')
_RE_RYZEN_SERIE = re.compile(r'\bryzen(?:\s*[3579])?(?:\s*pro)?[-\s]+(\d{4})[a-z]*\b')


def _gen_intel(modelo: str) -> int:
    # 5 dígitos (10210, 13700) o 4 dígitos que empiezan con 1 (1135, 1005): gen = dos primeros dígitos
    # 4 dígitos que empiezan con 2-9 (8250, 9750): gen = primer dígito
    if len(modelo) == 5 or modelo.startswith('1'):
        return int(modelo[:2])
    return int(modelo[0])


def _extraer_modelos_intel(t: str) -> List[str]:
    modelos = _RE_INTEL_PREFIJO.findall(t)
    # Evitar que sufijos de Ryzen (4800H, 5500U) se interpreten como Intel 4ª/5ª gen
    if 'ryzen' not in t:
        modelos += _RE_INTEL_SUFIJO.findall(t)
    return modelos


def es_cpu_obsoleta(titulo: str) -> bool:
    t = str(titulo).lower()
    if _RE_TIER_BAJO.search(t):
        return True
    if _RE_OBSOLETAS_FAMILIA.search(t):
        return True
    series_ryzen = [int(s) for s in _RE_RYZEN_SERIE.findall(t)]
    if series_ryzen and any(s < MIN_RYZEN_SERIE for s in series_ryzen):
        return True
    modelos = _extraer_modelos_intel(t)
    if modelos:
        return any(_gen_intel(m) < MIN_INTEL_GEN for m in modelos)
    # Solo aplicar "gen N" textual si no hubo modelo Intel explícito (ej. "ThinkPad T14 Gen 2 i5-1135G7")
    if _RE_INTEL_CTX.search(t) and _RE_GEN_VIEJA_TXT.search(t):
        return True
    return False


def es_cpu_moderna(titulo: str) -> bool:
    t = str(titulo).lower()
    if es_cpu_obsoleta(t):
        return False
    if 'core ultra' in t or re.search(r'\bultra\s*[3579]\b', t):
        return True
    series_ryzen = [int(s) for s in _RE_RYZEN_SERIE.findall(t)]
    if any(s >= MIN_RYZEN_SERIE for s in series_ryzen):
        return True
    modelos = _extraer_modelos_intel(t)
    if any(_gen_intel(m) >= MIN_INTEL_GEN for m in modelos):
        return True
    if _RE_INTEL_CTX.search(t) and _RE_GEN_MODERNA_TXT.search(t):
        return True
    return False
