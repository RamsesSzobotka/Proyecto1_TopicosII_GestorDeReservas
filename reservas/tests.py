import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
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

    def test_solape_parcial_con_reserva_existente_devuelve_409(self):
        self.client.force_login(self.user)
        Booking.objects.create(user=self.user, resource=self.resource,
                               start_time=self.start + timedelta(minutes=30),
                               end_time=self.end + timedelta(minutes=30))
        response = self.client.post(self.url, self.payload(), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_cuerpo_json_no_objeto_devuelve_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, "[1, 2]", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_start_time_faltante_devuelve_400(self):
        self.client.force_login(self.user)
        data = json.loads(self.payload())
        del data["start_time"]
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_formato_datetime_invalido_devuelve_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            self.payload(start_time="no-es-fecha", end_time="tampoco"),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_datetime_sin_timezone_devuelve_400(self):
        self.client.force_login(self.user)
        naive = self.start.replace(tzinfo=None).isoformat()
        response = self.client.post(
            self.url,
            self.payload(start_time=naive, end_time=self.end.isoformat()),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("zona horaria", response.json()["error"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_repeat_weeks_fuera_de_rango_devuelve_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(repeat_weeks=53), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_repeat_weeks_no_entero_devuelve_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(repeat_weeks="varias"), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_limite_52_semanas_crea_53_ocurrencias(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(repeat_weeks=52), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["reservas"]), 53)
        self.assertEqual(Booking.objects.count(), 53)


class CsrfApiCrearReservaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.url = "/api/reservas/crear/"
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)
        self.client = Client(enforce_csrf_checks=True)

    def payload(self):
        return json.dumps({
            "resource_id": self.resource.id,
            "start_time": self.start.isoformat(),
            "end_time": self.end.isoformat(),
            "repeat_weeks": 0,
        })

    def test_post_sin_token_csrf_rechazado(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.payload(), content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.count(), 0)

    def test_calendario_full_emite_cookie_csrf(self):
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)

    def test_post_con_token_csrf_aceptado(self):
        self.client.force_login(self.user)
        self.client.get(f"/calendario_full/{self.resource.id}/")
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            self.url, self.payload(),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(Booking.objects.count(), 1)


class VistasTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")

    def test_home_carga(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_calendario_full_carga(self):
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
