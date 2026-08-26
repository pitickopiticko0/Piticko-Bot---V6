import unittest

from services.products.sestavsipocitac import SestavSiPocitacProvider


class SestavSiPocitacProviderTests(unittest.TestCase):
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

