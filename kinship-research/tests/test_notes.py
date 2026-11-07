"""Evidence-note schema tests: draft notes cannot masquerade as read papers."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SITE/"scripts"))
from dynasty_data.notes import draft_note,validate_note,hash_pdf,load_and_validate

class NoteTest(unittest.TestCase):
    def example(self):
        return draft_note({"id":"family-wealth-and-mobility","title":"Family Wealth and Mobility"},
                          [{"doi":"10.1234/test","url":"https://doi.org/10.1234/test","kind":"journal_article"}])

    def test_draft_is_not_full_text_review(self):
        note=self.example()
        self.assertEqual(note["status"],"draft")
        self.assertEqual(validate_note(note),[])
        self.assertIn("no paper has been read",note["disclaimer"])

    def test_read_status_requires_pdf_provenance(self):
        note=self.example()
        note["status"]="source_read"
        self.assertTrue(any("PDF SHA256" in e for e in validate_note(note)))
        note["source"]["pdf_sha256"]="a"*64
        note["source"]["pdf_pages"]=15
        note["reviewer"]="Editor"
        self.assertEqual(validate_note(note),[])

    def test_checked_claim_requires_page_evidence(self):
        note=self.example()
        note["status"]="evidence_checked"
        note["source"]["pdf_sha256"]="b"*64
        note["source"]["pdf_pages"]=20
        note["reviewer"]="Editor"
        note["claims"]=[{"kind":"identified_estimand","text":"Effect of parental lottery wins","evidence":[]}]
        self.assertTrue(any("page-level evidence" in e for e in validate_note(note)))
        note["claims"][0]["evidence"]=[{"page":21,"table":"Table 2"}]
        self.assertTrue(any("beyond PDF" in e for e in validate_note(note)))
        note["claims"][0]["evidence"]=[{"page":10,"table":"Table 2"}]
        self.assertEqual(validate_note(note),[])

    def test_pdf_hash_checks_magic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"paper.pdf"
            p.write_bytes(b"not a pdf")
            with self.assertRaises(ValueError):
                hash_pdf(p)
            p.write_bytes(b"%PDF-1.7\nTest bytes")
            self.assertEqual(hash_pdf(p),hashlib.sha256(p.read_bytes()).hexdigest())

    def test_load_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"note.json"
            p.write_text(json.dumps(self.example()),encoding="utf-8")
            self.assertEqual(load_and_validate(p),[])

if __name__=="__main__":
    unittest.main()
