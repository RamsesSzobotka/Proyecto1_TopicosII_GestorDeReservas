import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Availability, Booking, Resource


def base_futura(hour=10):
    return (timezone.now() + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)


class ResourceTests(TestCase):
    def test_creacion_resource(self):
        resource = Resource.objects.create(name="Pista 1")
        self.assertEqual(Resource.objects.count(), 1)
        self.assertEqual(str(resource), "Pista 1")


class BookingCleanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)
        self.reserva = Booking.objects.create(
            user=self.user, resource=self.resource,
            start_time=self.start, end_time=self.end
        )

    def test_clean_rechaza_solape(self):
        solapada = Booking(
            user=self.user, resource=self.resource,
            start_time=self.start + timedelta(minutes=30),
            end_time=self.end + timedelta(minutes=30)
        )
        with self.assertRaises(ValidationError):
            solapada.clean()

    def test_clean_permite_reserva_sin_solape(self):
        libre = Booking(
            user=self.user, resource=self.resource,
            start_time=self.end + timedelta(hours=1),
            end_time=self.end + timedelta(hours=2)
        )
        libre.clean()  # no debe lanzar ValidationError


class ApiCrearReservaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.url = "/api/reservas/crear/"
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)

    def payload(self, **kwargs):
        data = {
            "resource_id": self.resource.id,
            "start_time": self.start.isoformat(),
            "end_time": self.end.isoformat(),
            "repeat_weeks": 0,
        }
        data.update(kwargs)
        return json.dumps(data)

    def test_sin_login_devuelve_403(self):
        response = self.client.post(self.url, self.payload(), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_recurso_inexistente_devuelve_error(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(resource_id=99999), content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_start_mayor_o_igual_que_end_devuelve_error(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            self.payload(start_time=self.end.isoformat(), end_time=self.start.isoformat()),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_bloqueo_devuelve_409(self):
        self.client.force_login(self.user)
        Availability.objects.create(resource=self.resource, start_time=self.start, end_time=self.end)
        response = self.client.post(self.url, self.payload(), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_crea_reserva_exitosa(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(repeat_weeks=1), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["reservas"]), 2)
        self.assertEqual(Booking.objects.count(), 2)

    def test_repeticion_con_conflicto_no_crea_nada(self):
        self.client.force_login(self.user)
        Booking.objects.create(user=self.user, resource=self.resource,
                               start_time=self.start + timedelta(weeks=1),
                               end_time=self.end + timedelta(weeks=1))
        response = self.client.post(self.url, self.payload(repeat_weeks=1), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertEqual(Booking.objects.count(), 1)  # solo la preexistente


class VistasTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")

    def test_home_carga(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_calendario_full_carga(self):
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
