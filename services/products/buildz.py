"""Načítání hotových počítačových sestav z Buildz.gg."""

from __future__ import annotations

from typing import Any

import httpx

from services.products.base import Product


class BuildzProvider:
    """Parser veřejného Buildz.gg API pro český katalog počítačů."""

    BASE_URL = "https://buildz.gg"
    API_URL = "https://backend.buildz.gg/api/computers/public"
    PER_PAGE = 30
    MAX_PAGES = 100

    async def fetch_products(self) -> list[Product]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PitickoBot/3.0)",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.7",
        }
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as client:
            first_payload = await self._fetch_page(client, 1)
            first_page = self._products_from_payload(first_payload)
            if not first_page:
                raise RuntimeError("Buildz.gg API nevrátilo žádné sestavy.")

            try:
                last_page = int(first_payload["meta"]["last_page"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("Buildz.gg API nevrátilo platné stránkování.") from exc

            if not 1 <= last_page <= self.MAX_PAGES:
                raise RuntimeError(
                    "Buildz.gg katalog má nečekaný počet stránek; "
                    "nebudu používat neúplný seznam."
                )

            products = {product.code: product for product in first_page}
            for page in range(2, last_page + 1):
                page_products = self._products_from_payload(
                    await self._fetch_page(client, page)
                )
                if not page_products:
                    raise RuntimeError(
                        f"Buildz.gg API nevrátilo sestavy na stránce {page}."
                    )
                products.update({product.code: product for product in page_products})

        return list(products.values())

    async def _fetch_page(
        self, client: httpx.AsyncClient, page: int
    ) -> dict[str, Any]:
        response = await client.get(
            self.API_URL,
            params={
                "locale": "cs",
                "page": page,
                "per_page": self.PER_PAGE,
                "sort": "performance",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Buildz.gg API vrátilo neplatná data.")
        return payload

    def _products_from_payload(self, payload: dict[str, Any]) -> list[Product]:
        raw_products = payload.get("data")
        if not isinstance(raw_products, list):
            raise RuntimeError("Buildz.gg API nevrátilo seznam sestav.")
        return [
            product
            for item in raw_products
            if isinstance(item, dict)
            if (product := self._product_from_data(item)) is not None
        ]

    def _product_from_data(self, item: dict[str, Any]) -> Product | None:
        identifier = item.get("id")
        name = str(item.get("name") or "").strip()
        if identifier is None or not name:
            return None

        code = str(identifier).strip()
        if not code.isdigit():
            return None

        price = str(
            item.get("price_display_formatted")
            or item.get("price_formatted")
            or "Cena neuvedena"
        ).strip()
        availability_data = item.get("availability")
        availability = self._availability(availability_data)
        image_url = str(item.get("display_image") or "").strip() or None

        return Product(
            code=code,
            name=name[:180],
            price=price,
            availability=availability,
            url=f"{self.BASE_URL}/cs/pocitace/{code}",
            image_url=image_url,
        )

    @staticmethod
    def _availability(value: Any) -> str:
        if not isinstance(value, dict):
            return "Dostupnost ověř na webu"

        status = str(value.get("status") or "").lower()
        label = str(value.get("label") or "").strip()
        status_labels = {
            "in_stock": "Skladem",
            "out_of_stock": "Není skladem",
            "preorder": "Předobjednávka",
        }
        return status_labels.get(status, label or "Dostupnost ověř na webu")
