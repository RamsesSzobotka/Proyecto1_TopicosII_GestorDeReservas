import json
from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.contrib.messages import get_messages
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

    def test_clean_rechaza_solape_con_bloqueo(self):
        Availability.objects.create(
            resource=self.resource, start_time=self.start, end_time=self.end
        )
        solapada = Booking(
            user=self.user, resource=self.resource,
            start_time=self.start, end_time=self.end
        )
        with self.assertRaises(ValidationError):
            solapada.clean()


class AvailabilityCleanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)

    def test_clean_rechaza_intervalo_invertido(self):
        bloque = Availability(
            resource=self.resource,
            start_time=self.end,
            end_time=self.start
        )
        with self.assertRaises(ValidationError):
            bloque.clean()

    def test_clean_rechaza_intervalo_de_duracion_cero(self):
        bloque = Availability(
            resource=self.resource,
            start_time=self.start,
            end_time=self.start
        )
        with self.assertRaises(ValidationError):
            bloque.clean()

    def test_clean_permite_intervalo_valido(self):
        bloque = Availability(
            resource=self.resource,
            start_time=self.start,
            end_time=self.end
        )
        bloque.clean()  # no debe lanzar ValidationError
        self.assertEqual(bloque.reservas_solapadas, 0)

    def test_clean_permite_bloqueo_que_solapa_reserva_existente(self):
        Booking.objects.create(
            user=self.user, resource=self.resource,
            start_time=self.start, end_time=self.end
        )
        bloque = Availability(
            resource=self.resource,
            start_time=self.start,
            end_time=self.end
        )
        bloque.clean()  # la reserva existente gana: no debe lanzar
        self.assertEqual(bloque.reservas_solapadas, 1)


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


class AdminBloqueosTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)
        self.url_add = "/admin/reservas/availability/add/"

    def staff_con_permiso(self, username="staff", codename="add_availability"):
        staff = User.objects.create_user(
            username=username, password="pass1234", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename=codename))
        return staff

    def payload_bloqueo(self, inicio, fin):
        """
        El admin usa el widget SplitDateTime: la fecha y la hora van en campos
        separados (start_time_0 / start_time_1).
        """
        return {
            "resource": self.resource.id,
            "start_time_0": inicio.strftime("%Y-%m-%d"),
            "start_time_1": inicio.strftime("%H:%M:%S"),
            "end_time_0": fin.strftime("%Y-%m-%d"),
            "end_time_1": fin.strftime("%H:%M:%S"),
            "_save": "Guardar",
        }

    def test_usuario_no_staff_no_entra_al_admin(self):
        user = User.objects.create_user(username="normal", password="pass1234")
        self.client.force_login(user)
        response = self.client.get(self.url_add)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_sin_permiso_no_puede_crear_bloqueo(self):
        staff = User.objects.create_user(
            username="staff", password="pass1234", is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(self.url_add)
        self.assertEqual(response.status_code, 403)

    def test_staff_con_permiso_puede_crear_bloqueo(self):
        staff = self.staff_con_permiso()
        self.client.force_login(staff)
        response = self.client.get(self.url_add)
        self.assertEqual(response.status_code, 200)

    def test_staff_sin_permiso_no_puede_crear_reserva(self):
        staff = User.objects.create_user(
            username="staff", password="pass1234", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="add_availability"))
        self.client.force_login(staff)
        response = self.client.get("/admin/reservas/booking/add/")
        self.assertEqual(response.status_code, 403)

    def test_admin_rechaza_intervalo_invertido(self):
        staff = self.staff_con_permiso()
        self.client.force_login(staff)
        response = self.client.post(
            self.url_add, self.payload_bloqueo(self.end, self.start)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Availability.objects.count(), 0)
        self.assertContains(response, "El fin del bloqueo debe ser posterior al inicio.")

    def test_admin_avisa_reservas_solapadas(self):
        user = User.objects.create_user(username="cliente", password="pass1234")
        Booking.objects.create(
            user=user, resource=self.resource,
            start_time=self.start, end_time=self.end
        )
        staff = self.staff_con_permiso()
        self.client.force_login(staff)
        response = self.client.post(
            self.url_add, self.payload_bloqueo(self.start, self.end)
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Availability.objects.count(), 1)
        self.assertEqual(Booking.objects.count(), 1)  # la reserva existente se conserva
        avisos = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("1 reserva(s)" in a for a in avisos), avisos)


class ApiBloqueosTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")
        self.otro = Resource.objects.create(name="Pista 2")
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.start = base_futura()
        self.end = self.start + timedelta(hours=1)

    def test_devuelve_solo_los_bloqueos_del_recurso(self):
        Availability.objects.create(
            resource=self.resource, start_time=self.start, end_time=self.end
        )
        Availability.objects.create(
            resource=self.otro, start_time=self.start, end_time=self.end
        )
        response = self.client.get(f"/api/bloqueos/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
        eventos = response.json()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["kind"], "bloqueo")
        self.assertEqual(eventos[0]["title"], "Bloqueado")

    def test_recurso_sin_bloqueos_devuelve_lista_vacia(self):
        response = self.client.get(f"/api/bloqueos/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_api_reservas_incluye_el_tipo_reserva(self):
        Booking.objects.create(
            user=self.user, resource=self.resource,
            start_time=self.start, end_time=self.end
        )
        response = self.client.get(f"/api/reservas/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["kind"], "reserva")

    def test_calendario_full_carga_bloqueos_desde_la_api(self):
        Availability.objects.create(
            resource=self.resource, start_time=self.start, end_time=self.end
        )
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/api/bloqueos/{self.resource.id}/")
