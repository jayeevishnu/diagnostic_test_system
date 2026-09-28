from decimal import Decimal

from centres.models import CentreTest, DiagnosticCentre, DiagnosticTest
from common.testing import BaseAPITestCase


class CentreTests(BaseAPITestCase):
    def test_public_can_list_centres_with_tests_and_prices(self):
        response = self.client.get("/centres/")
        self.assertEqual(response.status_code, 200)
        centre = response.data["results"][0]
        self.assertEqual(centre["name"], "Lab One")
        self.assertEqual(centre["city"], "Pune")
        self.assertEqual(centre["tests"][0]["test"]["code"], "CBC")
        self.assertEqual(centre["tests"][0]["price"], "499.00")

    def test_list_is_query_efficient(self):
        for i in range(5):
            c = DiagnosticCentre.objects.create(name=f"Lab {i}", address="x", city="Pune")
            CentreTest.objects.create(centre=c, test=self.test_cbc, price=Decimal("100"))
        # count + centres + prefetched offerings(with tests), independent of number of centres
        with self.assertNumQueries(3):
            self.client.get("/centres/")

    def test_filters(self):
        other_test = DiagnosticTest.objects.create(code="TSH", name="TSH")
        mumbai = DiagnosticCentre.objects.create(name="Lab Two", address="2 Sea Rd", city="Mumbai")
        CentreTest.objects.create(centre=mumbai, test=other_test, price=Decimal("300"))

        by_city = self.client.get("/centres/?city=mumbai").data["results"]
        self.assertEqual([c["name"] for c in by_city], ["Lab Two"])
        by_test = self.client.get(f"/centres/?test={self.test_cbc.id}").data["results"]
        self.assertEqual([c["name"] for c in by_test], ["Lab One"])
        self.assertEqual(self.client.get("/centres/?test=abc").status_code, 400)

    def test_inactive_centres_and_unavailable_tests_hidden(self):
        self.offering.is_available = False
        self.offering.save()
        self.assertEqual(self.client.get(f"/centres/{self.centre.id}/tests/").data, [])
        self.centre.is_active = False
        self.centre.save()
        self.assertEqual(self.client.get("/centres/").data["count"], 0)

    def test_only_admin_can_write(self):
        payload = {"name": "New Lab", "address": "5 Road", "city": "Delhi"}
        self.assertEqual(self.client.post("/centres/", payload).status_code, 401)
        self.login(self.user)
        self.assertEqual(self.client.post("/centres/", payload).status_code, 403)
        self.assertEqual(self.client.patch(f"/centres/{self.centre.id}/", {"name": "Hacked"}).status_code, 403)
        self.login(self.admin)
        response = self.client.post("/centres/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tests"], [])

    def test_admin_adds_test_to_centre(self):
        self.login(self.admin)
        new_test = DiagnosticTest.objects.create(code="LIPID", name="Lipid Profile")
        response = self.client.post(
            "/centre-tests/", {"centre": self.centre.id, "test": new_test.id, "price": "799.00"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        dup = self.client.post(
            "/centre-tests/", {"centre": self.centre.id, "test": new_test.id, "price": "1.00"}, format="json"
        )
        self.assertEqual(dup.status_code, 400)
        bad_price = self.client.patch(f"/centre-tests/{response.data['id']}/", {"price": "-5"}, format="json")
        self.assertEqual(bad_price.status_code, 400)

    def test_cannot_delete_centre_with_bookings(self):
        self.create_booking()
        self.login(self.admin)
        self.assertEqual(self.client.delete(f"/centres/{self.centre.id}/").status_code, 409)
