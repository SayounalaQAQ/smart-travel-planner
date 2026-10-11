import importlib.util,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from travel_utils import budget,validate_trip
class UtilityTests(unittest.TestCase):
 def test_budget_breakdown_and_per_person(self):
  b=budget({'transport':120,'accommodation':300,'traveler_count':2,'currency':'EUR'}); self.assertEqual(b['scenarios']['estimate']['total'],420); self.assertEqual(b['scenarios']['estimate']['per_person'],210)
 def test_negative_budget_rejected(self):
  with self.assertRaises(ValueError): budget({'food':-1})
 def test_profile_validation_flags_missing_destination_and_days(self):
  self.assertGreaterEqual(len(validate_trip({'days':[{'activities':[]}]})),2)
 def test_assumptions_and_estimates_are_allowed_as_strings(self):
  self.assertEqual(validate_trip({'destination':'Tokyo','days':[{'activities':[{'activity':'buffer'}]}]}),[])
 def test_evidence_bad_timestamp_fails(self):
  self.assertTrue(any('checked_at' in x for x in validate_trip({'destination':'X','evidence':[{'source_url':'https://example.org','checked_at':'bad'}]})))
if __name__=='__main__': unittest.main()
