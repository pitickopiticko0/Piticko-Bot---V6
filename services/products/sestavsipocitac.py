"""Načítání hotových PC sestav z sestavsipocitac.cz."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from services.products.base import Product


class SestavSiPocitacProvider:
    """Parser veřejného katalogu hotových sestav.

    Web je postavený v Next.js. Karty nejsou v prvotním HTML, ale data sestav
    jsou bezpečně vložená ve stránce v poli ``initialProducts``. Nečteme proto
    vykreslené prvky závislé na JavaScriptu, nýbrž tento zdroj dat.
    """

    BASE_URL = "https://sestavsipocitac.cz"
    CATEGORY_URL = f"{BASE_URL}/hotove-sestavy"

    async def fetch_products(self) -> list[Product]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PitickoBot/3.0)",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.7",
        }
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=httpx.Timeout(30.0)
        ) as client:
            response = await client.get(self.CATEGORY_URL)
            response.raise_for_status()
            first_page_products, page_count = self._parse_next_page(response.text)

            # SSP stránkuje katalog šesti kartami, ale jednotlivé stránky má
            # přímo na URL ``?page=2`` atd. První HTML odpověď proto obsahuje
            # jen první várku sestav, nikoli celý katalog.
            if first_page_products:
                products = {product.code: product for product in first_page_products}
                for page in range(2, page_count + 1):
                    page_response = await client.get(self.CATEGORY_URL, params={"page": page})
                    page_response.raise_for_status()
                    page_products, _ = self._parse_next_page(page_response.text)
                    products.update({product.code: product for product in page_products})
                return list(products.values())

        return self._parse_page(response.text)

    def _parse_page(self, html: str) -> list[Product]:
        products_from_next, _ = self._parse_next_page(html)
        if products_from_next:
            return products_from_next

        # Nouzová kompatibilita pro případ, že web jednou přejde zpět na
        # klasické HTML produktové karty.
        soup = BeautifulSoup(html, "html.parser")
        products: dict[str, Product] = {}

        for link in soup.select('a[href*="/hotove-sestavy/"]'):
            href = str(link.get("href") or "").strip()
            url = urljoin(self.CATEGORY_URL, href)
            parsed = urlparse(url)
            slug = parsed.path.rstrip("/").split("/")[-1]
            if not slug or slug == "hotove-sestavy" or parsed.netloc not in {"", "sestavsipocitac.cz"}:
                continue

            # Odstraní opakované odkazy (obrázek i nadpis obvykle vedou na detail).
            if slug in products:
                continue

            card = link.find_parent(["article", "li"]) or link.find_parent("div")
            name = " ".join(link.get_text(" ", strip=True).split())
            # Některé odkazy obsahují pouze „Detail“; skutečný název je v
            # nadpisu celé karty sestavy.
            if (not name or name.lower() in {"detail", "zobrazit detail"}) and isinstance(card, Tag):
                heading = card.select_one("h1, h2, h3, h4")
                name = heading.get_text(" ", strip=True) if isinstance(heading, Tag) else ""
            if not name or name.lower() in {"detail", "zobrazit detail"}:
                continue

            text = card.get_text(" ", strip=True) if isinstance(card, Tag) else name
            price_match = re.search(r"(\d[\d\s\u00a0]{2,})\s*Kč", text)
            price = f"{price_match.group(1).strip()} Kč" if price_match else "Cena neuvedena"
            availability = "Dostupnost ověř na webu"
            image_url = None
            if isinstance(card, Tag):
                image = card.select_one("img")
                if isinstance(image, Tag):
                    image_src = image.get("src") or image.get("data-src")
                    if image_src:
                        image_url = urljoin(self.CATEGORY_URL, str(image_src))

            products[slug] = Product(
                code=slug,
                name=name[:180],
                price=price,
                availability=availability,
                url=url,
                image_url=image_url,
            )

        return list(products.values())

    def _parse_next_page(self, html: str) -> tuple[list[Product], int]:
        """Vrátí sestavy a počet stránek z dat vložených Next.js do HTML."""
        soup = BeautifulSoup(html, "html.parser")

        for script in soup.find_all("script"):
            script_text = script.string or script.get_text()
            if "initialProducts" not in script_text:
                continue

            payload = self._decode_next_payload(script_text)
            raw_products = self._decode_next_value(payload, "initialProducts")

            if not isinstance(raw_products, list):
                continue

            products = [
                product
                for item in raw_products
                if isinstance(item, dict)
                if (product := self._product_from_next_data(item)) is not None
            ]
            if products:
                pagination = self._decode_next_value(payload, "initialPagination")
                page_count = (
                    pagination.get("pageCount", 1)
                    if isinstance(pagination, dict)
                    else 1
                )
                try:
                    return products, max(1, int(page_count))
                except (TypeError, ValueError):
                    return products, 1

        return [], 1

    @staticmethod
    def _decode_next_value(payload: str, field_name: str) -> object | None:
        """Načte jedno JSON pole vložené v Next.js payloadu."""
        marker = f'"{field_name}":'
        marker_start = payload.find(marker)
        if marker_start < 0:
            return None

        try:
            value, _ = json.JSONDecoder().raw_decode(payload[marker_start + len(marker) :])
        except json.JSONDecodeError:
            return None
        return value

    @staticmethod
    def _decode_next_payload(script_text: str) -> str:
        """Rozbalí řetězec předaný přes ``self.__next_f.push``.

        Next.js ukládá data jako JSON řetězec uvnitř JavaScriptového volání.
        Pokud se formát změní, vrací se původní text a parser jej jen přeskočí.
        """
        match = re.search(r"self\.__next_f\.push\((\[1,.*\])\)\s*$", script_text, re.DOTALL)
        if not match:
            return script_text

        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            return script_text

        return value[1] if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str) else script_text

    def _product_from_next_data(self, item: dict[str, object]) -> Product | None:
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "").strip()
        if not slug or not name:
            return None

        price_value = item.get("priceWithVat")
        try:
            price = f"{int(float(str(price_value))):,}".replace(",", "\u00a0") + " Kč"
        except (TypeError, ValueError):
            price = "Cena neuvedena"

        availability_map = {
            "in_stock": "Skladem",
            "out_of_stock": "Není skladem",
            "preorder": "Předobjednávka",
        }
        availability_key = str(item.get("availabilityStatus") or "").strip().lower()
        availability = availability_map.get(availability_key, "Dostupnost ověř na webu")

        image_url = str(item.get("mainImageUrl") or "").strip() or None
        return Product(
            code=slug,
            name=name[:180],
            price=price,
            availability=availability,
            url=f"{self.CATEGORY_URL}/{slug}",
            image_url=image_url,
        )
