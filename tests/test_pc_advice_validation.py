import unittest

from utils.pc_advice_validation import validate_advice_answers


class PCAdviceValidationTests(unittest.TestCase):
    def test_valid_build(self):
        answers = {
            "Rozpočet": "35 000 Kč včetně počítače, bez monitoru",
            "Použití a programy": "Hraní her a občasný střih videa",
            "Monitor a cílový výkon": "1440p, 165 Hz, monitor už mám",
            "Preference a vzhled": "Preferuji NVIDIA, RGB není nutné",
            "Co už vlastníš a termín": "Nevlastním nic, nákup během září",
        }
        self.assertEqual(validate_advice_answers("build", answers), [])

    def test_build_requires_numeric_budget(self):
        answers = {
            "Rozpočet": "zatím nevím přesně",
            "Použití a programy": "Hraní her",
            "Monitor a cílový výkon": "Full HD při 144 Hz",
            "Preference a vzhled": "Bez preference značky",
            "Co už vlastníš a termín": "Mám pouze monitor, nákup v září",
        }
        errors = validate_advice_answers("build", answers)
        self.assertTrue(any("částku" in error for error in errors))

    def test_rejects_placeholder_answers(self):
        answers = {
            "Popis problému": "-",
            "Chybová hláška": "nevím",
            "Konfigurace počítače": "nic",
            "Co už jsi vyzkoušel": "?",
            "Kdy problém nastává": "idk",
        }
        errors = validate_advice_answers("diagnostics", answers)
        self.assertGreaterEqual(len(errors), 5)


if __name__ == "__main__":
    unittest.main()
