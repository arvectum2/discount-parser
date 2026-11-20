import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("gate",Path(__file__).with_name("check_section_review.py"))
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class Cases(unittest.TestCase):
    def setUp(self):self.d,self.o,self.p,self.c=gate.inputs()
    def run_gate(self):return gate.validate(self.d,self.o,self.p,self.c)
    def test_valid(self):self.assertEqual(self.run_gate(),[])
    def test_lost_line(self):self.d["sources"][0]["rows"].pop();self.assertTrue(self.run_gate())
    def test_lost_source(self):self.d["sources"].pop();self.assertTrue(self.run_gate())
    def test_source_drift(self):self.c[next(iter(self.c))]+=b"\n";self.assertTrue(self.run_gate())
    def test_heading_drift(self):self.d["sources"][0]["rows"][0][1]=-1;self.assertTrue(self.run_gate())
    def test_lost_gate(self):self.d["gates"].pop();self.assertTrue(self.run_gate())
    def test_fake_completion(self):self.d["gates"][0]["review_state"]="verified";self.assertTrue(self.run_gate())
    def test_authority(self):self.d["execution_authorized"]=True;self.assertTrue(self.run_gate())
