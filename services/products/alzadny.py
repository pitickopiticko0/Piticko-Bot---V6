from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag


log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AlzaDeal:
    code: str
    name: str
    url: str
    coupon: str
    discount_percent: int
    price: str
    original_price: str
    availability: str
    category: str
    image_url: str | None = None


@dataclass(slots=True, frozen=True)
class AlzaSourceDiagnostic:
    category: str
    status_code: int | None
    final_url: str
    response_bytes: int
    cards_found: int
    coupons_found: int
    deals_accepted: int
    error: str | None = None


class AlzaDaysProvider:
    BASE_URL = "https://www.alza.cz"
    SOURCES = (
        (
            "Počítače a gaming",
            f"{BASE_URL}/pocitace/alza-dny/18852653-e40.htm",
            False,
        ),
        (
            "Servisní nářadí",
            f"{BASE_URL}/hobby/naradi/alza-dny/18858962-e40.htm",
            True,
        ),
        (
            "Čištění elektroniky",
            f"{BASE_URL}/maxi/cistici-prostredky/alza-dny/18855774-e40.htm",
            True,
        ),
    )
    REPAIR_KEYWORDS = (
        "šroubovák",
        "sada bitů",
        "precizní bity",
        "páječ",
        "pájecí",
        "multimetr",
        "měřicí přístroj",
        "zkoušečka",
        "pinzeta",
        "odizol",
        "horkovzduš",
        "odsávačka cínu",
        "antistat",
        "esd",
        "ifixit",
        "oprava elektroniky",
        "servis elektroniky",
        "stlačený vzduch",
        "čištění elektroniky",
        "čistič elektroniky",
        "čistící ubrousky",
        "izopropyl",
        "isopropyl",
        "displej",
        "monitor",
        "notebook",
        "klávesnic",
    )

    def __init__(self, min_discount: int = 15):
        self.min_discount = max(5, min(int(min_discount), 90))
        self.last_diagnostics: list[AlzaSourceDiagnostic] = []

    async def fetch_deals(self) -> list[AlzaDeal]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml",
        }
        deals: dict[str, AlzaDeal] = {}
        self.last_diagnostics = []

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(15.0),
        ) as client:
            for category, url, require_keyword in self.SOURCES:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    log.warning(
                        "AlzaDny zdroj %s se nepodařilo načíst: %s",
                        category,
                        error,
                    )
                    self.last_diagnostics.append(
                        AlzaSourceDiagnostic(
                            category=category,
                            status_code=getattr(
                                getattr(error, "response", None),
                                "status_code",
                                None,
                            ),
                            final_url=str(getattr(error, "request", None).url)
                            if getattr(error, "request", None)
                            else url,
                            response_bytes=0,
                            cards_found=0,
                            coupons_found=0,
                            deals_accepted=0,
                            error=type(error).__name__,
                        )
                    )
                    continue

                parsed_deals, cards_found, coupons_found = self._parse_page_with_stats(
                    response.text,
                    category=category,
                    source_url=str(response.url),
                    require_keyword=require_keyword,
                )
                self.last_diagnostics.append(
                    AlzaSourceDiagnostic(
                        category=category,
                        status_code=response.status_code,
                        final_url=str(response.url),
                        response_bytes=len(response.content),
                        cards_found=cards_found,
                        coupons_found=coupons_found,
                        deals_accepted=len(parsed_deals),
                    )
                )
                for deal in parsed_deals:
                    current = deals.get(deal.code)
                    if current is None or deal.discount_percent > current.discount_percent:
                        deals[deal.code] = deal

        return sorted(
            deals.values(),
            key=lambda deal: (-deal.discount_percent, deal.name.casefold()),
        )

    def _parse_page(
        self,
        html: str,
        *,
        category: str,
        source_url: str,
        require_keyword: bool,
    ) -> list[AlzaDeal]:
        deals, _, _ = self._parse_page_with_stats(
            html,
            category=category,
            source_url=source_url,
            require_keyword=require_keyword,
        )
        return deals

    def _parse_page_with_stats(
        self,
        html: str,
        *,
        category: str,
        source_url: str,
        require_keyword: bool,
    ) -> tuple[list[AlzaDeal], int, int]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(
            ".box.browsingitem, .browsingitem, "
            "[data-product-id].box, [data-item-id].box"
        )
        deals = []
        coupons_found = 0

        for card in cards:
            if re.search(r"\bALZADNY\d{1,2}\b", card.get_text(" ", strip=True), re.I):
                coupons_found += 1
            deal = self._parse_card(
                card,
                category=category,
                source_url=source_url,
                require_keyword=require_keyword,
            )
            if deal is not None:
                deals.append(deal)

        return deals, len(cards), coupons_found

    def _parse_card(
        self,
        card: Tag,
        *,
        category: str,
        source_url: str,
        require_keyword: bool,
    ) -> AlzaDeal | None:
        card_text = " ".join(card.get_text(" ", strip=True).split())
        coupon_match = re.search(r"\bALZADNY(\d{1,2})\b", card_text, re.IGNORECASE)
        if coupon_match is None:
            return None

        discount = int(coupon_match.group(1))
        if discount < self.min_discount:
            return None

        link = (
            card.select_one("a.name.browsinglink[href]")
            or card.select_one("a.name[href]")
            or card.select_one("a.browsinglink[href]")
            or card.select_one("h2 a[href], h3 a[href]")
        )
        if not isinstance(link, Tag):
            return None

        name = " ".join(link.get_text(" ", strip=True).split())
        href = str(link.get("href") or "").strip()
        if not name or not href:
            return None

        product_url = urljoin(source_url, href)
        hostname = (urlparse(product_url).hostname or "").casefold()
        if hostname != "alza.cz" and not hostname.endswith(".alza.cz"):
            return None

        if require_keyword:
            searchable = f"{name} {card_text}".casefold()
            if not any(keyword in searchable for keyword in self.REPAIR_KEYWORDS):
                return None

        code = self._extract_code(card, card_text, product_url)
        if not code:
            return None

        price, original_price = self._extract_prices(card_text, coupon_match.end())
        availability_match = re.search(
            r"(Skladem(?:\s*>\s*\d+\s*ks)?(?:\s*u dodavatele)?|"
            r"Na objednávku|Momentálně nedostupné)",
            card_text,
            re.IGNORECASE,
        )
        availability = (
            availability_match.group(1)
            if availability_match
            else "Dostupnost neuvedena"
        )

        return AlzaDeal(
            code=code,
            name=name,
            url=product_url,
            coupon=coupon_match.group(0).upper(),
            discount_percent=discount,
            price=price,
            original_price=original_price,
            availability=availability,
            category=category,
            image_url=self._extract_image(card, source_url),
        )

    @staticmethod
    def _extract_code(card: Tag, text: str, product_url: str) -> str | None:
        for attribute in ("data-product-id", "data-item-id", "data-id"):
            value = card.get(attribute)
            if value:
                return str(value).strip()

        match = re.search(
            r"Objednací\s+kód\s*:\s*([A-Za-z0-9_-]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

        slug = urlparse(product_url).path.rstrip("/").split("/")[-1]
        return slug or None

    @staticmethod
    def _extract_prices(text: str, coupon_end: int) -> tuple[str, str]:
        after_coupon = text[coupon_end:]
        values = re.findall(
            r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})*)\s*,-",
            after_coupon,
        )
        cleaned = []
        for value in values:
            normalized = re.sub(r"\s+", " ", value).strip()
            if normalized not in cleaned:
                cleaned.append(normalized)

        price = f"{cleaned[0]} Kč" if cleaned else "Cena neuvedena"
        original = (
            f"{cleaned[1]} Kč"
            if len(cleaned) > 1
            else "Původní cena neuvedena"
        )
        return price, original

    @classmethod
    def _extract_image(cls, card: Tag, source_url: str) -> str | None:
        image = card.select_one("img")
        if not isinstance(image, Tag):
            return None

        source = (
            image.get("data-src")
            or image.get("data-lazy-src")
            or image.get("data-original")
            or image.get("src")
        )
        return urljoin(source_url, str(source).strip()) if source else None
