"""Offline checks for display cleanup and the shared-surname version pass in the discovery index."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from publish_pilot_discovery import tidy,tidy_title,tidy_author,combine

def row(id,title,authors,doi=None,collection="pilot23",source="Journal of Things",year=2020):
    return {"id":id,"title":title,"authors":authors,"year":year,"source":source,"doi":doi,
            "url":"https://example.org/"+id,"provider":"crossref","review_status":"pending",
            "evidence_level":"metadata_only","collection":collection,"topics":["Wealth and inheritance"],
            "source_ids":[],"score":10,"match_type":"none"}

class TidyTests(unittest.TestCase):
    def test_titles_lose_markup_entities_and_footnote_stars(self):
        self.assertEqual(tidy_title("Making a <i>NARCO</i>: Childhood Exposure*"),"Making a NARCO: Childhood Exposure")
        self.assertEqual(tidy_title("Data from Capitalized Income Tax Data *"),"Data from Capitalized Income Tax Data")
        self.assertEqual(tidy_title("BEQUEST RECEIPT AND FAMILY SIZE EFFECTS"),"Bequest Receipt and Family Size Effects")
        self.assertEqual(tidy_title("Bequests"),"Bequests")

    def test_author_cleanup_is_conservative(self):
        self.assertEqual(tidy_author("Bhashkar Mazumder B"),"Bhashkar Mazumder")
        self.assertEqual(tidy_author("WOJCIECH KOPCZUK"),"Wojciech Kopczuk")
        self.assertEqual(tidy_author("Kaymak, Bar&#305;&#537;"),"Kaymak, Barıș")  # numeric entities decoded
        self.assertEqual(tidy_author("Rodríguez Mora, José V"),"Rodríguez Mora, José V")  # Surname, First M kept
        self.assertEqual(tidy_author("Malcolm X"),"Malcolm X")  # two tokens kept
        self.assertEqual(tidy_author("Hamish W. Low"),"Hamish W. Low")

    def test_tidy_drops_empty_authors_and_fills_known_sources(self):
        r=tidy(row("a","Title",[",","Ann Author"],doi="10.1920/wp.ifs.2017.1701",source=""))
        self.assertEqual(r["authors"],["Ann Author"])
        self.assertEqual(r["source"],"IFS Working Papers")

    def test_curated_rows_are_never_touched(self):
        c=row("curated:x","TITLE IN CAPS*",["ANN AUTHOR"],collection="curated")
        self.assertIs(tidy(c),c)

class SharedSurnamePassTests(unittest.TestCase):
    def test_same_title_with_reordered_authors_is_a_possible_version(self):
        a=row("crossref:1","Born with a Silver Spoon?",["Simon Halphen Boserup","Wojciech Kopczuk"],doi="10.1/a")
        b=row("repec:2","Born with a Silver Spoon?",["Kopczuk, Wojciech","Boserup, Simon"],doi=None,source="CEPR Discussion Papers")
        merged=combine([a,b])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]["match_type"],"possible")
        self.assertEqual(merged[0]["version_count"],2)

    def test_same_title_without_shared_author_stays_separate(self):
        a=row("crossref:1","Intergenerational Mobility",["Ann Author"],doi="10.1/a")
        b=row("crossref:2","Intergenerational Mobility",["Bo Writer"],doi="10.1/b")
        self.assertEqual(len(combine([a,b])),2)

if __name__=="__main__":
    unittest.main()
