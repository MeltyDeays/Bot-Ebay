from dataclasses import dataclass
from typing import Optional

@dataclass
class OfertaLaptop:
    categoria: str
    estado: str
    titulo: str
    precio: float
    precio_texto: str
    enlace: str
    imagen: str
    es_subasta: bool
    tiempo_restante: str
    vendedor: str
    procesador: str = ""
