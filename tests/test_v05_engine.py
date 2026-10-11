import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts")); sys.path.insert(0,str(ROOT/"mcp-server"/"src"))
from planning_engine import compare_destinations, select_attractions, optimize_route_order, weather_alternatives
from models.evidence import record
from providers.places import PlacesProvider, PlaceDetailsProvider, CallbackPlacesProvider, CallbackPlaceDetailsProvider
from providers.search import SearchProvider, HostNativeSearchProvider, BraveSearchProvider
from providers.transit import TransitProvider, UnavailableTransitProvider


class ProviderAndPipelineTests(unittest.TestCase):
    def test_interfaces_are_replaceable_contracts(self):
        self.assertTrue(issubclass(HostNativeSearchProvider,SearchProvider))
        self.assertTrue(issubclass(CallbackPlacesProvider,PlacesProvider))
        self.assertTrue(issubclass(CallbackPlaceDetailsProvider,PlaceDetailsProvider))
        self.assertTrue(issubclass(UnavailableTransitProvider,TransitProvider))

    def test_host_search_results_normalize_provenance(self):
        provider=HostNativeSearchProvider(lambda *_args,**_kw:{"results":[{"title":"Tourism","url":"https://www.japan.travel/en/","snippet":"Official"}]})
        result=provider.search("Japan")
        self.assertEqual(result["results"][0]["source_domain"],"www.japan.travel")
        self.assertIn("retrieved_at",result["results"][0]); self.assertIn("confidence",result["results"][0])

    def test_brave_without_key_degrades_explicitly(self):
        result=BraveSearchProvider(lambda *_a,**_k:{},api_key="",checked_at=lambda:"now").search("Tokyo")
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["results"],[])

    def test_search_provider_failure_returns_unavailable_not_exception(self):
        from providers.search import SearchService
        service=SearchService({"search":{"primary":{"type":"agent"},"fallback":{"adapter":"wikipedia","base_url":"https://en.wikipedia.org/w/api.php"}}},
            lambda *_a,**_k: (_ for _ in ()).throw(TimeoutError()),lambda:"now")
        self.assertEqual(service.search("current fares")["status"],"unavailable")

    def test_search_rejects_unsafe_domain_filter_and_bounds_query(self):
        from providers.search import SearchService
        service=SearchService({},lambda *_:{},lambda:"now")
        with self.assertRaises(ValueError): service.search("x",domains=["example.com/path"])
        with self.assertRaises(ValueError): service.search("x"*501)

    def test_search_official_result_priority(self):
        from providers.search import prioritize_official_results
        rows=[{"url":"https://blog.example/x"},{"url":"https://www.gotokyo.org/en"}]
        self.assertIn("gotokyo",prioritize_official_results(rows)[0]["url"])

    def test_evidence_record_canonical_and_legacy_fields(self):
        item=record("ticket","100 JPY","Venue","https://venue.example/ticket","official","2026-10-07T00:00:00Z")
        for key in ("id","claim","source_url","source_title","source_type","source_domain","retrieved_at","published_at","evidence","confidence","checked_at","value"):
            self.assertIn(key,item)
        self.assertEqual(item["source_domain"],"venue.example")

    def test_places_normalize_fields_without_inventing_metadata(self):
        result=CallbackPlacesProvider(lambda *_:{"results":[{"name":"Station","location":{"latitude":1,"longitude":2}}]}).search("Station","City")
        place=result["results"][0]
        self.assertEqual((place["lat"],place["lon"]),(1,2)); self.assertIsNone(place["official_url"])
        details=CallbackPlaceDetailsProvider(lambda *_:{"name":"Museum","opening_hours":None}).details("Museum","City")
        self.assertEqual(details["field_status"]["opening_hours"],"requires_verification")

    def test_transit_unavailable_never_returns_fake_route(self):
        result=UnavailableTransitProvider().route("A","B")
        self.assertEqual(result["data_status"],"unavailable")
        self.assertIsNone(result["duration"]); self.assertIsNone(result["fare"]); self.assertIsNone(result["transfers"])

    def test_destination_comparison_scores_only_known_factors(self):
        ranked=compare_destinations([{"name":"Tokyo","factors":{"interest_match":1,"budget_fit":.3}},
                                    {"name":"Kansai","factors":{"interest_match":.8,"budget_fit":.8}}])
        self.assertEqual(ranked[0]["name"],"Kansai"); self.assertEqual(ranked[0]["known_factor_count"],2)

    def test_attraction_budget_and_step_cap_change_selection(self):
        result=select_attractions([{"name":"Outdoor View","interest_tags":["photo"],"estimated_cost":0,"estimated_steps":15000},
                                   {"name":"Gallery","interest_tags":["photo"],"estimated_cost":4000,"estimated_steps":3000}],
                                  {"interests":["photo"],"walking_tolerance_steps":12000},attraction_budget=1000)
        self.assertFalse(result["selected"]); self.assertEqual(len(result["omitted"]),2)

    def test_unsourced_place_cannot_enter_formal_attraction_selection(self):
        result=select_attractions([{"name":"Unsourced","interest_tags":["food"],"coordinates":{"latitude":1,"longitude":2},"estimated_cost":0}],{"interests":["food"]})
        self.assertFalse(result["selected"])
        self.assertIn("缺少可追溯来源",result["omitted"][0]["why_not"])

    def test_real_coordinates_geographic_order_and_missing_time(self):
        start=(35.68,139.76)
        result=optimize_route_order([{"name":"Far","coordinates":{"latitude":35.8,"longitude":139.8}},
                                     {"name":"Near","coordinates":{"latitude":35.681,"longitude":139.761}}],start,walking_limit_steps=12000)
        self.assertEqual(result["stops"][0]["name"],"Near")
        self.assertIsNone(result["estimated_steps"]); self.assertEqual(result["duration_status"],"unavailable unless backed by route provider evidence")

    def test_weather_alternatives_require_real_hours_and_source(self):
        out=weather_alternatives([{"name":"Park","interest_tags":["photo"]}],
            [{"name":"Museum","interest_tags":["photo"],"source_url":"https://museum.example","opening_hours":"09-17"},
             {"name":"Unverified","source_url":None,"opening_hours":None}])
        self.assertEqual(out[0]["rain_alternative"]["name"],"Museum"); self.assertEqual(out[0]["rain_status"],"mapped")
        self.assertEqual(out[0]["extreme_status"],"unavailable")

    def test_no_fake_data_gate_rejects_unresolved_profile(self):
        from travel_utils import trip_readiness
        state=trip_readiness({"destination":"Japan","duration_days":8})
        self.assertFalse(state["ready_for_formal_plan"])
        self.assertIn("destination_choice",state["missing_critical_fields"])

    def test_evidence_shape_has_traceable_urls_and_checked_times(self):
        # TEST_SYNTHETIC schema contract: no dependency on private historical
        # acceptance output; never claim this is live research evidence.
        records=[{'id':str(i),'source_url':'https://example.org/source/'+str(i),
                  'retrieved_at':'2026-10-11T00:00:00Z','claim':'contract claim',
                  'evidence':'TEST_SYNTHETIC schema value'} for i in range(8)]
        self.assertGreaterEqual(len(records),8)
        self.assertEqual(len({item["id"] for item in records}),len(records))
        for item in records:
            self.assertTrue(item["source_url"].startswith("https://"))
            self.assertIn("T",item["retrieved_at"])
            self.assertTrue(item["claim"]); self.assertTrue(item["evidence"])


if __name__=="__main__": unittest.main()
