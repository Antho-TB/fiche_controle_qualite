"""Tests unitaires - PDFExtractor._parse_line_regex"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import partiel sans instanciation (evite l'init ADI/Sylob)
from pdf_extractor import PDFExtractor


def make_extractor() -> PDFExtractor:
    """Cree un extractor minimal sans charger de PDFs ni ADI."""
    obj = object.__new__(PDFExtractor)
    obj.pdf_dir = ""
    obj.articles_pdf = {}
    obj.adi_available = False
    obj._adi_client = None
    return obj


@pytest.fixture()
def ext():
    return make_extractor()


# ---------------------------------------------------------------------------
# Format D - Jieyang Wanxin (PO8+Lot5+Item8 sans espaces, texte chinois apres)
# ---------------------------------------------------------------------------

class TestFormatD:
    def test_format_d_chinois_direct(self, ext):
        """Texte chinois immédiatement apres Item."""
        art, po, lot = ext._parse_line_regex(
            "2024010112345105900141中文描述", "", "", False
        )
        assert art == "10590014"
        assert po  == "20240101"
        assert lot == "12345"

    def test_format_d_quantite_puis_chinois(self, ext):
        """Quantite (1-2 chiffres) entre Item et texte chinois - bug regressi anterieur."""
        art, po, lot = ext._parse_line_regex(
            "2024010212345105900152商品名称B", "", "", False
        )
        assert art == "10590015"
        assert po  == "20240102"
        assert lot == "12345"

    def test_format_d_sans_chinois_ignore(self, ext):
        """Ligne sans texte chinois ne doit PAS matcher Format D."""
        art, po, lot = ext._parse_line_regex(
            "202401011234510590014ABCDEF", "", "", False
        )
        # Format D ignoré (pas de chinois); d'autres formats peuvent matcher
        assert art != "10590014" or po != "20240101"


# ---------------------------------------------------------------------------
# Format 3 - PO+Lot+Item avec espaces (\d{5} lot fixe)
# ---------------------------------------------------------------------------

class TestFormat3:
    def test_format3_lot5_chiffres(self, ext):
        art, po, lot = ext._parse_line_regex(
            "20240101 12345 10590014", "", "", False
        )
        assert art == "10590014"
        assert po  == "20240101"
        assert lot == "12345"

    def test_format3_lot6_chiffres_pas_match(self, ext):
        """Lot 6 chiffres ne doit plus matcher Format 3 (evite sur-capture PyPDF Jieyang)."""
        art, po, lot = ext._parse_line_regex(
            "20240101 123456 10590014", "", "", False
        )
        # Ne doit pas extraire avec lot=123456 (6 digits)
        assert lot != "123456"


# ---------------------------------------------------------------------------
# Formats B, E, G - non-regression
# ---------------------------------------------------------------------------

class TestAutresFormats:
    def test_format_b_item_explicite(self, ext):
        art, po, lot = ext._parse_line_regex(
            "PO#12345678/MEN#99999 ITEM# 10590014", "", "", False
        )
        assert art == "10590014"
        assert po  == "12345678"

    def test_format_e_8chiffres_puis_lettre(self, ext):
        art, po, lot = ext._parse_line_regex(
            "10590014 FUSIL BIBI 3EN1", "88000001", "12345", True
        )
        assert art == "10590014"
        assert po  == "88000001"

    def test_format_g_code_seul(self, ext):
        art, po, lot = ext._parse_line_regex(
            "10590014", "88000001", "12345", False
        )
        assert art == "10590014"
        assert po  == "88000001"
