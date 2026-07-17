from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from services.products.base import Product


log = logging.getLogger(__name__)


class MakeJPCProvider:
    BASE_URL = "https://www.makejpc.cz"
    CATEGORY_URL = f"{BASE_URL}/pocitace/"

    def __init__(self, max_pages: int = 5):
        self.max_pages = max(1, max_pages)

    async def fetch_products(self) -> list[Product]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; PitickoBot/2.0; "
                "+https://github.com/pitickopiticko0/Piticko-Bot---V6)"
            ),
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.7",
        }

        products: dict[str, Product] = {}

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as client:
            for page in range(1, self.max_pages + 1):
                url = self.CATEGORY_URL if page == 1 else f"{self.CATEGORY_URL}strana-{page}/"
                response = await client.get(url)

                # Shoptet u neexistující další stránky někdy vrátí 404.
                if response.status_code == 404 and page > 1:
                    break

                response.raise_for_status()
                page_products = self._parse_page(response.text)

                if not page_products:
                    if page == 1:
                        log.warning("MakejPC parser nenašel na první stránce žádné produkty.")
                    break

                added = 0
                for product in page_products:
                    if product.code not in products:
                        products[product.code] = product
                        added += 1

                # Pokud další stránka nepřinesla nic nového, nemá smysl pokračovat.
                if page > 1 and added == 0:
                    break

        return list(products.values())

    def _parse_page(self, html: str) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")

        # Výpis produktů Shoptetu bývá v #products. Záložní selektory drží
        # parser funkční i při menších změnách šablony.
        containers = soup.select(
            "#products .product, "
            ".products-block .product, "
            ".products .product"
        )

        if not containers:
            containers = soup.select(".product")

        products: list[Product] = []

        for item in containers:
            product = self._parse_card(item)
            if product is not None:
                products.append(product)

        return products

    def _parse_card(self, item: Tag) -> Product | None:
        link = (
            item.select_one("a.name")
            or item.select_one("a.p-name")
            or item.select_one(".name a")
            or item.select_one("a[href]")
        )
        if not isinstance(link, Tag):
            return None

        href = (link.get("href") or "").strip()
        name = link.get_text(" ", strip=True)

        if not href or not name:
            return None

        product_url = urljoin(self.CATEGORY_URL, href)

        # Přeskočí odkazy, které nejsou detail produktu.
        parsed = urlparse(product_url)
        if parsed.netloc and "makejpc.cz" not in parsed.netloc:
            return None

        code = self._extract_code(item, product_url)
        if not code:
            return None

        price = self._text_from(
            item,
            ".price-final, .price-final-holder, .price, .p-final-price-wrapper",
            "Cena neuvedena",
        )
        availability = self._text_from(
            item,
            ".availability, .availability-amount, .p-availability, .availability-label",
            "Dostupnost neuvedena",
        )
        image_url = self._extract_image(item)

        return Product(
            code=code,
            name=name,
            price=price,
            availability=availability,
            url=product_url,
            image_url=image_url,
        )

    def _extract_code(self, item: Tag, product_url: str) -> str | None:
        for attr in (
            "data-micro-product-id",
            "data-product-id",
            "data-micro-product-code",
            "data-product-code",
        ):
            value = item.get(attr)
            if value:
                return str(value).strip()

        code_node = item.select_one(
            ".product-code, .p-code, [data-micro-product-id], [data-product-id]"
        )
        if isinstance(code_node, Tag):
            for attr in (
                "data-micro-product-id",
                "data-product-id",
                "data-micro-product-code",
                "data-product-code",
            ):
                value = code_node.get(attr)
                if value:
                    return str(value).strip()

            text = code_node.get_text(" ", strip=True)
            match = re.search(r"(?:Kód\s*:?)?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
            if match:
                return match.group(1)

        # Poslední možnost: kód z textu celé produktové karty.
        text = item.get_text(" ", strip=True)
        match = re.search(r"Kód\s*:\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Stabilní fallback podle URL detailu.
        slug = urlparse(product_url).path.rstrip("/").split("/")[-1]
        return slug or None

    def _extract_image(self, item: Tag) -> str | None:
        image = item.select_one("img")
        if not isinstance(image, Tag):
            return None

        src = (
            image.get("data-src")
            or image.get("data-lazy-src")
            or image.get("data-original")
            or image.get("src")
        )
        if not src:
            return None

        return urljoin(self.CATEGORY_URL, str(src).strip())

    @staticmethod
    def _text_from(item: Tag, selector: str, fallback: str) -> str:
        node = item.select_one(selector)
        if not isinstance(node, Tag):
            return fallback

        text = " ".join(node.get_text(" ", strip=True).split())
        return text or fallback
