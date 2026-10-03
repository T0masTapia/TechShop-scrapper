import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

def slugify(text: str) -> str:
    """Convierte un título en slug: 'Silla Gamer X' -> 'silla-gamer-x'"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text

def scrape_spdigital(url: str):
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    }

    print(f"Descargando datos de: {url}...")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error al consultar la página: Código {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []

    # Selector real de las tarjetas en SP Digital
    items = soup.select('div[data-fractalds*="productcard"]')
    print(f"Tarjetas detectadas: {len(items)}")

    for item in items:
        # 1. Título del producto
        nombre_elem = item.select_one('.Fractal-ProductCard--productDescriptionTextContainer a')
        if not nombre_elem:
            continue
        nombre = nombre_elem.get_text(strip=True)

        # 2. Marca (Cougar, Asus, etc.)
        brand_elem = item.select_one('.Fractal-ProductCard--productDetailsContainer span a')
        marca = brand_elem.get_text(strip=True) if brand_elem else "Genérico"

        # 3. Precio (primer valor de transferencia o precio con descuento)
        precio_elem = item.select_one('.Fractal-ProductCard--priceVariantContainer span.Fractal-Price--price')
        precio_raw = precio_elem.get_text(strip=True) if precio_elem else "0"
        precio_limpio = int(re.sub(r'[^\d]', '', precio_raw) or 0)

        # 4. Imagen
        img_elem = item.select_one('.Fractal-ProductCard__image--container img')
        img_url = ""
        if img_elem:
            raw_src = img_elem.get('src') or img_elem.get('data-src') or ""
            # Si la URL viene relativa tipo '//media.spdigital.cl', le agregamos 'https:'
            if raw_src.startswith("//"):
                img_url = f"https:{raw_src}"
            else:
                img_url = raw_src

        # 5. Enlace original del producto
        link_rel = nombre_elem.get('href', '')
        link_producto = f"https://www.spdigital.cl{link_rel}" if link_rel.startswith('/') else link_rel

        ID_CATEGORIA_SILLAS = "c1bdcdd9-5540-44e2-b9bc-cdd8c524123b"
        products.append({
            "name": nombre,
            "brand": marca,
            "price": precio_limpio,
            "stock": 10,
            "image_url": img_url,
            "slug": slugify(nombre),
            "category_id": ID_CATEGORIA_SILLAS,
            "views": 0,
            "specifications": "{}"
        })

    return products

def main():
    url_objetivo = "https://www.spdigital.cl/categories/gaming-y-streaming-sillas-y-escritorios-silla-gamer-profesional/"
    productos = scrape_spdigital(url_objetivo)

    if productos:
        df = pd.DataFrame(productos)
        
        excel_filename = "productos_catalogo.xlsx"
        df.to_excel(excel_filename, index=False)
        print(f"Se guardaron {len(productos)} productos en '{excel_filename}'.")

        csv_filename = "productos_catalogo.csv"
        df.to_csv(csv_filename, index=False, encoding='utf-8')
        print(f"Archivo CSV generado en '{csv_filename}'.")
    else:
        print("No se encontraron productos.")

if __name__ == "__main__":
    main()