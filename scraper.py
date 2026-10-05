import os
import re
import time
from typing import List, Dict, Any, Callable
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Conexión con Supabase
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Conectado a Supabase correctamente.")
    except Exception as e:
        print(f"Error conectando a Supabase: {e}")
else:
    print("Variables de Supabase no detectadas en .env. Se omitira la sincronizacion remota.")

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es;q=0.9",
})

# ─────────────────────────────────────────────────────────────
# UTILIDADES DE LIMPIEZA
# ─────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convierte un titulo en slug: 'Silla Gamer X' -> 'silla-gamer-x'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def clean_price(price_str: str) -> int:
    """Extrae unicamente digitos de la cadena de texto."""
    digits = re.sub(r"[^\d]", "", price_str)
    return int(digits) if digits else 0


# ─────────────────────────────────────────────────────────────
# EXTRACTORES POR TIENDA
# ─────────────────────────────────────────────────────────────

def extract_spdigital(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extractor para SP Digital basado en Fractal DS."""
    items = []
    cards = soup.select('div[data-fractalds*="productcard"]')

    for card in cards:
        nombre_elem = card.select_one(".Fractal-ProductCard--productDescriptionTextContainer a")
        if not nombre_elem:
            continue
        nombre = nombre_elem.get_text(strip=True)

        brand_elem = card.select_one(".Fractal-ProductCard--productDetailsContainer span a")
        marca = brand_elem.get_text(strip=True) if brand_elem else "Generico"

        precio_elem = card.select_one(".Fractal-ProductCard--priceVariantContainer span.Fractal-Price--price")
        precio_raw = precio_elem.get_text(strip=True) if precio_elem else "0"
        precio = clean_price(precio_raw)

        img_elem = card.select_one(".Fractal-ProductCard__image--container img")
        img_url = ""
        if img_elem:
            raw_src = img_elem.get("src") or img_elem.get("data-src") or ""
            img_url = f"https:{raw_src}" if raw_src.startswith("//") else raw_src

        if nombre and precio > 0:
            items.append({
                "name": nombre,
                "brand": marca,
                "price": precio,
                "image_url": img_url,
            })

    return items


def extract_falabella(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extractor para Falabella."""
    items = []
    cards = soup.select("div.pod-item, div[class*='search-results--product']")

    for card in cards:
        name_elem = card.select_one("b[class*='pod-subTitle'], span[class*='name']")
        price_elem = card.select_one("li[class*='prices-0'], span[class*='copy12']")
        img_elem = card.select_one("img")

        if not name_elem or not price_elem:
            continue

        name = name_elem.get_text(strip=True)
        price = clean_price(price_elem.get_text(strip=True))
        image_url = img_elem.get("src", "") if img_elem else ""

        if name and price > 0:
            items.append({
                "name": name,
                "brand": "Generico",
                "price": price,
                "image_url": image_url,
            })

    return items


SITE_EXTRACTORS: Dict[str, Callable[[BeautifulSoup], List[Dict[str, Any]]]] = {
    "spdigital.cl": extract_spdigital,
    "falabella.com": extract_falabella,
}


# ─────────────────────────────────────────────────────────────
# MOTOR PRINCIPAL DE DESCARGA POR LIMITE
# ─────────────────────────────────────────────────────────────

def scrape_url_target(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_url = target["url"]
    category_id = target["category_id"]
    category_name = target.get("name", "general")
    limit = target.get("limit", 10)

    domain = urlparse(base_url).netloc.replace("www.", "")
    extractor = None
    for key, func in SITE_EXTRACTORS.items():
        if key in domain:
            extractor = func
            break

    if not extractor:
        print(f"Aviso: No hay un extractor definido para el dominio: {domain}")
        return []

    collected_products: List[Dict[str, Any]] = []
    current_page = 1

    print(f"\nIniciando extraccion de {limit} productos para '{category_name}' desde {domain}...")

    while len(collected_products) < limit:
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}page={current_page}" if current_page > 1 else base_url

        print(f"  Procesando pagina {current_page} ({len(collected_products)}/{limit} productos)...")
        try:
            res = session.get(url, timeout=12)
            if res.status_code != 200:
                print(f"  Fin de paginas o error HTTP {res.status_code}.")
                break

            soup = BeautifulSoup(res.text, "html.parser")
            raw_items = extractor(soup)

            if not raw_items:
                print("  No se encontraron mas productos en esta seccion.")
                break

            for item in raw_items:
                slug = slugify(item["name"])

                if any(p["slug"] == slug for p in collected_products):
                    continue

                collected_products.append({
                    "name": item["name"],
                    "brand": item["brand"],
                    "price": item["price"],
                    "stock": 10,
                    "image_url": item["image_url"],
                    "slug": slug,
                    "category_id": category_id,
                    "views": 0,
                    "specifications": "{}",
                })

                if len(collected_products) >= limit:
                    break

            current_page += 1
            time.sleep(1)

        except Exception as e:
            print(f"  Error en pagina {current_page}: {e}")
            break

    print(f"  Completado: {len(collected_products)} productos recopilados de '{category_name}'.")
    return collected_products


def sync_with_supabase(products: List[Dict[str, Any]], batch_size: int = 50):
    """Guarda o actualiza los datos extraidos en Supabase."""
    if not supabase:
        print("Cliente de Supabase no configurado. Se omite la subida.")
        return

    if not products:
        return

    print(f"\nSubiendo {len(products)} registros a la tabla 'product' en Supabase...")
    for i in range(0, len(products), batch_size):
        batch = products[i : i + batch_size]
        try:
            supabase.table("product").upsert(batch, on_conflict="slug").execute()
            print(f"  Lote {i // batch_size + 1} insertado con exito ({len(batch)} items).")
        except Exception as err:
            print(f"  Error al insertar lote: {err}")


# ─────────────────────────────────────────────────────────────
# CONFIGURACION DE OBJETIVOS
# ─────────────────────────────────────────────────────────────

TARGETS = [
    {
        "name": "Sillas Gamer",
        "url": "https://www.spdigital.cl/categories/gaming-y-streaming-sillas-y-escritorios-silla-gamer-profesional/",
        "category_id": "c1bdcdd9-5540-44e2-b9bc-cdd8c524123b",
        "limit": 5,
    },
    {
        "name": "Teclados Gamer",
        "url": "https://www.spdigital.cl/categories/gaming-y-streaming-perifericos-gamer-teclado-gamer/",
        "category_id": "11e67898-5dc2-46c3-81ec-d72ecef071ff",
        "limit": 5,
    }
]

def main():
    all_results = []

    for target in TARGETS:
        products = scrape_url_target(target)
        all_results.extend(products)

    if all_results:
        # Respaldo opcional en CSV
        df = pd.DataFrame(all_results)
        df.to_csv("productos_catalogo.csv", index=False, encoding="utf-8")
        print("\nArchivo local 'productos_catalogo.csv' actualizado.")

        # Sincronizacion directa con Supabase
        sync_with_supabase(all_results)
        print("\nProceso finalizado con exito.")
    else:
        print("\nNo se encontraron productos.")


if __name__ == "__main__":
    main()