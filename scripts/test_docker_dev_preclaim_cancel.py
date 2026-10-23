"""Offline option guards only; native recovery is not executed."""
import unittest
from types import SimpleNamespace
from scripts.docker_dev_preclaim_cancel import validate_options
class Options(unittest.TestCase):
    def good(self):
        return SimpleNamespace(backend_container_id="a"*64,image_id="sha256:"+"b"*64,
            request_sha256="c"*64,candidate_receipt_sha256="d"*64,
            candidate_basename=".backend-package-candidate-owned",request="verification/request.json")
    def test_exact_pins(self): validate_options(self.good())
    def test_bad_pin(self):
        for name in ("backend_container_id","image_id","request_sha256","candidate_receipt_sha256"):
            x=self.good();setattr(x,name,"short")
            with self.assertRaises(ValueError):validate_options(x)
    def test_candidate_traversal(self):
        x=self.good();x.candidate_basename="../package"
        with self.assertRaises(ValueError):validate_options(x)
    def test_request_traversal(self):
        for path in ("/tmp/request","verification/../request","request.json"):
            x=self.good();x.request=path
            with self.assertRaises(ValueError):validate_options(x)
if __name__=="__main__":unittest.main()
