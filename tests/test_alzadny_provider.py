from __future__ import annotations

import unittest

from services.products.alzadny import AlzaDaysProvider


class AlzaDaysProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = AlzaDaysProvider(min_discount=15)

    def test_parses_relevant_discounted_product(self) -> None:
        html = """
        <div class="box browsingitem" data-product-id="IFX001">
          <a class="name browsinglink" href="/ifixit-sada-d123.htm">
            iFixit sada precizních šroubováků
          </a>
          <p>Koupit s kódem ALZADNY20. 799,- 999,-</p>
          <span>Skladem &gt; 5 ks</span>
          <img data-src="https://cdn.alza.cz/example.jpg">
        </div>
        """

        deals = self.provider._parse_page(
            html,
            category="Servisní nářadí",
            source_url="https://www.alza.cz/hobby/naradi/alza-dny/test.htm",
            require_keyword=True,
        )

        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].code, "IFX001")
        self.assertEqual(deals[0].coupon, "ALZADNY20")
        self.assertEqual(deals[0].price, "799 Kč")
        self.assertEqual(deals[0].original_price, "999 Kč")

    def test_rejects_irrelevant_tool_and_small_discount(self) -> None:
        html = """
        <div class="box browsingitem" data-product-id="HAMMER1">
          <a class="name browsinglink" href="/kladivo-d1.htm">Velké kladivo</a>
          <p>Koupit s kódem ALZADNY30. 300,- 500,-</p>
        </div>
        <div class="box browsingitem" data-product-id="IFX002">
          <a class="name browsinglink" href="/ifixit-d2.htm">iFixit sada bitů</a>
          <p>Koupit s kódem ALZADNY10. 900,- 1 000,-</p>
        </div>
        """

        deals = self.provider._parse_page(
            html,
            category="Servisní nářadí",
            source_url="https://www.alza.cz/hobby/naradi/alza-dny/test.htm",
            require_keyword=True,
        )

        self.assertEqual(deals, [])


if __name__ == "__main__":
    unittest.main()
