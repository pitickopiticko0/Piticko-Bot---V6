"""Veřejné zdroje her zdarma a slev z ověřených obchodů."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


USER_AGENT = "PitickoBot/6.0 (Discord game notifications)"


class GameDealsAPIError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GameOffer:
    source: str
    offer_id: str
    title: str
    url: str
    image_url: str | None
    store: str
    description: str
    sale_price: str | None = None
    normal_price: str | None = None
    discount: int | None = None
    ends_at: str | None = None


class GameDealsAPI:
    GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways"
    CHEAPSHARK_URL = "https://www.cheapshark.com/api/1.0"

    async def _json(self, url: str, *, params: dict | None = None):
        timeout = aiohttp.ClientTimeout(total=25)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 201:
                        return []
                    if response.status != 200:
                        raise GameDealsAPIError(
                            f"Zdroj {url} vrátil HTTP {response.status}."
                        )
                    return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise GameDealsAPIError(f"Načtení herních nabídek selhalo: {exc}") from exc

    async def fetch_free_games(self) -> list[GameOffer]:
        data = await self._json(
            self.GAMERPOWER_URL,
            params={"type": "game", "sort-by": "date"},
        )
        if not isinstance(data, list):
            raise GameDealsAPIError("GamerPower vrátil neplatná data.")

        offers: list[GameOffer] = []
        for item in data:
            if not isinstance(item, dict) or item.get("status") == "Expired":
                continue
            platforms = str(item.get("platforms") or "PC")
            if not any(
                name in platforms.lower()
                for name in ("pc", "steam", "epic", "gog", "itch")
            ):
                continue
            offer_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            url = str(
                item.get("open_giveaway_url")
                or item.get("gamerpower_url")
                or ""
            ).strip()
            if not offer_id or not title or not url:
                continue
            description = str(item.get("description") or "Hra je dočasně zdarma.").strip()
            offers.append(
                GameOffer(
                    source="gamerpower",
                    offer_id=offer_id,
                    title=title,
                    url=url,
                    image_url=str(item.get("image") or item.get("thumbnail") or "") or None,
                    store=platforms,
                    description=description[:700],
                    normal_price=str(item.get("worth") or "") or None,
                    sale_price="Zdarma",
                    discount=100,
                    ends_at=str(item.get("end_date") or "") or None,
                )
            )
        return offers

    async def fetch_discounted_games(self) -> list[GameOffer]:
        stores_data = await self._json(f"{self.CHEAPSHARK_URL}/stores")
        stores = {
            str(row.get("storeID")): str(row.get("storeName") or "Obchod")
            for row in stores_data
            if isinstance(row, dict) and row.get("isActive")
        }
        data = await self._json(
            f"{self.CHEAPSHARK_URL}/deals",
            params={
                "pageNumber": 0,
                "pageSize": 60,
                "sortBy": "Recent",
                "desc": 1,
                "onSale": 1,
                "lowerPrice": 0.01,
            },
        )
        if not isinstance(data, list):
            raise GameDealsAPIError("CheapShark vrátil neplatná data.")

        offers: list[GameOffer] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            offer_id = str(item.get("dealID") or "").strip()
            title = str(item.get("title") or "").strip()
            try:
                discount = round(float(item.get("savings") or 0))
                sale_price = float(item.get("salePrice") or 0)
                normal_price = float(item.get("normalPrice") or 0)
            except (TypeError, ValueError):
                continue
            if not offer_id or not title or discount <= 0:
                continue
            offers.append(
                GameOffer(
                    source="cheapshark",
                    offer_id=offer_id,
                    title=title,
                    url=f"https://www.cheapshark.com/redirect?dealID={quote(offer_id, safe='')}",
                    image_url=str(item.get("thumb") or "") or None,
                    store=stores.get(str(item.get("storeID")), "Digitální obchod"),
                    description="Aktuální sleva z nabídky ověřeného digitálního obchodu.",
                    sale_price=f"${sale_price:.2f}",
                    normal_price=f"${normal_price:.2f}",
                    discount=discount,
                )
            )
        return offers


game_deals_api = GameDealsAPI()
