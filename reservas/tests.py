import json
import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.models import Permission, User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.utils import timezone

from . import forecast
from .forms import PerfilReservaForm
from .models import Availability, Booking, PerfilReserva, Resource


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
def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=dt_timezone.utc)


class PrevisionDemandaTests(TestCase):
    """Issue #5: previsión de la demanda (solo administradores, solo lectura)."""
    URL = "/prevision/"
    DESDE = date(2026, 9, 7)   # lunes
    HASTA = date(2026, 10, 5)  # lunes (excluido): 4 semanas completas

    def setUp(self):
        self.staff = User.objects.create_user(username="admin1", password="pass1234", is_staff=True)
        self.normal = User.objects.create_user(username="normal", password="pass1234")
        self.pista = Resource.objects.create(name="Pista 1")
        self.otra = Resource.objects.create(name="Pista 2")

    def reservar(self, recurso, inicio, fin):
        return Booking.objects.create(user=self.normal, resource=recurso, start_time=inicio, end_time=fin)

    def cargar_fixtures(self):
        # Semana 07/09: borde lunes 00:00 (1.5 h) + miércoles (2 h) -> 2 reservas, 3.5 h
        self.reservar(self.pista, utc(2026, 9, 7, 0, 0), utc(2026, 9, 7, 1, 30))
        self.reservar(self.pista, utc(2026, 9, 9, 10), utc(2026, 9, 9, 12))
        # Semana 14/09: vacía
        # Semana 21/09: domingo 23:00 a lunes 01:00 -> cuenta en su semana de inicio, 2 h
        self.reservar(self.pista, utc(2026, 9, 27, 23), utc(2026, 9, 28, 1))
        # Semana 28/09: 3 reservas, 2.5 h
        self.reservar(self.pista, utc(2026, 9, 28, 0), utc(2026, 9, 28, 1))
        self.reservar(self.pista, utc(2026, 9, 30, 9), utc(2026, 9, 30, 10))
        self.reservar(self.pista, utc(2026, 9, 30, 11), utc(2026, 9, 30, 11, 30))
        # Fuera del rango: justo antes de desde y justo en hasta (excluido)
        self.reservar(self.pista, utc(2026, 9, 6, 23), utc(2026, 9, 7, 0))
        self.reservar(self.pista, utc(2026, 10, 5, 0), utc(2026, 10, 5, 1))
        # Otro recurso dentro del rango: no debe contarse
        self.reservar(self.otra, utc(2026, 9, 8, 10), utc(2026, 9, 8, 12))

    def get(self, **params):
        base = {"recurso": self.pista.id, "desde": self.DESDE.isoformat(), "hasta": self.HASTA.isoformat()}
        base.update(params)
        return self.client.get(self.URL, base)

    # --- permisos ---
    def test_anonimo_redirige_al_login_de_admin(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/"))

    def test_usuario_normal_redirige(self):
        self.client.force_login(self.normal)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/"))

    def test_staff_inactivo_redirige(self):
        inactivo = User.objects.create_user(username="inactivo", password="pass1234", is_staff=True, is_active=False)
        self.client.force_login(inactivo)
        self.assertEqual(self.client.get(self.URL).status_code, 302)

    def test_staff_accede(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.URL).status_code, 200)

    def test_post_devuelve_405(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.URL, {"recurso": self.pista.id}).status_code, 405)

    def test_home_muestra_enlace_solo_a_staff(self):
        self.assertNotContains(self.client.get("/"), "/prevision/")
        self.client.force_login(self.normal)
        self.assertNotContains(self.client.get("/"), "/prevision/")
        self.client.force_login(self.staff)
        self.assertContains(self.client.get("/"), "/prevision/")

    # --- agregación ---
    def test_agregacion_exacta_por_semana(self):
        self.cargar_fixtures()
        semanas = forecast.agregar_semanas(self.pista, self.DESDE, self.HASTA)
        resumen = [(s["inicio"], s["reservas"], s["horas"], s["completa"]) for s in semanas]
        self.assertEqual(resumen, [
            (date(2026, 9, 7), 2, 3.5, True),
            (date(2026, 9, 14), 0, 0.0, True),   # semana vacía en medio
            (date(2026, 9, 21), 1, 2.0, True),
            (date(2026, 9, 28), 3, 2.5, True),
        ])

    def test_aislamiento_entre_recursos(self):
        self.cargar_fixtures()
        semanas = forecast.agregar_semanas(self.otra, self.DESDE, self.HASTA)
        self.assertEqual([s["reservas"] for s in semanas], [1, 0, 0, 0])
        self.assertEqual(semanas[0]["horas"], 2.0)

    def test_semana_parcial_se_marca_y_borde_desde_incluido(self):
        self.reservar(self.pista, utc(2026, 9, 1, 0), utc(2026, 9, 1, 1))  # martes 00:00 = desde
        semanas = forecast.agregar_semanas(self.pista, date(2026, 9, 1), self.HASTA)
        self.assertEqual(semanas[0]["inicio"], date(2026, 8, 31))
        self.assertFalse(semanas[0]["completa"])
        self.assertEqual(semanas[0]["reservas"], 1)
        self.assertTrue(all(s["completa"] for s in semanas[1:]))

    def test_agregar_rechaza_rango_invertido(self):
        with self.assertRaises(ValueError):
            forecast.agregar_semanas(self.pista, self.HASTA, self.DESDE)

    # --- previsión ---
    def test_media_movil_exacta(self):
        self.cargar_fixtures()
        semanas = forecast.agregar_semanas(self.pista, self.DESDE, self.HASTA)
        resultado = forecast.pronosticar(semanas)
        self.assertTrue(resultado["suficiente"])
        self.assertEqual(len(resultado["prevision"]), forecast.HORIZONTE_SEMANAS)
        # reservas: (2+0+1+3)/4 = 1.5 ; horas: (3.5+0+2+2.5)/4 = 2.0
        self.assertEqual([p["inicio"] for p in resultado["prevision"]],
                         [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)])
        for p in resultado["prevision"]:
            self.assertEqual(p["reservas"], 1.5)
            self.assertEqual(p["horas"], 2.0)

    def test_media_movil_solo_usa_las_ultimas_semanas_completas(self):
        semanas = [
            {"inicio": date(2026, 8, 31) + timedelta(weeks=i), "reservas": r, "horas": float(r), "completa": True}
            for i, r in enumerate([100, 1, 2, 3, 4])
        ]
        resultado = forecast.pronosticar(semanas)
        self.assertEqual(resultado["prevision"][0]["reservas"], 2.5)  # (1+2+3+4)/4, sin el 100

    def test_determinismo(self):
        self.cargar_fixtures()
        a = forecast.pronosticar(forecast.agregar_semanas(self.pista, self.DESDE, self.HASTA))
        b = forecast.pronosticar(forecast.agregar_semanas(self.pista, self.DESDE, self.HASTA))
        self.assertEqual(a, b)

    def test_rango_por_defecto(self):
        desde, hasta = forecast.rango_por_defecto(date(2026, 10, 21))  # miércoles
        self.assertEqual(hasta, date(2026, 10, 19))
        self.assertEqual(desde, date(2026, 7, 27))

    # --- sin datos / historial insuficiente ---
    def test_sin_reservas_estado_comprensible(self):
        self.client.force_login(self.staff)
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["resultado"]["suficiente"])
        self.assertEqual(response.context["resultado"]["prevision"], [])
        self.assertContains(response, "No hay reservas registradas")

    def test_historial_insuficiente_estado_comprensible(self):
        self.cargar_fixtures()
        self.client.force_login(self.staff)
        response = self.get(desde="2026-09-14")  # solo 3 semanas completas
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["resultado"]["suficiente"])
        self.assertContains(response, "historial es insuficiente")
        self.assertContains(response, "No se puede estimar la demanda")

    def test_sin_recurso_muestra_selector_y_estado_vacio(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pista 1")
        self.assertContains(response, "Elige un recurso")

    def test_con_datos_muestra_grafico_aviso_y_json(self):
        self.cargar_fixtures()
        self.client.force_login(self.staff)
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esta previsión es una estimación basada en el histórico; no modifica precios ni inventario.")
        self.assertContains(response, 'id="datos-prevision"')
        self.assertContains(response, "chart.js@4.4.1")
        self.assertEqual(response.context["datos"]["recurso"], "Pista 1")
        self.assertEqual(response.context["datos"]["desde"], "2026-09-07")
        self.assertEqual(response.context["datos"]["hasta"], "2026-10-05")

    # --- rangos y entradas inválidas (400, nunca 500) ---
    def assert_400(self, response, texto):
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, texto, status_code=400)

    def test_fecha_invalida(self):
        self.client.force_login(self.staff)
        self.assert_400(self.get(desde="no-es-fecha"), "formato AAAA-MM-DD")
        self.assert_400(self.get(hasta="2026-02-30"), "formato AAAA-MM-DD")
        self.assert_400(self.get(desde="20260907"), "formato AAAA-MM-DD")

    def test_desde_igual_o_posterior_a_hasta(self):
        self.client.force_login(self.staff)
        self.assert_400(self.get(desde="2026-10-05", hasta="2026-10-05"), "anterior")
        self.assert_400(self.get(desde="2026-10-12", hasta="2026-10-05"), "anterior")

    def test_rango_mayor_a_52_semanas(self):
        self.client.force_login(self.staff)
        self.assert_400(self.get(desde="2025-01-01", hasta="2026-10-05"), "52 semanas")

    def test_rango_de_exactamente_52_semanas_es_valido(self):
        self.client.force_login(self.staff)
        response = self.get(desde="2025-10-06", hasta="2026-10-05")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["semanas"]), 52)

    def test_recurso_inexistente_o_invalido(self):
        self.client.force_login(self.staff)
        self.assert_400(self.get(recurso=99999), "no existe")
        self.assert_400(self.get(recurso="abc"), "no existe")
        self.assert_400(self.get(recurso="-1"), "no existe")
        self.assert_400(self.get(recurso="²"), "no existe")

    # --- solo lectura ---
    def test_la_vista_no_modifica_la_base_de_datos(self):
        self.cargar_fixtures()
        self.client.force_login(self.staff)
        antes = (Booking.objects.count(), Resource.objects.count(), Availability.objects.count())
        self.get()
        self.get(desde="x")
        self.client.get(self.URL)
        despues = (Booking.objects.count(), Resource.objects.count(), Availability.objects.count())
        self.assertEqual(antes, despues)


class CancelacionBase(TestCase):
    """Utilidades comunes del issue #6 (autogestión y cancelación)."""

    def setUp(self):
        self.dueno = User.objects.create_user(username="dueno", password="pass1234")
        self.otro = User.objects.create_user(username="otro", password="pass1234")
        self.staff = User.objects.create_user(username="admin6", password="pass1234", is_staff=True)
        self.pista = Resource.objects.create(name="Pista 6")

    def reserva(self, desde_ahora, usuario=None, horas=1, recurso=None, serie=None):
        inicio = timezone.now() + desde_ahora
        return Booking.objects.create(
            user=usuario or self.dueno, resource=recurso or self.pista,
            start_time=inicio, end_time=inicio + timedelta(hours=horas), serie=serie,
        )

    def cancelar(self, reserva_pk, alcance="una", cliente=None):
        cliente = cliente or self.client
        datos = {} if alcance is None else {"alcance": alcance}
        return cliente.post(f"/reservas/{reserva_pk}/cancelar/", datos)

    def mensajes(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]


class CancelacionPropiedadTests(CancelacionBase):
    def test_otro_usuario_recibe_404_y_la_reserva_sigue_activa(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.otro)
        response = self.cancelar(r.pk)
        self.assertEqual(response.status_code, 404)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_reserva_ajena_e_inexistente_dan_la_misma_respuesta(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.otro)
        ajena = self.cancelar(r.pk)
        inexistente = self.cancelar(999999)
        self.assertEqual(ajena.status_code, 404)
        self.assertEqual(inexistente.status_code, 404)
        self.assertEqual(ajena.content, inexistente.content)

    def test_id_no_numerico_no_resuelve(self):
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.post("/reservas/abc/cancelar/").status_code, 404)

    def test_el_propietario_cancela_y_queda_registro(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.dueno)
        response = self.cancelar(r.pk)
        self.assertRedirects(response, "/mis-reservas/")
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.CANCELADA)
        self.assertEqual(r.cancelada_por, self.dueno)
        self.assertIsNotNone(r.cancelada_en)
        self.assertEqual(Booking.objects.filter(pk=r.pk).count(), 1)  # cancelación lógica

    def test_staff_cancela_reserva_ajena(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.staff)
        self.cancelar(r.pk)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.CANCELADA)
        self.assertEqual(r.cancelada_por, self.staff)

    def test_mis_reservas_solo_muestra_las_propias(self):
        propia = self.reserva(timedelta(days=3))
        ajena = self.reserva(timedelta(days=4), usuario=self.otro, recurso=Resource.objects.create(name="Sala ajena"))
        self.client.force_login(self.dueno)
        response = self.client.get("/mis-reservas/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.pista.name)
        self.assertNotContains(response, "Sala ajena")
        self.assertNotContains(response, f"/reservas/{ajena.pk}/cancelar/")
        self.assertContains(response, f"/reservas/{propia.pk}/cancelar/")

    def test_staff_en_mis_reservas_ve_solo_las_suyas(self):
        self.reserva(timedelta(days=3))
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get("/mis-reservas/"), self.pista.name)


class CancelacionAccesoTests(CancelacionBase):
    def test_get_devuelve_405_sin_cancelar(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.get(f"/reservas/{r.pk}/cancelar/").status_code, 405)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_anonimo_va_al_login_y_no_cancela(self):
        r = self.reserva(timedelta(days=3))
        response = self.cancelar(r.pk)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_mis_reservas_anonimo_redirige_al_login(self):
        response = self.client.get("/mis-reservas/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_cancelar_exige_csrf(self):
        r = self.reserva(timedelta(days=3))
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        response = cliente.post(f"/reservas/{r.pk}/cancelar/", {"alcance": "una"})
        self.assertEqual(response.status_code, 403)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_la_pagina_incluye_el_token_csrf_en_el_formulario(self):
        self.reserva(timedelta(days=3))
        self.client.force_login(self.dueno)
        self.assertContains(self.client.get("/mis-reservas/"), "csrfmiddlewaretoken")

    def test_alcance_invalido_no_cancela(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.dueno)
        response = self.cancelar(r.pk, alcance="todas")
        self.assertRedirects(response, "/mis-reservas/")
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)


class CancelacionLimiteTests(CancelacionBase):
    def test_cliente_dentro_del_limite_si_puede(self):
        r = self.reserva(timedelta(hours=2, minutes=5))
        self.client.force_login(self.dueno)
        self.cancelar(r.pk)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.CANCELADA)

    def test_cliente_fuera_del_limite_no_puede_y_se_le_explica(self):
        r = self.reserva(timedelta(hours=1, minutes=55))
        self.client.force_login(self.dueno)
        response = self.cancelar(r.pk)
        self.assertRedirects(response, "/mis-reservas/")
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)
        self.assertTrue(any("2 horas" in m for m in self.mensajes(response)))

    def test_frontera_exacta_con_ahora_fijo(self):
        ahora = timezone.now()
        inicio = ahora + timedelta(hours=2)
        r = Booking(user=self.dueno, resource=self.pista, start_time=inicio, end_time=inicio + timedelta(hours=1))
        self.assertTrue(r.puede_cancelar(self.dueno, ahora)[0])  # justo 2 h: permitido
        self.assertFalse(r.puede_cancelar(self.dueno, ahora + timedelta(seconds=1))[0])  # 1 s menos

    def test_staff_dentro_de_las_2_horas_si_puede(self):
        r = self.reserva(timedelta(minutes=30))
        self.client.force_login(self.staff)
        self.cancelar(r.pk)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.CANCELADA)

    def test_reserva_empezada_no_se_cancela_ni_por_staff(self):
        r = self.reserva(timedelta(minutes=-30))
        for usuario in (self.dueno, self.staff):
            self.client.force_login(usuario)
            response = self.cancelar(r.pk)
            self.assertRedirects(response, "/mis-reservas/")
            r.refresh_from_db()
            self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_reserva_pasada_no_se_cancela(self):
        r = self.reserva(timedelta(days=-2))
        self.client.force_login(self.dueno)
        self.cancelar(r.pk)
        r.refresh_from_db()
        self.assertEqual(r.estado, Booking.Estado.ACTIVA)

    def test_la_regla_se_comunica_en_la_pagina(self):
        self.client.force_login(self.dueno)
        response = self.client.get("/mis-reservas/")
        self.assertContains(response, "hasta 2 horas antes")

    def test_reserva_dentro_de_limite_no_ofrece_boton(self):
        r = self.reserva(timedelta(minutes=30))
        self.client.force_login(self.dueno)
        response = self.client.get("/mis-reservas/")
        self.assertNotContains(response, f"/reservas/{r.pk}/cancelar/")
        self.assertContains(response, "Solo puedes cancelar hasta 2 horas antes")


class CancelacionRepetidaTests(CancelacionBase):
    def test_cancelar_dos_veces_la_segunda_falla_sin_cambiar_datos(self):
        r = self.reserva(timedelta(days=3))
        self.client.force_login(self.dueno)
        self.cancelar(r.pk)
        r.refresh_from_db()
        primera = r.cancelada_en
        response = self.cancelar(r.pk)
        self.assertRedirects(response, "/mis-reservas/")
        self.assertTrue(any("ya está cancelada" in m for m in self.mensajes(response)))
        r.refresh_from_db()
        self.assertEqual(r.cancelada_en, primera)

    def test_staff_tampoco_puede_cancelar_una_cancelada(self):
        r = self.reserva(timedelta(days=3))
        r.cancelar(self.dueno)
        self.client.force_login(self.staff)
        response = self.cancelar(r.pk)
        self.assertTrue(any("ya está cancelada" in m for m in self.mensajes(response)))
        r.refresh_from_db()
        self.assertEqual(r.cancelada_por, self.dueno)


class CancelacionDisponibilidadTests(CancelacionBase):
    def crear_via_api(self, inicio, fin, repeat_weeks=0):
        return self.client.post("/api/reservas/crear/", json.dumps({
            "resource_id": self.pista.id, "start_time": inicio.isoformat(),
            "end_time": fin.isoformat(), "repeat_weeks": repeat_weeks,
        }), content_type="application/json")

    def test_api_reservas_deja_de_devolver_la_cancelada(self):
        r = self.reserva(timedelta(days=3))
        otra = self.reserva(timedelta(days=4))
        self.assertEqual(len(self.client.get(f"/api/reservas/{self.pista.id}/").json()), 2)
        r.cancelar(self.dueno)
        eventos = self.client.get(f"/api/reservas/{self.pista.id}/").json()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["start"], otra.start_time.isoformat())

    def test_se_puede_volver_a_reservar_la_franja_cancelada(self):
        r = self.reserva(timedelta(days=3))
        inicio, fin = r.start_time, r.end_time
        self.client.force_login(self.otro)
        self.assertEqual(self.crear_via_api(inicio, fin).status_code, 409)
        r.cancelar(self.dueno)
        response = self.crear_via_api(inicio, fin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.filter(estado=Booking.Estado.ACTIVA).count(), 1)
        self.assertEqual(Booking.objects.count(), 2)  # la cancelada se conserva

    def test_la_restriccion_unica_solo_aplica_a_activas(self):
        r = self.reserva(timedelta(days=3))
        r.cancelar(self.dueno)
        Booking.objects.create(user=self.otro, resource=self.pista, start_time=r.start_time, end_time=r.end_time)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(user=self.dueno, resource=self.pista, start_time=r.start_time, end_time=r.end_time)

    def test_booking_clean_ignora_canceladas(self):
        r = self.reserva(timedelta(days=3))
        r.cancelar(self.dueno)
        nueva = Booking(user=self.otro, resource=self.pista, start_time=r.start_time, end_time=r.end_time)
        nueva.clean()  # no lanza

    def test_bloqueo_no_cuenta_reservas_canceladas_como_solapadas(self):
        r = self.reserva(timedelta(days=3))
        r.cancelar(self.dueno)
        bloque = Availability(resource=self.pista, start_time=r.start_time, end_time=r.end_time)
        bloque.clean()
        self.assertEqual(bloque.reservas_solapadas, 0)

    def test_vista_calendario_no_lista_canceladas(self):
        r = self.reserva(timedelta(hours=1))
        r.start_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        r.end_time = r.start_time + timedelta(hours=1)
        r.save()
        response = self.client.get(f"/calendario/{self.pista.id}/")
        self.assertEqual(response.status_code, 200)
        total = sum(len(v) for v in response.context["reservas_por_dia"].values())
        self.assertEqual(total, 1)
        r.cancelar(self.dueno)
        response = self.client.get(f"/calendario/{self.pista.id}/")
        self.assertEqual(sum(len(v) for v in response.context["reservas_por_dia"].values()), 0)

    def test_prevision_excluye_canceladas(self):
        inicio = datetime(2026, 9, 9, 10, tzinfo=dt_timezone.utc)
        activa = Booking.objects.create(user=self.dueno, resource=self.pista,
                                        start_time=inicio, end_time=inicio + timedelta(hours=1))
        cancelada = Booking.objects.create(user=self.dueno, resource=self.pista,
                                           start_time=inicio + timedelta(days=1),
                                           end_time=inicio + timedelta(days=1, hours=2))
        desde, hasta = date(2026, 9, 7), date(2026, 9, 14)
        antes = forecast.agregar_semanas(self.pista, desde, hasta)
        self.assertEqual((antes[0]["reservas"], antes[0]["horas"]), (2, 3.0))
        cancelada.cancelar(self.dueno)
        despues = forecast.agregar_semanas(self.pista, desde, hasta)
        self.assertEqual((despues[0]["reservas"], despues[0]["horas"]), (1, 1.0))
        activa.refresh_from_db()
        self.assertEqual(activa.estado, Booking.Estado.ACTIVA)


class SerieTests(CancelacionBase):
    def crear_serie(self, semanas=3, inicio=None):
        inicio = inicio or (timezone.now() + timedelta(days=10)).replace(microsecond=0)
        self.client.force_login(self.dueno)
        response = self.client.post("/api/reservas/crear/", json.dumps({
            "resource_id": self.pista.id, "start_time": inicio.isoformat(),
            "end_time": (inicio + timedelta(hours=1)).isoformat(), "repeat_weeks": semanas,
        }), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        return list(Booking.objects.filter(resource=self.pista).order_by("start_time"))

    def test_las_ocurrencias_comparten_serie(self):
        reservas = self.crear_serie(3)
        self.assertEqual(len(reservas), 4)
        series = {r.serie for r in reservas}
        self.assertEqual(len(series), 1)
        self.assertIsNotNone(series.pop())

    def test_reserva_simple_no_tiene_serie(self):
        reservas = self.crear_serie(0)
        self.assertEqual(len(reservas), 1)
        self.assertIsNone(reservas[0].serie)

    def test_dos_series_distintas_no_se_mezclan(self):
        a = self.crear_serie(1)
        b = self.crear_serie(1, inicio=timezone.now() + timedelta(days=11, hours=3))
        self.assertEqual(len({r.serie for r in b} - {r.serie for r in a if r.serie}), 1)

    def test_la_respuesta_de_la_api_conserva_su_contrato(self):
        self.client.force_login(self.dueno)
        inicio = timezone.now() + timedelta(days=5)
        response = self.client.post("/api/reservas/crear/", json.dumps({
            "resource_id": self.pista.id, "start_time": inicio.isoformat(),
            "end_time": (inicio + timedelta(hours=1)).isoformat(), "repeat_weeks": 1,
        }), content_type="application/json")
        self.assertEqual(set(response.json()), {"success", "reservas"})
        self.assertEqual(set(response.json()["reservas"][0]), {"start", "end"})

    def test_cancelar_una_de_la_serie_no_toca_las_demas(self):
        reservas = self.crear_serie(3)
        self.cancelar(reservas[1].pk, "una")
        estados = [Booking.objects.get(pk=r.pk).estado for r in reservas]
        self.assertEqual(estados, ["activa", "cancelada", "activa", "activa"])

    def test_cancelar_esta_y_las_siguientes(self):
        reservas = self.crear_serie(3)
        response = self.cancelar(reservas[1].pk, "serie")
        estados = [Booking.objects.get(pk=r.pk).estado for r in reservas]
        self.assertEqual(estados, ["activa", "cancelada", "cancelada", "cancelada"])
        self.assertTrue(any("3 reserva(s)" in m for m in self.mensajes(response)))

    def test_serie_solo_cancela_las_siguientes_activas(self):
        serie = uuid.uuid4()
        anterior = self.reserva(timedelta(days=3), serie=serie)
        elegida = self.reserva(timedelta(days=10), serie=serie)
        ya_cancelada = self.reserva(timedelta(days=17), serie=serie)
        ya_cancelada.cancelar(self.otro)
        siguiente = self.reserva(timedelta(days=24), serie=serie)
        self.client.force_login(self.dueno)
        response = self.cancelar(elegida.pk, "serie")
        estados = [Booking.objects.get(pk=x.pk).estado for x in (anterior, elegida, ya_cancelada, siguiente)]
        self.assertEqual(estados, ["activa", "cancelada", "cancelada", "cancelada"])
        self.assertEqual(Booking.objects.get(pk=ya_cancelada.pk).cancelada_por, self.otro)  # no se reescribe
        self.assertTrue(any("2 reserva(s)" in m for m in self.mensajes(response)))

    def test_serie_con_la_elegida_fuera_del_limite_no_cambia_nada(self):
        serie = uuid.uuid4()
        elegida = self.reserva(timedelta(minutes=90), serie=serie)
        siguiente = self.reserva(timedelta(days=7), serie=serie)
        self.client.force_login(self.dueno)
        response = self.cancelar(elegida.pk, "serie")
        self.assertTrue(any("2 horas" in m for m in self.mensajes(response)))
        self.assertEqual([Booking.objects.get(pk=x.pk).estado for x in (elegida, siguiente)], ["activa", "activa"])

    def test_staff_cancela_serie_incluso_dentro_de_2_horas(self):
        serie = uuid.uuid4()
        a = self.reserva(timedelta(minutes=40), serie=serie)
        b = self.reserva(timedelta(minutes=100), serie=serie)
        c = self.reserva(timedelta(days=7), serie=serie)
        self.client.force_login(self.staff)
        self.cancelar(a.pk, "serie")
        self.assertEqual([Booking.objects.get(pk=x.pk).estado for x in (a, b, c)], ["cancelada"] * 3)

    def test_alcance_serie_en_reserva_simple_cancela_solo_esa(self):
        r = self.reserva(timedelta(days=3))
        otra = self.reserva(timedelta(days=4))
        self.client.force_login(self.dueno)
        self.cancelar(r.pk, "serie")
        r.refresh_from_db(); otra.refresh_from_db()
        self.assertEqual((r.estado, otra.estado), ("cancelada", "activa"))

    def test_mis_reservas_muestra_ocurrencia_n_de_m_contando_canceladas(self):
        reservas = self.crear_serie(3)
        reservas[0].cancelar(self.dueno)
        response = self.client.get("/mis-reservas/")
        self.assertContains(response, "Serie: ocurrencia 2 de 4")
        self.assertContains(response, "Serie: ocurrencia 4 de 4")
        self.assertContains(response, "Serie: ocurrencia 1 de 4")  # la cancelada, en el historial
        self.assertContains(response, "Cancelar esta y las siguientes")

    def test_mis_reservas_separa_proximas_e_historial(self):
        futura = self.reserva(timedelta(days=3))
        cancelada = self.reserva(timedelta(days=5))
        cancelada.cancelar(self.dueno)
        pasada = self.reserva(timedelta(days=-3))
        self.client.force_login(self.dueno)
        response = self.client.get("/mis-reservas/")
        self.assertEqual([r.pk for r in response.context["proximas"]], [futura.pk])
        self.assertEqual({r.pk for r in response.context["historial"]}, {cancelada.pk, pasada.pk})
        self.assertContains(response, "Cancelada")
        self.assertContains(response, "Pasada")


class EnlaceMisReservasTests(CancelacionBase):
    def test_home_muestra_el_enlace_solo_a_usuarios_autenticados(self):
        self.assertNotContains(self.client.get("/"), "/mis-reservas/")
        self.client.force_login(self.dueno)
        self.assertContains(self.client.get("/"), "/mis-reservas/")

    def test_admin_lista_estado_y_serie(self):
        self.staff.is_superuser = True
        self.staff.save()
        r = self.reserva(timedelta(days=3), serie=uuid.uuid4())
        self.client.force_login(self.staff)
        response = self.client.get("/admin/reservas/booking/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Estado")
        self.assertContains(response, "Serie")
        self.assertContains(response, str(r.serie)[:8])


class CalendarioEventosApiTests(TestCase):
    """ISSUE-04: serialización, aislamiento, rangos y privacidad de las APIs del calendario."""

    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")
        self.otro = Resource.objects.create(name="Pista 2")
        self.dueno = User.objects.create_user(username="dueno", password="pass1234")
        self.extra = User.objects.create_user(username="extra", password="pass1234")
        self.staff = User.objects.create_user(username="admin1", password="pass1234", is_staff=True)
        self.inicio = utc(2030, 1, 10, 10)
        self.fin = utc(2030, 1, 10, 11)
        self.reserva = Booking.objects.create(
            user=self.dueno, resource=self.resource, start_time=self.inicio, end_time=self.fin
        )
        self.url_r = f"/api/reservas/{self.resource.id}/"
        self.url_b = f"/api/bloqueos/{self.resource.id}/"

    # --- Serialización ---
    def test_serializa_reserva_con_campos_exactos(self):
        self.client.force_login(self.extra)
        evento = self.client.get(self.url_r).json()[0]
        self.assertEqual(evento["title"], "Ocupado")
        self.assertEqual(evento["start"], "2030-01-10T10:00:00+00:00")
        self.assertEqual(evento["end"], "2030-01-10T11:00:00+00:00")
        self.assertEqual(evento["color"], "#10b981")
        self.assertEqual(evento["kind"], "reserva")
        self.assertFalse(evento["propia"])

    def test_serializa_bloqueo_con_campos_exactos(self):
        Availability.objects.create(resource=self.resource, start_time=self.inicio, end_time=self.fin)
        evento = self.client.get(self.url_b).json()[0]
        self.assertEqual(evento["title"], "Bloqueado")
        self.assertEqual(evento["start"], "2030-01-10T10:00:00+00:00")
        self.assertEqual(evento["end"], "2030-01-10T11:00:00+00:00")
        self.assertEqual(evento["color"], "#ef4444")
        self.assertEqual(evento["kind"], "bloqueo")

    # --- Aislamiento por recurso ---
    def test_reservas_de_otro_recurso_no_aparecen(self):
        Booking.objects.create(user=self.extra, resource=self.otro, start_time=self.inicio, end_time=self.fin)
        self.assertEqual(len(self.client.get(self.url_r).json()), 1)

    def test_bloqueos_de_otro_recurso_no_aparecen(self):
        Availability.objects.create(resource=self.otro, start_time=self.inicio, end_time=self.fin)
        self.assertEqual(self.client.get(self.url_b).json(), [])

    # --- Recurso inexistente ---
    def test_recurso_inexistente_devuelve_404_json(self):
        for url in ("/api/reservas/99999/", "/api/bloqueos/99999/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)
            self.assertIn("error", response.json())

    # --- Rangos ---
    def rango(self, url, start, end):
        return self.client.get(url, {"start": start, "end": end})

    def test_rango_incluye_evento_dentro_y_excluye_fuera(self):
        dentro = self.rango(self.url_r, "2030-01-10T00:00:00+00:00", "2030-01-11T00:00:00+00:00")
        self.assertEqual(len(dentro.json()), 1)
        fuera = self.rango(self.url_r, "2030-01-11T00:00:00+00:00", "2030-01-12T00:00:00+00:00")
        self.assertEqual(fuera.json(), [])

    def test_rango_frontera_exacta_se_excluye_y_solape_parcial_se_incluye(self):
        # El rango termina justo cuando empieza la reserva: no solapa.
        self.assertEqual(self.rango(self.url_r, "2030-01-10T09:00:00+00:00", "2030-01-10T10:00:00+00:00").json(), [])
        # El rango empieza justo cuando termina la reserva: no solapa.
        self.assertEqual(self.rango(self.url_r, "2030-01-10T11:00:00+00:00", "2030-01-10T12:00:00+00:00").json(), [])
        # Solape parcial: se incluye.
        self.assertEqual(len(self.rango(self.url_r, "2030-01-10T10:30:00+00:00", "2030-01-10T12:00:00+00:00").json()), 1)

    def test_rango_aplica_tambien_a_bloqueos(self):
        Availability.objects.create(resource=self.resource, start_time=self.inicio, end_time=self.fin)
        self.assertEqual(len(self.rango(self.url_b, "2030-01-10T10:30:00+00:00", "2030-01-10T12:00:00+00:00").json()), 1)
        self.assertEqual(self.rango(self.url_b, "2030-01-10T11:00:00+00:00", "2030-01-10T12:00:00+00:00").json(), [])

    def test_sin_parametros_devuelve_todo(self):
        Booking.objects.create(
            user=self.extra, resource=self.resource, start_time=utc(2031, 5, 1, 9), end_time=utc(2031, 5, 1, 10)
        )
        self.assertEqual(len(self.client.get(self.url_r).json()), 2)

    def test_parametros_invalidos_devuelven_400(self):
        for url in (self.url_r, self.url_b):
            self.assertEqual(self.rango(url, "no-es-fecha", "2030-01-11T00:00:00+00:00").status_code, 400)
            self.assertEqual(self.client.get(url, {"start": "2030-01-10T00:00:00+00:00"}).status_code, 400)
            self.assertEqual(self.rango(url, "", "").status_code, 400)

    def test_rango_invertido_o_vacio_devuelve_400(self):
        for url in (self.url_r, self.url_b):
            invertido = self.rango(url, "2030-01-11T00:00:00+00:00", "2030-01-10T00:00:00+00:00")
            self.assertEqual(invertido.status_code, 400)
            self.assertIn("error", invertido.json())
            vacio = self.rango(url, "2030-01-10T00:00:00+00:00", "2030-01-10T00:00:00+00:00")
            self.assertEqual(vacio.status_code, 400)

    def test_fechas_naive_devuelven_400(self):
        for url in (self.url_r, self.url_b):
            response = self.rango(url, "2030-01-10T00:00:00", "2030-01-11T00:00:00")
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json())

    def test_mas_sin_codificar_llega_como_espacio_y_funciona(self):
        # Un '+' sin codificar en la query string llega al servidor como espacio.
        response = self.client.get(
            self.url_r + "?start=2030-01-10T00:00:00+02:00&end=2030-01-11T00:00:00+02:00"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    # --- Privacidad ---
    def test_anonimo_y_otro_usuario_ven_ocupado_sin_username(self):
        anonimo = self.client.get(self.url_r)
        self.assertEqual(anonimo.json()[0]["title"], "Ocupado")
        self.assertNotIn("dueno", anonimo.content.decode())
        self.client.force_login(self.extra)
        otro = self.client.get(self.url_r)
        self.assertEqual(otro.json()[0]["title"], "Ocupado")
        self.assertNotIn("dueno", otro.content.decode())

    def test_propietario_ve_tu_reserva(self):
        self.client.force_login(self.dueno)
        evento = self.client.get(self.url_r).json()[0]
        self.assertEqual(evento["title"], "Tu reserva")
        self.assertTrue(evento["propia"])

    def test_staff_ve_el_username(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url_r).json()[0]["title"], "Reservado por dueno")

    def test_staff_titular_ve_tu_reserva(self):
        # Ser titular tiene prioridad sobre ser staff.
        Booking.objects.create(
            user=self.staff, resource=self.resource, start_time=utc(2030, 1, 11, 10), end_time=utc(2030, 1, 11, 11)
        )
        self.client.force_login(self.staff)
        titulos = [e["title"] for e in self.client.get(self.url_r).json()]
        self.assertEqual(titulos, ["Reservado por dueno", "Tu reserva"])


class CalendarioFullUxTests(TestCase):
    """ISSUE-04: leyenda, zona horaria, vistas y manejo de conflictos en el cliente y el servidor."""

    def setUp(self):
        self.resource = Resource.objects.create(name="Pista 1")
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.rival = User.objects.create_user(username="rival", password="pass1234")

    def test_pagina_incluye_leyenda_zona_horaria_y_vistas(self):
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        self.assertContains(response, "Disponible (horario 09:00-21:00)")
        self.assertContains(response, "Ocupado (reserva)")
        self.assertContains(response, "Tu reserva")
        self.assertContains(response, "Bloqueado por el administrador")
        self.assertContains(response, "Horarios mostrados en tu zona horaria local")
        self.assertContains(response, "dayGridMonth,timeGridWeek,timeGridDay")
        self.assertContains(response, "selectAllow")

    def test_pagina_refresca_eventos_tras_respuesta_del_servidor(self):
        response = self.client.get(f"/calendario_full/{self.resource.id}/")
        html = response.content.decode()
        bloque = html[html.index("function crearReserva"):html.index("function getCookie")]
        self.assertIn("calendar.refetchEvents()", bloque)
        self.assertIn("content-type", bloque)
        self.assertIn("52", bloque)

    def test_conflicto_concurrente_sigue_rechazado_por_el_servidor(self):
        # El usuario cargó el calendario con la franja libre; otro reserva antes del POST.
        inicio = base_futura()
        fin = inicio + timedelta(hours=1)
        Booking.objects.create(user=self.rival, resource=self.resource, start_time=inicio, end_time=fin)
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/reservas/crear/",
            json.dumps({
                "resource_id": self.resource.id,
                "start_time": inicio.isoformat(),
                "end_time": fin.isoformat(),
                "repeat_weeks": 0,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertTrue(response.json()["error"])
        self.assertEqual(Booking.objects.count(), 1)

# === ISSUE-03: datos de reserva guardados ===

DATOS_PERFIL = {
    "nombre_completo": "Ana Pérez",
    "telefono": "+57 300 123 4567",
    "email_contacto": "ana@example.com",
    "metodo_pago": "tarjeta",
    "tarjeta_ultimos4": "1234",
}


def crear_perfil(user, **extra):
    datos = dict(DATOS_PERFIL)
    datos.update(extra)
    return PerfilReserva.objects.create(user=user, **datos)


class PerfilReservaModeloFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pass1234")

    def test_form_valido_completo(self):
        form = PerfilReservaForm(DATOS_PERFIL)
        self.assertTrue(form.is_valid(), form.errors)

    def test_telefono_invalido(self):
        form = PerfilReservaForm({**DATOS_PERFIL, "telefono": "abc"})
        self.assertFalse(form.is_valid())
        self.assertIn("telefono", form.errors)

    def test_email_invalido(self):
        form = PerfilReservaForm({**DATOS_PERFIL, "email_contacto": "no-es-correo"})
        self.assertFalse(form.is_valid())
        self.assertIn("email_contacto", form.errors)

    def test_tarjeta_sin_ultimos4_da_error(self):
        form = PerfilReservaForm({**DATOS_PERFIL, "tarjeta_ultimos4": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("tarjeta_ultimos4", form.errors)

    def test_ultimos4_con_cinco_digitos_o_letras_da_error(self):
        for valor in ("12345", "12ab"):
            form = PerfilReservaForm({**DATOS_PERFIL, "tarjeta_ultimos4": valor})
            self.assertFalse(form.is_valid(), valor)
            self.assertIn("tarjeta_ultimos4", form.errors)

    def test_digitos_unicode_no_son_validos(self):
        # \d aceptaría dígitos de ancho completo o árabe-índicos.
        for valor in ("１２３４", "١٢٣٤"):
            form = PerfilReservaForm({**DATOS_PERFIL, "tarjeta_ultimos4": valor})
            self.assertFalse(form.is_valid(), valor)
            self.assertIn("tarjeta_ultimos4", form.errors)
        form = PerfilReservaForm({**DATOS_PERFIL, "telefono": "１２３４５６７"})
        self.assertFalse(form.is_valid())
        self.assertIn("telefono", form.errors)

    def test_salto_de_linea_final_no_es_valido_en_el_modelo(self):
        perfil = PerfilReserva(nombre_completo="Ana", telefono="3001234567", email_contacto="a@b.com",
                               metodo_pago="tarjeta", tarjeta_ultimos4="123\n")
        self.assertFalse(perfil.esta_completo())

    def test_en_pista_ignora_ultimos4_con_formato_invalido(self):
        form = PerfilReservaForm({**DATOS_PERFIL, "metodo_pago": "en_pista", "tarjeta_ultimos4": "abcd"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).tarjeta_ultimos4, "")

    def test_en_pista_vacia_ultimos4(self):
        form = PerfilReservaForm({**DATOS_PERFIL, "metodo_pago": "en_pista", "tarjeta_ultimos4": "9999"})
        self.assertTrue(form.is_valid(), form.errors)
        perfil = form.save(commit=False)
        self.assertEqual(perfil.tarjeta_ultimos4, "")

    def test_esta_completo_y_resumen(self):
        perfil = crear_perfil(self.user)
        self.assertTrue(perfil.esta_completo())
        self.assertEqual(
            perfil.resumen(),
            "Ana Pérez · ana@example.com · +57 300 123 4567 · Tarjeta (simulada) •••• 1234",
        )
        incompleto = PerfilReserva(user=self.user, nombre_completo="Ana", metodo_pago="tarjeta")
        self.assertFalse(incompleto.esta_completo())
        sin_ultimos4 = PerfilReserva(**{**DATOS_PERFIL, "tarjeta_ultimos4": ""}, user=self.user)
        self.assertFalse(sin_ultimos4.esta_completo())

    def test_modelo_sin_campos_sensibles(self):
        nombres = {f.name for f in PerfilReserva._meta.get_fields()}
        for prohibido in ("numero_tarjeta", "cvv", "caducidad"):
            self.assertNotIn(prohibido, nombres)


class PerfilVistaTests(TestCase):
    URL = "/perfil/"

    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pass1234")
        self.otro = User.objects.create_user(username="beto", password="pass1234")

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))
        self.assertEqual(self.client.post(self.URL, DATOS_PERFIL).status_code, 302)
        self.assertEqual(PerfilReserva.objects.count(), 0)

    def test_primer_uso_get_formulario_vacio(self):
        self.client.force_login(self.user)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aún no tienes datos guardados")
        self.assertContains(response, "Nunca escribas el número completo ni el CVV")

    def test_primer_uso_post_valido_crea_perfil(self):
        self.client.force_login(self.user)
        response = self.client.post(self.URL, DATOS_PERFIL)
        self.assertEqual(response.status_code, 302)
        perfil = PerfilReserva.objects.get(user=self.user)
        self.assertEqual(perfil.nombre_completo, "Ana Pérez")
        mensajes = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("guardaron" in m for m in mensajes))

    def test_post_invalido_no_crea_y_muestra_error(self):
        self.client.force_login(self.user)
        response = self.client.post(self.URL, {**DATOS_PERFIL, "telefono": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Introduce un teléfono válido")
        self.assertEqual(PerfilReserva.objects.count(), 0)

    def test_next_seguro_redirige_y_externo_se_ignora(self):
        self.client.force_login(self.user)
        response = self.client.post(self.URL, {**DATOS_PERFIL, "next": "/calendario_full/1/"})
        self.assertRedirects(response, "/calendario_full/1/", fetch_redirect_response=False)
        response = self.client.post(self.URL, {**DATOS_PERFIL, "next": "https://evil.example/"})
        self.assertEqual(response["Location"], "/perfil/")

    def test_actualizacion_modifica_el_perfil_existente(self):
        crear_perfil(self.user)
        self.client.force_login(self.user)
        self.client.post(self.URL, {**DATOS_PERFIL, "nombre_completo": "Ana María", "metodo_pago": "en_pista"})
        self.assertEqual(PerfilReserva.objects.count(), 1)
        perfil = PerfilReserva.objects.get(user=self.user)
        self.assertEqual(perfil.nombre_completo, "Ana María")
        self.assertEqual(perfil.tarjeta_ultimos4, "")

    def test_control_de_acceso_no_ve_ni_modifica_datos_ajenos(self):
        crear_perfil(self.user)
        self.client.force_login(self.otro)
        response = self.client.get(self.URL)
        self.assertNotContains(response, "Ana Pérez")
        self.assertNotContains(response, "ana@example.com")
        self.client.post(self.URL, {**DATOS_PERFIL, "nombre_completo": "Beto", "email_contacto": "beto@example.com"})
        self.assertEqual(PerfilReserva.objects.get(user=self.user).nombre_completo, "Ana Pérez")
        self.assertEqual(PerfilReserva.objects.get(user=self.otro).nombre_completo, "Beto")

    def test_no_existe_url_con_id(self):
        crear_perfil(self.user)
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get("/perfil/1/").status_code, 404)

    def test_datos_de_pago_extra_no_se_almacenan(self):
        self.client.force_login(self.user)
        self.client.post(self.URL, {**DATOS_PERFIL, "numero_tarjeta": "4111111111111111", "cvv": "987"})
        perfil = PerfilReserva.objects.get(user=self.user)
        guardado = " ".join(str(getattr(perfil, f.name)) for f in perfil._meta.concrete_fields)
        self.assertNotIn("4111111111111111", guardado)
        self.assertNotIn("987", guardado)


class ApiDatosGuardadosTests(TestCase):
    URL = "/api/reservas/crear/"

    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.inicio = utc(2030, 5, 6, 10)
        self.client.force_login(self.user)

    def payload(self, horas=0, **extra):
        inicio = self.inicio + timedelta(hours=horas)
        data = {
            "resource_id": self.resource.id,
            "start_time": inicio.isoformat(),
            "end_time": (inicio + timedelta(hours=1)).isoformat(),
            "repeat_weeks": 0,
        }
        data.update(extra)
        return json.dumps(data)

    def post(self, **kwargs):
        return self.client.post(self.URL, self.payload(**kwargs), content_type="application/json")

    def test_uso_repetido_sin_reenviar_datos(self):
        perfil = crear_perfil(self.user)
        r1 = self.post(usar_datos_guardados=True)
        r2 = self.post(horas=2, usar_datos_guardados=True)
        for r in (r1, r2):
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["success"])
            self.assertEqual(r.json()["datos_usados"], perfil.resumen())
        self.assertEqual(Booking.objects.filter(user=self.user).count(), 2)

    def test_sin_perfil_devuelve_400_y_no_crea(self):
        response = self.post(usar_datos_guardados=True)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["perfil_url"], "/perfil/")
        self.assertIn("Completa tus datos de reserva", response.json()["error"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_perfil_incompleto_devuelve_400_y_no_crea(self):
        PerfilReserva.objects.create(user=self.user, nombre_completo="Ana", metodo_pago="tarjeta")
        response = self.post(usar_datos_guardados=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["perfil_url"], "/perfil/")
        self.assertEqual(Booking.objects.count(), 0)

    def test_actualizacion_se_refleja_en_la_siguiente_reserva(self):
        crear_perfil(self.user)
        self.client.post("/perfil/", {**DATOS_PERFIL, "nombre_completo": "Ana María", "metodo_pago": "en_pista"})
        response = self.post(usar_datos_guardados=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ana María", response.json()["datos_usados"])
        self.assertIn("Pago en la pista", response.json()["datos_usados"])

    def test_flag_no_booleano_devuelve_400(self):
        crear_perfil(self.user)
        for valor in ("true", 1, None, [True]):
            response = self.post(usar_datos_guardados=valor)
            self.assertEqual(response.status_code, 400, valor)
        self.assertEqual(Booking.objects.count(), 0)

    def test_sin_flag_o_false_comportamiento_previo(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("datos_usados", response.json())
        response = self.post(horas=2, usar_datos_guardados=False)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("datos_usados", response.json())

    def test_ignora_datos_de_pago_en_el_cuerpo(self):
        crear_perfil(self.user)
        response = self.post(usar_datos_guardados=True, numero_tarjeta="4111111111111111", cvv="987")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("4111111111111111", json.dumps(response.json()))
        self.assertEqual(PerfilReserva.objects.get(user=self.user).tarjeta_ultimos4, "1234")

    def test_usa_solo_el_perfil_del_usuario_autenticado(self):
        crear_perfil(self.user)
        otro = User.objects.create_user(username="beto", password="pass1234")
        self.client.force_login(otro)
        response = self.post(usar_datos_guardados=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)


class CalendarioDatosGuardadosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pass1234")
        self.otro = User.objects.create_user(username="beto", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.url = f"/calendario_full/{self.resource.id}/"

    def test_con_perfil_completo_muestra_resumen(self):
        perfil = crear_perfil(self.user)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Datos de reserva guardados")
        self.assertContains(response, perfil.resumen())

    def test_sin_perfil_muestra_aviso_de_completar(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Aún no tienes datos de reserva guardados")
        self.assertContains(response, "/perfil/?next=")

    def test_resumen_de_otro_usuario_no_aparece(self):
        crear_perfil(self.user)
        self.client.force_login(self.otro)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Ana Pérez")
        self.assertNotContains(response, "ana@example.com")
        self.assertContains(response, "Aún no tienes datos de reserva guardados")

    def test_anonimo_no_ve_recuadro(self):
        crear_perfil(self.user)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Ana Pérez")
        self.assertNotContains(response, "Datos de reserva guardados")
