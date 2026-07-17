from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Product:
    code: str
    name: str
    price: str
    availability: str
    url: str
    image_url: str | None = None

    @property
    def thread_name(self) -> str:
        """Discord forum thread name, maximálně 100 znaků."""
        name = " ".join(self.name.split()).strip()
        return (name or f"MakejPC produkt {self.code}")[:100]
