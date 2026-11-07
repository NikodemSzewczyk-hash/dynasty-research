"""Stratified metadata audit sampling regression tests."""
import sys
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from audit_sample import sample

class AuditTest(unittest.TestCase):
    def test_sample_deterministic_and_has_blank_review_columns(self):
        records=[]
        for i in range(150):
            records.append({"provider":"crossref","provider_id":f"10.1234/{i}",
                "title":("Intergenerational Wealth Mobility" if i%3==0 else
                         "Family income and child outcomes" if i%3==1 else
                         "Unrelated topic in physics"),
                "authors":["A. Researcher"],"year":2020,"source_name":"Test Journal",
                "url":"https://doi.org/10.1234/example"})
        a=sample(records,n=100,seed=42)
        b=sample(records,n=100,seed=42)
        self.assertEqual(a,b)
        self.assertEqual(len(a),100)
        self.assertTrue(all(x["metadata_verified"]=="" and x["topically_relevant"]=="" for x in a))
        self.assertGreater(sum(x["stratum"]=="high" for x in a),0)

    def test_sample_limits(self):
        with self.assertRaises(ValueError):
            sample([],n=0)

if __name__=="__main__":
    unittest.main()
