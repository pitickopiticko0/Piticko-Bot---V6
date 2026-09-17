import unittest

from services.products.buildz import BuildzProvider


class BuildzProviderTests(unittest.TestCase):
    def test_buildz_provider_parses_czech_build(self):
        provider = BuildzProvider()

        product = provider._product_from_data(
            {
                "id": 34375,
                "name": "Herní PC RTX 5080",
                "price_display_formatted": "86 621 Kč",
                "availability": {"status": "in_stock", "label": "Skladom"},
                "display_image": "https://backend.buildz.gg/example.webp",
            }
        )

        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product.code, "34375")
        self.assertEqual(product.url, "https://buildz.gg/cs/pocitace/34375")
        self.assertEqual(product.price, "86 621 Kč")
        self.assertEqual(product.availability, "Skladem")
        self.assertEqual(product.image_url, "https://backend.buildz.gg/example.webp")

    def test_buildz_provider_ignores_invalid_build(self):
        provider = BuildzProvider()

        self.assertIsNone(provider._product_from_data({"id": "invalid", "name": "Sestava"}))
        self.assertIsNone(provider._product_from_data({"id": 12, "name": ""}))
