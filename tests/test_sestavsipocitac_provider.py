import json
import unittest

from services.products.sestavsipocitac import SestavSiPocitacProvider


class SestavSiPocitacProviderTests(unittest.TestCase):
    def test_parse_next_data_reads_initial_products(self):
        next_payload = {
            "initialProducts": [
                {
                    "id": 1264,
                    "name": "SSP Machine - RX 9060 XT 8GB / R5 7500F",
                    "slug": "ssp-machine-rx-9060-xt-8-gb-r5-7500-f",
                    "priceWithVat": 24490,
                    "mainImageUrl": "https://sestavserver.roit.sk/uploads/build.webp",
                    "availabilityStatus": "in_stock",
                }
            ]
        }
        html = (
            "<script>self.__next_f.push([1,"
            + json.dumps("6:" + json.dumps(next_payload), ensure_ascii=False)
            + "])</script>"
        )

        products = SestavSiPocitacProvider()._parse_page(html)

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].code, "ssp-machine-rx-9060-xt-8-gb-r5-7500-f")
        self.assertEqual(products[0].name, "SSP Machine - RX 9060 XT 8GB / R5 7500F")
        self.assertEqual(products[0].price, "24\u00a0490 Kč")
        self.assertEqual(products[0].availability, "Skladem")
        self.assertEqual(products[0].image_url, "https://sestavserver.roit.sk/uploads/build.webp")

    def test_parse_card_uses_heading_when_link_only_says_detail(self):
        html = """
        <article>
          <h2>Fractal White RTX 5070 Ti</h2>
          <a href="/hotove-sestavy/fractal-white-rtx-5070-ti-r5-7500-x3-d">Detail</a>
          <span>45 990 Kč</span>
          <img src="/images/fractal.jpg">
        </article>
        """

        products = SestavSiPocitacProvider()._parse_page(html)

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].code, "fractal-white-rtx-5070-ti-r5-7500-x3-d")
        self.assertEqual(products[0].name, "Fractal White RTX 5070 Ti")
        self.assertEqual(products[0].price, "45 990 Kč")
        self.assertEqual(products[0].image_url, "https://sestavsipocitac.cz/images/fractal.jpg")
