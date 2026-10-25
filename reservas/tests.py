import json
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
