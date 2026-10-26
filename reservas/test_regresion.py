"""
Suite de regresión de ISSUE-08 (fase A, sobre main).

Complementa a reservas/tests.py (que NO se modifica aquí) con:
  - login/logout, api_crear_reserva (casos no cubiertos), vista `calendario`,
  - admin (borrado de bloqueos, permisos sobre Resource), __str__,
  - comando crear_reservas_demo,
  - integridad del proyecto (check y migraciones),
  - FALLOS CONOCIDOS marcados con @unittest.expectedFailure (ver doc/PRUEBAS.md).

Todos los tests usan la BD de test aislada de Django (nunca db.sqlite3) y fechas
fijas; solo se congela timezone.now donde la vista lo consulta.
"""
import io
import json
import unittest
import warnings
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings

from .models import Availability, Booking, Resource


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=dt_timezone.utc)


URL_CREAR = "/api/reservas/crear/"


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegresionBase(TestCase):
    """Base común: hasher rápido y fechas fijas (2030) independientes del reloj."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass1234")
        self.resource = Resource.objects.create(name="Pista 1")
        self.start = utc(2030, 3, 4, 10)
        self.end = utc(2030, 3, 4, 11)

    def payload(self, **kwargs):
        data = {
            "resource_id": self.resource.id,
            "start_time": self.start.isoformat(),
            "end_time": self.end.isoformat(),
            "repeat_weeks": 0,
        }
        data.update(kwargs)
        return json.dumps(data)

    def post_crear(self, cuerpo, client=None):
        client = client or self.client
        return client.post(URL_CREAR, cuerpo, content_type="application/json")


# ---------------------------------------------------------------- login/logout

class LoginLogoutTests(RegresionBase):
    def test_login_get_muestra_formulario(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')

    def test_login_valido_redirige_y_abre_sesion(self):
        response = self.client.post("/login/", {"username": "tester", "password": "pass1234"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_invalido_muestra_error_y_no_abre_sesion(self):
        response = self.client.post("/login/", {"username": "tester", "password": "incorrecta"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario o contraseña incorrectos.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_usuario_inexistente_no_abre_sesion(self):
        response = self.client.post("/login/", {"username": "nadie", "password": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_redirige_y_cierra_sesion(self):
        self.client.force_login(self.user)
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.get("/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)


# ------------------------------------------------------------ api_crear_reserva

class ApiCrearReservaRegresionTests(RegresionBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_get_devuelve_405(self):
        response = self.client.get(URL_CREAR)
        self.assertEqual(response.status_code, 405)
        self.assertFalse(response.json()["success"])

    def test_cuerpo_no_json_devuelve_400(self):
        response = self.post_crear("esto no es json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_falta_resource_id_devuelve_400(self):
        data = json.loads(self.payload())
        del data["resource_id"]
        response = self.post_crear(json.dumps(data))
        self.assertEqual(response.status_code, 400)
        self.assertIn("resource_id", response.json()["error"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_integrity_error_en_segunda_ocurrencia_devuelve_409_sin_parciales(self):
        """La 1ª creación es real; la 2ª lanza IntegrityError: la serie se revierte."""
        crear_real = Booking.objects.create
        llamadas = []

        def create_con_fallo(**kwargs):
            llamadas.append(kwargs)
            if len(llamadas) == 2:
                raise IntegrityError("carrera simulada sobre unique_together")
            return crear_real(**kwargs)

        with mock.patch.object(Booking.objects, "create", side_effect=create_con_fallo):
            response = self.post_crear(self.payload(repeat_weeks=2))
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertEqual(Booking.objects.count(), 0)

    def test_52_semanas_crean_53_reservas_con_fechas_exactas(self):
        response = self.post_crear(self.payload(repeat_weeks=52))
        self.assertEqual(response.status_code, 200)
        reservas = response.json()["reservas"]
        self.assertEqual(len(reservas), 53)
        for i, item in enumerate(reservas):
            self.assertEqual(item["start"], (self.start + timedelta(weeks=i)).isoformat())
            self.assertEqual(item["end"], (self.end + timedelta(weeks=i)).isoformat())
        guardadas = list(Booking.objects.order_by("start_time").values_list("start_time", "end_time"))
        esperadas = [(self.start + timedelta(weeks=i), self.end + timedelta(weeks=i)) for i in range(53)]
        self.assertEqual(guardadas, esperadas)
        self.assertEqual(guardadas[-1][0], utc(2031, 3, 3, 10))


# ------------------------------------------------------------------- calendario

class CalendarioSemanalTests(RegresionBase):
    AHORA = utc(2030, 1, 16, 12)  # miércoles; la semana va del lunes 14 al domingo 20

    def setUp(self):
        super().setUp()
        self.otra = Resource.objects.create(name="Pista 2")

    def reservar(self, recurso, inicio):
        return Booking.objects.create(
            user=self.user, resource=recurso,
            start_time=inicio, end_time=inicio + timedelta(hours=1))

    def get_calendario(self, resource_id):
        with mock.patch("django.utils.timezone.now", return_value=self.AHORA):
            return self.client.get(f"/calendario/{resource_id}/")

    def test_carga_y_agrupa_reservas_de_la_semana_actual(self):
        """Se comprueba el contexto de la vista (ver hallazgo sobre la plantilla en doc/PRUEBAS.md)."""
        lunes = self.reservar(self.resource, utc(2030, 1, 14, 9))
        domingo = self.reservar(self.resource, utc(2030, 1, 20, 22))
        self.reservar(self.resource, utc(2030, 1, 13, 22))   # domingo anterior: fuera
        self.reservar(self.resource, utc(2030, 1, 21, 9))    # lunes siguiente: fuera
        self.reservar(self.otra, utc(2030, 1, 15, 9))        # otro recurso: fuera
        response = self.get_calendario(self.resource.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["resource"], self.resource)
        por_dia = response.context["reservas_por_dia"]
        self.assertEqual(sorted(por_dia), [f"2030-01-{d}" for d in range(14, 21)])
        self.assertEqual(por_dia["2030-01-14"], [lunes])
        self.assertEqual(por_dia["2030-01-20"], [domingo])
        self.assertEqual(sum(len(v) for v in por_dia.values()), 2)

    def test_semana_sin_reservas_carga_con_dias_vacios(self):
        response = self.get_calendario(self.resource.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["dias_semana"]), 7)
        self.assertTrue(all(v == [] for v in response.context["reservas_por_dia"].values()))

    def test_recurso_inexistente_devuelve_404(self):
        self.assertEqual(self.get_calendario(99999).status_code, 404)

    @unittest.expectedFailure
    def test_c1_plantilla_muestra_las_reservas_de_la_semana(self):
        """
        FALLO CONOCIDO (C1). Bug: calendario.html usa {% if reservas_por_dia.fecha %},
        que busca la clave literal 'fecha' y no la variable del {% with %}; la vista
        agrupa bien las reservas pero la plantilla pinta siempre "Libre".
        Reproducción: reserva el lunes 14/01/2030 09:00 y abre /calendario/<id>/ esa semana.
        Origen: código base (vista semanal previa a las issues).
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        self.reservar(self.resource, utc(2030, 1, 14, 9))
        response = self.get_calendario(self.resource.id)
        self.assertContains(response, "09:00 - 10:00")
        self.assertContains(response, "Libre", count=6)


# ------------------------------------------------------------------------ admin

class AdminRegresionTests(RegresionBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pass1234")

    def test_borrar_bloqueo_conserva_reservas_solapadas(self):
        reserva = Booking.objects.create(
            user=self.user, resource=self.resource, start_time=self.start, end_time=self.end)
        bloqueo = Availability.objects.create(
            resource=self.resource, start_time=self.start, end_time=self.end)
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/admin/reservas/availability/{bloqueo.pk}/delete/", {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Availability.objects.filter(pk=bloqueo.pk).exists())
        self.assertTrue(Booking.objects.filter(pk=reserva.pk).exists())

    def test_resource_anonimo_redirige_al_login_del_admin(self):
        response = self.client.get("/admin/reservas/resource/add/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_resource_staff_sin_permiso_recibe_403(self):
        staff = User.objects.create_user("staff", password="pass1234", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/reservas/resource/add/").status_code, 403)
        response = self.client.post("/admin/reservas/resource/add/", {"name": "X", "description": ""})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Resource.objects.filter(name="X").exists())

    def test_resource_staff_con_permiso_add_puede_crear(self):
        staff = User.objects.create_user("staff", password="pass1234", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="add_resource"))
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/reservas/resource/add/").status_code, 200)
        response = self.client.post(
            "/admin/reservas/resource/add/", {"name": "Sala Nueva", "description": "desc", "_save": "Guardar"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Resource.objects.filter(name="Sala Nueva").exists())


class StrModelosTests(RegresionBase):
    def test_str_resource(self):
        self.assertEqual(str(self.resource), "Pista 1")

    def test_str_availability(self):
        bloqueo = Availability.objects.create(
            resource=self.resource, start_time=self.start, end_time=self.end)
        self.assertEqual(str(bloqueo), f"Pista 1 - {self.start} a {self.end}")

    def test_str_booking(self):
        reserva = Booking.objects.create(
            user=self.user, resource=self.resource, start_time=self.start, end_time=self.end)
        self.assertEqual(str(reserva), "Reserva de Pista 1 por tester")


# ----------------------------------------------------------------- comando demo

class CrearReservasDemoTests(RegresionBase):
    def ejecutar(self):
        salida = io.StringIO()
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            call_command("crear_reservas_demo", stdout=salida)
        return salida.getvalue(), avisos

    def test_crea_usuario_recurso_y_15_reservas(self):
        salida, _ = self.ejecutar()
        demo = User.objects.get(username="demo_user")
        self.assertTrue(demo.check_password("demo1234"))
        pista = Resource.objects.get(name="Pista Pádel 1")
        self.assertEqual(Booking.objects.filter(user=demo, resource=pista).count(), 15)
        self.assertEqual(Booking.objects.count(), 15)
        self.assertIn("Reservas demo creadas correctamente.", salida)

    def test_es_idempotente_en_usuario_y_recurso(self):
        self.ejecutar()
        self.ejecutar()
        self.assertEqual(User.objects.filter(username="demo_user").count(), 1)
        self.assertEqual(Resource.objects.filter(name="Pista Pádel 1").count(), 1)
        self.assertEqual(Booking.objects.count(), 15)

    @unittest.expectedFailure
    def test_d1_no_borra_reservas_ajenas(self):
        """
        FALLO CONOCIDO (D1). Bug: el comando ejecuta Booking.objects.all().delete(),
        así que borra también las reservas reales de otros usuarios y recursos.
        Reproducción: crea una reserva de otro usuario y ejecuta
        python manage.py crear_reservas_demo; la reserva desaparece.
        Origen: código base (comando de datos demo).
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        ajena = Booking.objects.create(
            user=self.user, resource=self.resource, start_time=self.start, end_time=self.end)
        self.ejecutar()
        self.assertTrue(Booking.objects.filter(pk=ajena.pk).exists())

    @unittest.expectedFailure
    def test_d2_no_emite_avisos_de_datetimes_naive(self):
        """
        FALLO CONOCIDO (D2). Bug: el comando usa datetime.now() sin zona horaria con
        USE_TZ=True; Django emite un RuntimeWarning por cada datetime naive guardado.
        Reproducción: python -W always manage.py crear_reservas_demo.
        Origen: código base (comando de datos demo).
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        _, avisos = self.ejecutar()
        naive = [a for a in avisos if issubclass(a.category, RuntimeWarning)
                 and "naive datetime" in str(a.message)]
        self.assertEqual(naive, [])


# ------------------------------------------------------------------ integridad

class IntegridadProyectoTests(RegresionBase):
    def test_check_sin_errores(self):
        call_command("check", stdout=io.StringIO())

    @unittest.expectedFailure
    def test_migraciones_consistentes_con_los_modelos(self):
        """
        FALLO CONOCIDO (MIG). Bug: Availability.Meta (verbose_name 'Bloqueo') no
        está reflejada en las migraciones; makemigrations propone
        0002_alter_availability_options.
        Reproducción: python manage.py makemigrations --check --dry-run (sale con código 1).
        Origen: ISSUE-07. El PR #15 lo corrige; cuando se integre, este test dará
        "unexpected success" y habrá que quitar la marca expectedFailure.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=io.StringIO())
        except SystemExit:
            self.fail("Hay cambios de modelo sin migración (makemigrations --check devolvió código != 0).")


# ------------------------------------------------------------ fallos conocidos

class FallosConocidosApiTests(RegresionBase):
    """Cada test afirma el comportamiento CORRECTO; hoy fallan (expectedFailure)."""

    def setUp(self):
        super().setUp()
        self.cliente = Client(raise_request_exception=False)
        self.cliente.force_login(self.user)

    def cuerpo_crudo(self, repeat_weeks_json):
        return (
            '{"resource_id": %d, "start_time": "%s", "end_time": "%s", "repeat_weeks": %s}'
            % (self.resource.id, self.start.isoformat(), self.end.isoformat(), repeat_weeks_json)
        )

    @unittest.expectedFailure
    def test_h1_repeat_weeks_infinito_devuelve_400(self):
        """
        FALLO CONOCIDO H1. Bug: int(float('inf')) lanza OverflowError no capturado.
        Reproducción: POST /api/reservas/crear/ con el JSON crudo "repeat_weeks":1e999
        -> hoy 500; esperado 400.
        Origen: ISSUE-02.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        response = self.post_crear(self.cuerpo_crudo("1e999"), client=self.cliente)
        self.assertEqual(response.status_code, 400)

    @unittest.expectedFailure
    def test_h2_fecha_maxima_con_repeticion_devuelve_400(self):
        """
        FALLO CONOCIDO H2. Bug: start_time + timedelta(weeks=1) desborda en 9999-12-31
        y lanza OverflowError no capturado.
        Reproducción: start_time 9999-12-31T10:00:00Z, end_time 9999-12-31T11:00:00Z,
        repeat_weeks 1 -> hoy 500; esperado 400.
        Origen: ISSUE-02.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        cuerpo = self.payload(
            start_time="9999-12-31T10:00:00Z", end_time="9999-12-31T11:00:00Z", repeat_weeks=1)
        response = self.post_crear(cuerpo, client=self.cliente)
        self.assertEqual(response.status_code, 400)

    @unittest.expectedFailure
    def test_h3_json_profundamente_anidado_devuelve_400(self):
        """
        FALLO CONOCIDO H3. Bug: json.loads lanza RecursionError (no es ValueError)
        con anidamiento extremo.
        Reproducción: cuerpo '[' * 100000 -> hoy 500; esperado 400.
        Origen: ISSUE-02.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        response = self.post_crear("[" * 100000, client=self.cliente)
        self.assertEqual(response.status_code, 400)

    @unittest.expectedFailure
    def test_h4_resource_id_booleano_devuelve_400(self):
        """
        FALLO CONOCIDO H4. Bug: resource_id true (bool JSON) se interpreta como
        pk=1 (True == 1) y se crea la reserva en el recurso 1.
        Reproducción: POST con "resource_id": true existiendo el recurso pk=1
        -> hoy 200 y crea la reserva; esperado 400.
        Origen: ISSUE-02.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        Booking.objects.all().delete()
        Resource.objects.all().delete()
        Resource.objects.create(id=1, name="Recurso uno")
        response = self.post_crear(self.payload(resource_id=True), client=self.cliente)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)


class FallosConocidosAdminBookingTests(RegresionBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pass1234")
        self.cliente = Client(raise_request_exception=False)
        self.cliente.force_login(self.admin)

    def datos(self, inicio, fin, con_recurso=True):
        datos = {
            "user": self.user.pk,
            "start_time_0": inicio.strftime("%Y-%m-%d"),
            "start_time_1": inicio.strftime("%H:%M:%S"),
            "end_time_0": fin.strftime("%Y-%m-%d"),
            "end_time_1": fin.strftime("%H:%M:%S"),
            "_save": "Guardar",
        }
        if con_recurso:
            datos["resource"] = self.resource.pk
        return datos

    @unittest.expectedFailure
    def test_b2_admin_reserva_sin_recurso_muestra_error_de_formulario(self):
        """
        FALLO CONOCIDO B2. Bug: Booking.clean accede a self.resource cuando no hay
        recurso y lanza RelatedObjectDoesNotExist durante la validación del admin.
        Reproducción: superusuario POST /admin/reservas/booking/add/ sin 'resource'
        (user, start_time_0/1 y end_time_0/1 rellenos) -> hoy 500; esperado 200
        con error de formulario.
        Origen: ISSUE-07.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        response = self.cliente.post(
            "/admin/reservas/booking/add/", self.datos(self.start, self.end, con_recurso=False))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)

    @unittest.expectedFailure
    def test_b3_admin_no_crea_reserva_con_inicio_posterior_al_fin(self):
        """
        FALLO CONOCIDO B3. Bug: Booking.clean no valida start_time < end_time, así
        que el admin acepta una reserva con intervalo invertido.
        Reproducción: admin crea Booking con inicio 12:00 y fin 11:00
        -> hoy 302 y la crea; esperado no crearla.
        Origen: ISSUE-07.
        Decisión de César García (26/10/2026): documentado, no corregido en ISSUE-08.
        """
        inicio, fin = utc(2030, 3, 4, 12), utc(2030, 3, 4, 11)
        self.cliente.post("/admin/reservas/booking/add/", self.datos(inicio, fin))
        self.assertEqual(Booking.objects.count(), 0)
