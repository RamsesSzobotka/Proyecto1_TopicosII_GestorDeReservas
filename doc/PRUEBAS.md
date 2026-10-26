# Suite de pruebas y regresión — ISSUE-08 (fase A)

**Fecha de ejecución:** 26/10/2026
**Issue:** #8 — Construir la suite automatizada de pruebas y regresión
**Base:** `main` en el commit `7d56870` (integradas ISSUE-01, 02, 05 y 07)
**Estado:** fase A (lo que se puede verificar sobre `main`). La fase B (unificar la suite tras
integrar los PR abiertos #15, #16 y #17) se hará después.

---

## 1. Cómo ejecutar la suite

Desde un entorno limpio (Windows, PowerShell; en Linux/macOS cambiar la ruta de activación):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py test reservas
```

Ese es el comando documentado de la suite. Para ver cada test: `python manage.py test reservas -v 2`.
Para ejecutar solo la suite de regresión: `python manage.py test reservas.test_regresion`.

### Cobertura (opcional)

`coverage` **no** está en `requirements.txt` (no se añadió ninguna dependencia). Para medirla:

```powershell
pip install coverage
coverage run manage.py test reservas
coverage report -m --include="reservas/*"
```

### Aislamiento de la base de datos

Django crea una base de datos de test **independiente** (SQLite en memoria) y la destruye al
terminar. Los tests nunca leen ni escriben `db.sqlite3`, por lo que no dependen del estado de la BD
local. Los tests nuevos usan fechas fijas (año 2030) y solo congelan `django.utils.timezone.now`
con `unittest.mock.patch` cuando la vista lo consulta (vista `calendario`). Los tests antiguos de
`reservas/tests.py` calculan algunas fechas a partir del reloj (`base_futura()`), pero siempre en
el futuro, sin depender de datos persistidos.

---

## 2. Resultado real

| Ejecución | Comando | Resultado |
|---|---|---|
| Worktree de ISSUE-08 | `python manage.py check` | `System check identified no issues (0 silenced).` |
| Worktree de ISSUE-08 | `python manage.py test reservas` | `Ran 94 tests in 23.894s` — `OK (expected failures=10)` |
| Entorno limpio (ver 2.1) | `python manage.py test reservas` | `Ran 94 tests in 26.821s` — `OK (expected failures=10)` |
| Cobertura (coverage 7.17.0) | `coverage run manage.py test reservas` | Medida en la versión previa a la revisión (93 tests, 7 fallos esperados); cobertura total de `reservas/*` 98 % (ver 2.2) |

Desglose: 61 tests de `reservas/tests.py` (sin cambios) + 33 de `reservas/test_regresion.py`
(23 normales + 10 `expectedFailure`). **0 fallos inesperados, 0 errores, 0 éxitos inesperados.**
Los 10 fallos esperados son defectos reales de `main` documentados (sección 5); no se ocultaron ni
eliminaron. La suite también pasa con `--reverse` y `--shuffle` (sin dependencias de orden).

### 2.1 Entorno limpio

Se copió el repositorio con `git archive HEAD` más `reservas/test_regresion.py` a un directorio
temporal fuera del repo (`%TEMP%`), se creó un `venv` nuevo (Python 3.14.7), se ejecutó
`pip install -r requirements.txt` (solo Django 5.2.4, asgiref, sqlparse, tzdata) y se comprobó que
no existía `db.sqlite3`. Resultado de `python manage.py test reservas`:
`Ran 94 tests in 26.821s`, `OK (expected failures=10)`. Tras la ejecución seguía sin existir
`db.sqlite3` (los tests no crean base de datos en disco). El directorio temporal se borró después.

### 2.2 Cobertura medida (`coverage report -m --include="reservas/*"`)

| Módulo | Cobertura | Líneas sin cubrir |
|---|---|---|
| `reservas/views.py` | 90 % | 56-79 (`calendario_navegable`, código muerto: no tiene ruta), 196-197 (`except (ValueError, ValidationError)` de `api_crear_reserva`) |
| `reservas/models.py` | 98 % | 82 (`raise` de bloqueo en `Booking.clean`; las pruebas de bloqueo se hacen por la API, que lo comprueba antes) |
| `admin.py`, `forecast.py`, `urls.py`, comando `crear_reservas_demo` | 100 % | — |
| Total `reservas/*` (incluye los propios tests) | 98 % | — |

---

## 3. Matriz de trazabilidad: historias de usuario → criterios de aceptación → tests

Los criterios de aceptación (AC) provienen de `doc/ISSUE_PLAN.md`. `T` = `reservas/tests.py`,
`R` = `reservas/test_regresion.py`. «No automatizable» indica AC verificados por revisión o
documentación, no por un test.

### ISSUE-01 — Línea base (integrada)

| AC | Tests |
|---|---|
| El proyecto arranca con la configuración local documentada | **No automatizable** (arranque con `runserver`); verificado indirectamente por el entorno limpio de la sección 2.1. `T: VistasTests.test_home_carga` y `test_calendario_full_carga` solo comprueban que las vistas principales responden |
| Migraciones y comprobaciones del sistema correctas | `R: IntegridadProyectoTests.test_check_sin_errores`; `R: IntegridadProyectoTests.test_migraciones_consistentes_con_los_modelos` (**expectedFailure MIG**, ver sección 5) |
| Reglas de reserva reflejadas en tests | `T: BookingCleanTests.*` (solape, sin solape, bloqueo), `T: ApiCrearReservaTests.*` (autenticación, recurso, intervalo, zona horaria, conflicto) |
| No se elimina funcionalidad existente | Cubierto por la regresión completa; `R: LoginLogoutTests.*`, `R: CalendarioSemanalTests.*`, `R: CrearReservasDemoTests.*`, `R: StrModelosTests.*` fijan funcionalidad previa |
| Limitaciones y defectos conocidos documentados | **Documental**: sección 5 de este documento (10 fallos conocidos con su test) |

### ISSUE-02 — Creación de reservas y recurrencia (integrada)

| AC | Tests |
|---|---|
| No autenticados no pueden reservar | `T: ApiCrearReservaTests.test_sin_login_devuelve_403`, `T: CsrfApiCrearReservaTests.test_post_sin_token_csrf_rechazado` |
| Intervalos inválidos/invertidos/faltantes/mal formados → error de cliente | `T: ApiCrearReservaTests.test_start_mayor_o_igual_que_end_devuelve_error`, `test_start_time_faltante_devuelve_400`, `test_formato_datetime_invalido_devuelve_400`, `test_datetime_sin_timezone_devuelve_400`, `test_cuerpo_json_no_objeto_devuelve_400`, `test_repeat_weeks_fuera_de_rango_devuelve_400`, `test_repeat_weeks_no_entero_devuelve_400`, `test_recurso_inexistente_devuelve_error`; `R: ApiCrearReservaRegresionTests.test_get_devuelve_405`, `test_cuerpo_no_json_devuelve_400`, `test_falta_resource_id_devuelve_400`. Huecos documentados: **H1, H2, H3, H4** (expectedFailure) |
| Solape con reserva o bloqueo se rechaza | `T: ApiCrearReservaTests.test_bloqueo_devuelve_409`, `test_solape_parcial_con_reserva_existente_devuelve_409` |
| Petición recurrente atómica | `T: ApiCrearReservaTests.test_repeticion_con_conflicto_no_crea_nada`; `R: ApiCrearReservaRegresionTests.test_integrity_error_en_segunda_ocurrencia_devuelve_409_sin_parciales` |
| Respuesta exitosa con las ocurrencias creadas | `T: ApiCrearReservaTests.test_crea_reserva_exitosa`, `test_limite_52_semanas_crea_53_ocurrencias`, `T: CsrfApiCrearReservaTests.test_post_con_token_csrf_aceptado`; `R: ApiCrearReservaRegresionTests.test_52_semanas_crean_53_reservas_con_fechas_exactas` (fechas semana a semana) |
| Tests cubren normal, frontera, conflicto y error | Conjunto de los anteriores (frontera: 52/53 semanas, `start == end`) |

### ISSUE-05 — Previsión de la demanda (integrada)

| AC | Tests |
|---|---|
| Solo administradores autorizados acceden | `T: PrevisionDemandaTests.test_anonimo_redirige_al_login_de_admin`, `test_usuario_normal_redirige`, `test_staff_inactivo_redirige`, `test_staff_accede`, `test_post_devuelve_405`, `test_home_muestra_enlace_solo_a_staff` |
| El gráfico se basa en el histórico persistido e identifica el recurso | `T: PrevisionDemandaTests.test_agregacion_exacta_por_semana`, `test_aislamiento_entre_recursos`, `test_semana_parcial_se_marca_y_borde_desde_incluido`, `test_con_datos_muestra_grafico_aviso_y_json` |
| Datos vacíos o historial insuficiente → estado comprensible | `T: PrevisionDemandaTests.test_sin_reservas_estado_comprensible`, `test_historial_insuficiente_estado_comprensible`, `test_sin_recurso_muestra_selector_y_estado_vacio` |
| Agregación determinista y probada con fixtures conocidas | `T: PrevisionDemandaTests.test_media_movil_exacta`, `test_media_movil_solo_usa_las_ultimas_semanas_completas`, `test_determinismo`, `test_rango_por_defecto` |
| La interfaz no cambia precios ni inventario | `T: PrevisionDemandaTests.test_la_vista_no_modifica_la_base_de_datos`, `test_post_devuelve_405` |
| Tests de permisos, agregación, rangos y vacío | `T: PrevisionDemandaTests.test_fecha_invalida`, `test_desde_igual_o_posterior_a_hasta`, `test_rango_mayor_a_52_semanas`, `test_rango_de_exactamente_52_semanas_es_valido`, `test_recurso_inexistente_o_invalido`, `test_agregar_rechaza_rango_invertido` |

### ISSUE-07 — Gestión administrativa de recursos y bloqueos (integrada)

| AC | Tests |
|---|---|
| Solo administradores autorizados crean/editan/eliminan bloqueos | `T: AdminBloqueosTests.test_usuario_no_staff_no_entra_al_admin`, `test_staff_sin_permiso_no_puede_crear_bloqueo`, `test_staff_con_permiso_puede_crear_bloqueo`, `test_staff_sin_permiso_no_puede_crear_reserva`; `R: AdminRegresionTests.test_resource_anonimo_redirige_al_login_del_admin`, `test_resource_staff_sin_permiso_recibe_403`, `test_resource_staff_con_permiso_add_puede_crear` |
| Intervalos de bloque inválidos se rechazan | `T: AvailabilityCleanTests.test_clean_rechaza_intervalo_invertido`, `test_clean_rechaza_intervalo_de_duracion_cero`, `test_clean_permite_intervalo_valido`; `T: AdminBloqueosTests.test_admin_rechaza_intervalo_invertido` |
| Un intervalo bloqueado no se puede reservar (UI/API) | `T: BookingCleanTests.test_clean_rechaza_solape_con_bloqueo`, `T: ApiCrearReservaTests.test_bloqueo_devuelve_409` |
| El calendario refleja los cambios de bloques | `T: ApiBloqueosTests.test_devuelve_solo_los_bloqueos_del_recurso`, `test_recurso_sin_bloqueos_devuelve_lista_vacia`, `test_api_reservas_incluye_el_tipo_reserva`, `test_calendario_full_carga_bloqueos_desde_la_api` |
| Política documentada para bloqueos que solapan reservas (la reserva existente gana) | `T: AvailabilityCleanTests.test_clean_permite_bloqueo_que_solapa_reserva_existente`, `T: AdminBloqueosTests.test_admin_avisa_reservas_solapadas`; `R: AdminRegresionTests.test_borrar_bloqueo_conserva_reservas_solapadas` |
| Tests de validación Admin/modelo y rechazo de reservas | Conjunto de los anteriores; `R: StrModelosTests.*`. Huecos documentados: **B2, B3** (admin de reservas, expectedFailure) |

### ISSUE-03, ISSUE-04 e ISSUE-06 — en PR abierto (fase B)

Sus criterios **no se verifican en esta fase**: el código no está en `main`. Se verificarán en la
fase B tras integrar los PR. Clases de test que aportan (según cada rama remota):

| Issue | PR | Rama | Clases de test que aporta |
|---|---|---|---|
| ISSUE-03 (datos de reserva guardados) | #17 | `feature/3-datos-reserva-guardados` | `PerfilReservaModeloFormTests`, `PerfilVistaTests`, `ApiDatosGuardadosTests`, `CalendarioDatosGuardadosTests` |
| ISSUE-04 (calendario dinámico) | #16 | `feature/4-calendario-dinamico` | `CalendarioEventosApiTests`, `CalendarioFullUxTests` |
| ISSUE-06 (cancelación y autogestión) | #15 | `feature/6-cancelacion-a-main` | `CancelacionBase` (base), `CancelacionPropiedadTests`, `CancelacionAccesoTests`, `CancelacionLimiteTests`, `CancelacionRepetidaTests`, `CancelacionDisponibilidadTests`, `SerieTests`, `EnlaceMisReservasTests` |

Esos tres PR modifican `reservas/tests.py`; por eso esta fase no lo toca (evita conflictos). Al
integrarlos habrá que: (1) rehacer la matriz con los métodos reales, (2) ejecutar la suite
completa, (3) quitar la marca `expectedFailure` del test de migraciones si #15 se integra (daría
«unexpected success»).

---

## 4. Contenido de `reservas/test_regresion.py` (33 tests)

| Clase | Tests | Qué cubre |
|---|---|---|
| `LoginLogoutTests` | 5 | GET con formulario; login válido (redirect `/` y sesión); credenciales incorrectas y usuario inexistente (200, mensaje, sin sesión); logout (redirect `/login/`, sesión cerrada) |
| `ApiCrearReservaRegresionTests` | 5 | GET → 405; cuerpo no JSON → 400; falta `resource_id` → 400; `IntegrityError` en la 2.ª creación → 409 sin reservas parciales; 52 semanas → 53 reservas con fechas exactas |
| `CalendarioSemanalTests` | 4 | `/calendario/<id>/`: reservas de la semana actual en el contexto (reloj congelado), semana vacía, 404, plantilla (expectedFailure C1) |
| `AdminRegresionTests` | 4 | Borrar bloqueo conserva reservas solapadas; permisos sobre `Resource` (anónimo, staff sin permiso, staff con `add_resource`) |
| `StrModelosTests` | 3 | `__str__` de `Resource`, `Availability`, `Booking` |
| `CrearReservasDemoTests` | 4 | Crea usuario, recurso y 15 reservas; idempotencia; no borrar reservas ajenas (expectedFailure D1); sin avisos de datetimes naive (expectedFailure D2) |
| `IntegridadProyectoTests` | 2 | `check` sin errores; migraciones consistentes (expectedFailure MIG) |
| `FallosConocidosApiTests` | 4 | H1, H2, H3, H4 (expectedFailure) |
| `FallosConocidosAdminBookingTests` | 2 | B2, B3 (expectedFailure) |

---

## 5. Fallos conocidos (decisión de César García, 26/10/2026: documentados, NO corregidos en ISSUE-08)

Cada test afirma el comportamiento **correcto** y lleva `@unittest.expectedFailure`. Se comprobó,
ejecutándolos sin la marca, que fallan por la razón descrita (no por un error del propio test).

| ID | Test (`R: …`) | Reproducción | Hoy | Esperado | Origen | Estado |
|---|---|---|---|---|---|---|
| H1 | `FallosConocidosApiTests.test_h1_repeat_weeks_infinito_devuelve_400` | POST `/api/reservas/crear/` con JSON crudo `"repeat_weeks":1e999` | 500 (`OverflowError`) | 400 | ISSUE-02 | Abierto, documentado |
| H2 | `FallosConocidosApiTests.test_h2_fecha_maxima_con_repeticion_devuelve_400` | `start_time` `9999-12-31T10:00:00Z`, `end_time` `…11:00:00Z`, `repeat_weeks` 1 | 500 (`OverflowError`) | 400 | ISSUE-02 | Abierto, documentado |
| H3 | `FallosConocidosApiTests.test_h3_json_profundamente_anidado_devuelve_400` | Cuerpo `'[' * 100000` | 500 (`RecursionError`) | 400 | ISSUE-02 | Abierto, documentado |
| H4 | `FallosConocidosApiTests.test_h4_resource_id_booleano_devuelve_400` | `"resource_id": true` con el recurso pk=1 existente | 200 y crea la reserva en pk=1 | 400 | ISSUE-02 | Abierto, documentado |
| B2 | `FallosConocidosAdminBookingTests.test_b2_admin_reserva_sin_recurso_muestra_error_de_formulario` | Superusuario: POST `/admin/reservas/booking/add/` sin `resource` (user y fechas rellenos) | 500 (`RelatedObjectDoesNotExist` en `Booking.clean`) | 200 con error de formulario | ISSUE-07 | Abierto, documentado |
| B3 | `FallosConocidosAdminBookingTests.test_b3_admin_no_crea_reserva_con_inicio_posterior_al_fin` | Admin crea `Booking` con inicio 12:00 y fin 11:00 | 302 y la crea | No crearla | ISSUE-07 | Abierto, documentado |
| C1 | `CalendarioSemanalTests.test_c1_plantilla_muestra_las_reservas_de_la_semana` | Reserva el lunes 14/01/2030 09:00 y abre `/calendario/<id>/` esa semana | La plantilla pinta «Libre» los 7 días (`reservas_por_dia.fecha` busca la clave literal «fecha») | Muestra `09:00 - 10:00` y 6 días libres | Código base | Abierto, documentado |
| D1 | `CrearReservasDemoTests.test_d1_no_borra_reservas_ajenas` | Crear una reserva de otro usuario y ejecutar `crear_reservas_demo` | La borra (`Booking.objects.all().delete()`) | Conservarla | Código base | Abierto, documentado |
| D2 | `CrearReservasDemoTests.test_d2_no_emite_avisos_de_datetimes_naive` | `python -W always manage.py crear_reservas_demo` | 30 `RuntimeWarning` (`datetime.now()` naive con `USE_TZ=True`) | Ningún aviso | Código base | Abierto, documentado |
| MIG | `IntegridadProyectoTests.test_migraciones_consistentes_con_los_modelos` | `python manage.py makemigrations --check --dry-run` | Sale con código 1 (propone `0002_alter_availability_options` por la deriva de `Meta` de `Availability`) | Sin cambios pendientes | ISSUE-07 | El PR #15 lo corrige; al integrarlo este test dará «unexpected success» y habrá que quitar la marca |

Verificación realizada sin la marca: H1, H2, H3 y B2 fallan con `500 != 400/200` (la excepción
subyacente indicada es la verificada manualmente por el orquestador en `main`; el test solo
comprueba el código de estado); H4 falla con `200 != 400`; B3 con `1 != 0` (la reserva se creó);
MIG falla con el `SystemExit` de `makemigrations --check` convertido en `self.fail`;
C1 con `Couldn't find '09:00 - 10:00'`; D1 con `False is not true` (la reserva ajena se borró);
D2 con la lista de `RuntimeWarning` distinta de `[]`.

C1, D1 y D2 se detectaron durante esta issue. En la primera versión D1 y D2 se fijaban como
comportamiento actual; el advisor señaló que eso convertía un defecto en contrato y se pasaron al
mismo formato `expectedFailure` que el resto (decisión de César García de documentar sin corregir).

### Otros hallazgos (sin test)

- **`calendario_navegable` es código muerto**: no tiene ruta en `urls.py`; no se prueba.

---

## 6. Limitaciones

- Esta es la fase A: ISSUE-03, 04 y 06 no están verificadas (viven en PR abiertos).
- No hay pruebas de navegador (JavaScript de FullCalendar, Chart.js); existen pruebas E2E manuales
  en `doc/PRUEBAS_E2E_PLAYWRIGHT.md` para ISSUE-07.
- La causa exacta de H1-H3 (tipo de excepción) proviene de la verificación manual previa; los
  tests comprueban el código HTTP, no el tipo de excepción.
- La medición de cobertura se hizo con `coverage` instalado solo en el venv del desarrollador;
  no forma parte de `requirements.txt`.
