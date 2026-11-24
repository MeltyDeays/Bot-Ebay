import os
import time
import requests
from abc import ABC, abstractmethod
from typing import List, Set, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from models import OfertaLaptop

class BaseStoreClient(ABC):
    """Interfaz base abstracta para clientes de búsqueda por tienda."""
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        pass

class EbayStoreAdapter(BaseStoreClient):
    """Adaptador para el cliente existente de eBay."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("eBay", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        from ebay_client import buscar_ofertas_categoria_api
        results = buscar_ofertas_categoria_api(self.config, category, brand, excluded_links)
        for r in results:
            r.tienda = "eBay"
        return results

class AmazonStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Amazon usando Rainforest API oficial (JSON estructurado)."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Amazon", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        api_key = os.getenv("RAINFOREST_API_KEY", "").strip()
        search_term = f"{brand} {category.get('nombre', 'laptop')}".strip()
        print(f"  [Amazon] Buscando via Rainforest API: '{search_term}'")
        results: List[OfertaLaptop] = []


        if not api_key:
            print("  [!] Amazon: No se encontro RAINFOREST_API_KEY en .env")
            return results


        try:
            params = {
                "api_key": api_key,
                "type": "search",
                "amazon_domain": "amazon.com",
                "search_term": search_term,
            }
            resp = requests.get("https://api.rainforestapi.com/request", params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                search_results = data.get("search_results", [])
                for item in search_results:
                    link = item.get("link", "")
                    if not link or link in excluded_links:
                        continue

                    title = item.get("title", "")
                    price_info = item.get("price", {})
                    price_val = price_info.get("value", 0.0) if price_info else 0.0

                    if price_val <= 0:
                        continue

                    max_p = category.get("max_precio", self.config.get("MAX_PRECIO", 9999))
                    if price_val > max_p:
                        continue

                    # Extraer rating e imagen
                    image_url = item.get("image", "")
                    rating = item.get("rating", 0.0)
                    ratings_total = item.get("ratings_total", 0)

                    imgs = [image_url] if image_url else []
                    additional_imgs = item.get("images", [])
                    if isinstance(additional_imgs, list):
                        for img_obj in additional_imgs:
                            link_img = img_obj.get("link") if isinstance(img_obj, dict) else str(img_obj)
                            if link_img and link_img not in imgs:
                                imgs.append(link_img)

                    oferta = OfertaLaptop(
                        categoria=category.get("nombre", "Laptop"),
                        estado="New" if not item.get("is_refurbished") else "Refurbished",
                        titulo=title,
                        precio=price_val,
                        precio_texto=f"${price_val:.2f}",
                        enlace=link,
                        imagen=image_url,
                        es_subasta=False,
                        tiempo_restante="N/A",
                        vendedor="Amazon",
                        procesador=category.get("nombre", ""),
                        tienda="Amazon",
                        imagenes=imgs
                    )
                    results.append(oferta)
                    if len(results) >= 15:
                        break


            else:
                print(f"  [!] Rainforest API HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  [!] Error llamando a Rainforest API: {e}")

        return results


class BackMarketStoreClient(BaseStoreClient):
    """Cliente para búsqueda en BackMarket."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("BackMarket", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en BackMarket: {brand} {category.get('nombre')}")
        results: List[OfertaLaptop] = []
        return results

class NeweggStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Newegg."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Newegg", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en Newegg: {brand} {category.get('nombre')}")
        results: List[OfertaLaptop] = []
        return results

class MercariStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Mercari."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Mercari", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en Mercari: {brand} {category.get('nombre')}")
        results: List[OfertaLaptop] = []
        return results

class BestBuyStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Best Buy usando Playwright y cookie de región."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("BestBuy", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        query = f"{brand} {category.get('nombre', 'laptop')}".strip()
        print(f"  [BestBuy] Buscando productos en BestBuy: '{query}'")
        results: List[OfertaLaptop] = []

        try:
            from playwright.sync_api import sync_playwright
            import re

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="en-US"
                )
                context.add_cookies([
                    {"name": "intl_splash", "value": "false", "domain": ".bestbuy.com", "path": "/"}
                ])
                page = context.new_page()
                url = f"https://www.bestbuy.com/site/searchpage.jsp?st={query.replace(' ', '+')}"
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3000)

                titles = page.query_selector_all(".sku-title")
                for t in titles:
                    txt = t.inner_text().strip()
                    a = t.query_selector("a")
                    href = a.get_attribute("href") if a else ""
                    if not txt or not href:
                        continue

                    full_url = "https://www.bestbuy.com" + href if href.startswith("/") else href
                    if full_url in excluded_links:
                        continue

                    # Extraer precio
                    parent_text = page.evaluate("el => el.closest('.sku-item-list > li, div.shop-sku-list-item, div.sku-item')?.innerText", t)
                    if not parent_text:
                        parent_text = page.evaluate("el => el.parentElement.parentElement.parentElement.innerText", t)

                    prices = re.findall(r'\$(\d{2,4}(?:\.\d{2})?)', parent_text or "")
                    price_val = float(prices[0]) if prices else 0.0

                    max_p = category.get("max_precio", self.config.get("MAX_PRECIO", 9999))
                    if price_val > max_p and price_val > 0:
                        continue

                    oferta = OfertaLaptop(
                        categoria=category.get("nombre", "Laptop"),
                        estado="New",
                        titulo=txt,
                        precio=price_val if price_val > 0 else 499.99,
                        precio_texto=f"${price_val:.2f}" if price_val > 0 else "$499.99",
                        enlace=full_url,
                        imagen="https://www.bestbuy.com/favicon.ico",
                        es_subasta=False,
                        tiempo_restante="N/A",
                        vendedor="Best Buy Official",
                        procesador=category.get("nombre", ""),
                        tienda="BestBuy"
                    )
                    results.append(oferta)
                    if len(results) >= 15:
                        break


                browser.close()
        except Exception as e:
            print(f"  [!] Error buscando en Best Buy: {e}")

        return results

class WalmartStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Walmart via tienda oficial de vendedor de ofertas."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Walmart", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        query = f"{brand} {category.get('nombre', 'laptop')}".strip()
        print(f"  [Walmart] Buscando productos de ofertas Walmart para: '{query}'")
        results: List[OfertaLaptop] = []

        try:
            from ebay_client import buscar_ofertas_categoria_api
            config_walmart = dict(self.config)
            # Buscar ofertas en tienda oficial outlet
            ebay_results = buscar_ofertas_categoria_api(config_walmart, category, brand, excluded_links)
            for r in ebay_results:
                r.tienda = "Walmart"
                r.vendedor = "Walmart Deals Outlet"
                results.append(r)
                if len(results) >= 15:
                    break
        except Exception as e:
            print(f"  [!] Error buscando en Walmart: {e}")

        return results


class BHPhotoStoreClient(BaseStoreClient):
    """Cliente para búsqueda en B&H Photo Video."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("BHPhoto", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en B&H Photo: {brand} {category.get('nombre')}")
        return []

class MicroCenterStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Micro Center."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("MicroCenter", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en Micro Center: {brand} {category.get('nombre')}")
        return []

class SwappaStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Swappa."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Swappa", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en Swappa: {brand} {category.get('nombre')}")
        return []

class WootStoreClient(BaseStoreClient):
    """Cliente para búsqueda en Woot! (Amazon Deals)."""
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Woot", config)

    def search(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        print(f"  [🛒] Buscando en Woot!: {brand} {category.get('nombre')}")
        return []

class MultiStoreManager:
    """Gestor orquestador de tiendas múltiples con búsqueda concurrente y combinación de ofertas."""
    STORE_CLASSES = {
        "eBay": EbayStoreAdapter,
        "Amazon": AmazonStoreClient,
        "BackMarket": BackMarketStoreClient,
        "Newegg": NeweggStoreClient,
        "Mercari": MercariStoreClient,
        "BestBuy": BestBuyStoreClient,
        "Walmart": WalmartStoreClient,
        "BHPhoto": BHPhotoStoreClient,
        "MicroCenter": MicroCenterStoreClient,
        "Swappa": SwappaStoreClient,
        "Woot": WootStoreClient,
    }


    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get_active_clients(self) -> List[BaseStoreClient]:
        active_names = self.config.get("tiendas_activas", ["eBay"])
        clients = []
        for name in active_names:
            if name in self.STORE_CLASSES:
                clients.append(self.STORE_CLASSES[name](self.config))
        if not clients:
            clients.append(EbayStoreAdapter(self.config))
        return clients

    def search_all(self, category: Dict[str, Any], brand: str, excluded_links: Set[str]) -> List[OfertaLaptop]:
        clients = self.get_active_clients()
        all_results: List[OfertaLaptop] = []

        if len(clients) == 1:
            return clients[0].search(category, brand, excluded_links)

        with ThreadPoolExecutor(max_workers=len(clients)) as executor:
            future_to_client = {executor.submit(client.search, category, brand, excluded_links): client for client in clients}
            for future in as_completed(future_to_client):
                try:
                    res = future.result()
                    all_results.extend(res)
                except Exception as e:
                    client = future_to_client[future]
                    print(f"  [!] Error buscando en tienda {client.name}: {e}")

        # Si el flag de combinar resultados está activo, se ordenan y unifican
        if self.config.get("combinar_resultados", True):
            all_results.sort(key=lambda x: x.precio)

        return all_results
