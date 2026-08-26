"""Načítání hotových PC sestav z sestavsipocitac.cz."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from services.products.base import Product


class SestavSiPocitacProvider:
    """Parser veřejného katalogu hotových sestav.

    Web není klasický e-shop se stabilními produktovými kartami. Parser proto
    vychází z odkazů na detaily a cenu hledá jen v jejich nejbližší kartě.
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
        return self._parse_page(response.text)

    def _parse_page(self, html: str) -> list[Product]:
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
