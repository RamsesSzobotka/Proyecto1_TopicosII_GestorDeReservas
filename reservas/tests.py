import json
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.models import Permission, User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.utils import timezone

from . import forecast
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
