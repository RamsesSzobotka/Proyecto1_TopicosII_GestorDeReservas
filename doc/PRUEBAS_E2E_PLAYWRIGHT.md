# Pruebas E2E con Playwright — ISSUE-07 (gestión administrativa de recursos y bloqueos)

**Fecha:** 2026-10-20
**Issue relacionada:** #7 (cerrada con el PR #12)
**Herramienta:** Playwright MCP (navegador Chromium), sobre `manage.py runserver`
**Alcance:** verificación en navegador real del flujo de bloqueos administrativos, el calendario
del cliente y los permisos del panel. Complementa a los 37 tests automatizados de
`reservas/tests.py`.

> **Estado de estas pruebas:** documento y capturas son **locales**, pendientes de revisión del
> equipo. **No se subió nada a GitHub** (no hay commit, rama ni PR de este trabajo).

---

## 1. Entorno de pruebas

Las pruebas se ejecutaron contra una **base de datos aislada en el directorio temporal**, para no
modificar el `db.sqlite3` que está versionado en el repositorio.

| Elemento | Valor |
|---|---|
| Settings | Módulo temporal `test_settings.py` que importa `gestor_reservas.settings` y sobrescribe `DATABASES` |
| Base de datos | `%TEMP%\opencode\pwtest\e2e.sqlite3` (nunca `db.sqlite3` del repo) |
| Servidor | `venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765 --settings=test_settings --noreload` |
| Navegador | Chromium (Playwright MCP), zona horaria `America/Bogota` (UTC-5) |
| Datos | 1 recurso con reservas y bloqueos, 1 recurso vacío, 3 usuarios (superusuario, staff sin permisos, cliente) |

Datos sembrados (todos en UTC):

| Tipo | Recurso | Inicio | Fin |
|---|---|---|---|
| Reserva (`cliente`) | Pista de padel | mié 21/10 16:00 | mié 21/10 17:00 |
| Bloqueo | Pista de padel | jue 22/10 16:00 | jue 22/10 18:00 |

### Usuarios de prueba

| Usuario | Contraseña | Perfil |
|---|---|---|
| `admin` | Admin12345 | superusuario (`is_staff=True`, todos los permisos) |
| `staff` | Staff12345 | `is_staff=True` **sin ningún permiso** de modelo |
| `cliente` | Cliente12345 | usuario normal (sin `is_staff`) |

---

## 2. Resultados

15 escenarios. **15 PASS / 0 FAIL.**

| # | Escenario | Resultado esperado | Resultado observado | Estado |
|---|---|---|---|---|
| E2E-01 | Home lista los recursos y enlaza al calendario | 2 tarjetas con enlace a `calendario_full` | "Pista de padel", "Pista de tenis" → `/calendario_full/1/`, `/calendario_full/2/` | PASS |
| E2E-02 | El calendario carga FullCalendar | `typeof FullCalendar !== 'undefined'`, eventos presentes | FullCalendar cargado; 4 eventos (3 bloqueos + 1 reserva) | PASS |
| E2E-03 | Se llama a los dos endpoints de eventos | GET a `/api/reservas/` **y** a `/api/bloqueos/` | Ambos `200 OK` con el rango visible `2026-10-18 → 2026-10-25` | PASS |
| E2E-04 | Bloqueo y reserva se distinguen visualmente | Colores distintos y título del bloqueo | `Bloqueado` en rojo (`#ef4444`), `Reservado por cliente` en verde (`#10b981`) | PASS |
| E2E-05 | Seleccionar una franja **bloqueada** | Alerta "Esta franja horaria está bloqueada por el administrador." | Alerta exacta mostrada; no se abre el diálogo de reserva | PASS |
| E2E-06 | Seleccionar una franja **con reserva** | Alerta "Ya existe una reserva en esta franja horaria." | Alerta exacta mostrada | PASS |
| E2E-07 | Seleccionar una franja **libre** | Diálogo "¿Quieres crear una reserva desde … hasta …?" | Diálogo de confirmación con el rango exacto | PASS |
| E2E-08 | Franja que empieza justo al **terminar** el bloque | Se permite (intervalo semiabierto: no hay solape) | Confirmación de reserva ofrecida | PASS |
| E2E-09 | El botón de refresco vuelve a pedir los datos | Nuevas peticiones a `/api/reservas/` y `/api/bloqueos/` | 2 peticiones nuevas tras el clic; los eventos se mantienen | PASS |
| E2E-10 | Reserva sobre un bloqueo vía **API** | HTTP 409 con el detalle del conflicto | `409` — `{"success": false, "error": "Conflicto: hay un bloqueo en la semana 1 (2026-10-22 16:00:00+00:00)."}` | PASS |
| E2E-11 | Admin: **intervalo invertido** (fin 16:00 < inicio 18:00) | Error de validación y **no** se crea el bloqueo | Error junto al campo: "El fin del bloqueo debe ser posterior al inicio."; sigue en el formulario; `Availability` sigue con 1 registro | PASS |
| E2E-12 | Admin: **bloque válido** | Se guarda y aparece en el listado | "The Bloqueo … was added successfully."; el listado muestra el bloque nuevo | PASS |
| E2E-13 | Admin: bloque que **solapa una reserva** | Aviso (no error) y la reserva se conserva | Aviso ámbar: "El bloqueo se guardó, pero se solapa con 1 reserva(s) existente(s). Las reservas se mantienen y el bloqueo solo impide reservas nuevas."; la reserva sigue en la BD | PASS |
| E2E-14 | Admin: **borrar un bloque** | El bloque desaparece del calendario del cliente y la reserva solapada se conserva | El bloque borrado desapareció del calendario **sin recargar la página** (tras el refresco); la reserva sigue en la BD | PASS |
| E2E-15 | Permisos del panel | `staff` sin permisos → 403; usuario no staff → 302 al login del admin | `staff`: 403 en `availability/add/`, `availability/` y `booking/add/`. `cliente`: el login del admin lo rechaza ("…for a staff account") y `/admin/…` responde **302** a `/admin/login/?next=…` | PASS |

### E2E-14 en detalle (extremo a extremo)

Es la prueba que valida el criterio *"El calendario refleja los cambios de bloques después de
actualizar"*, que antes de ISSUE-07 no se cumplía (los bloqueos iban embebidos en el HTML):

1. La pestaña del calendario del cliente se cargó con 3 bloques y 1 reserva (**4 eventos**).
2. En otra pestaña, el admin borró el bloque del viernes.
3. En la pestaña del cliente se pulsó **"🔄 Actualizar Reservas y Bloqueos"** sin recargar la página.
4. Resultado: la pestaña pasó de **4 eventos a 3** — el bloque borrado desapareció y la reserva se mantuvo.

---

## 3. Evidencia

| Captura | Qué muestra |
|---|---|
| [`capturas/prueba-e2e-01-calendario.png`](capturas/prueba-e2e-01-calendario.png) | Calendario del cliente: bloqueos en rojo, reserva en verde, bloque y reserva solapados el mismo día |
| [`capturas/prueba-e2e-02-admin-aviso-solape.png`](capturas/prueba-e2e-02-admin-aviso-solape.png) | Panel admin: aviso ámbar de solape con 1 reserva existente + mensaje de guardado |
| [`capturas/prueba-e2e-03-admin-error-intervalo.png`](capturas/prueba-e2e-03-admin-error-intervalo.png) | Panel admin: error "El fin del bloqueo debe ser posterior al inicio." en el formulario de alta |

---

## 4. Cómo reproducir

```powershell
# 1) Base de datos aislada (nunca el db.sqlite3 del repo)
$env:PYTHONPATH = "$env:TEMP\opencode\pwtest"
venv\Scripts\python.exe manage.py migrate --settings=test_settings
venv\Scripts\python.exe "$env:TEMP\opencode\pwtest\seed.py"

# 2) Servidor
$env:PYTHONPATH = "$env:TEMP\opencode\pwtest"
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765 --settings=test_settings --noreload

# 3) Playwright MCP: navegar a http://127.0.0.1:8765/
```

Los pasos manuales exactos de cada escenario (coordenadas del arrastre, selectores del admin,
mensajes esperados) están descritos en la tabla de la sección 2.

---

## 5. Hallazgos

### 5.1 Comportamiento verificado como correcto

- La UI avisa **antes** de dejar reservar: la comprobación en el cliente (`isBlocked` / `isReserved`)
  lee los eventos ya cargados en el calendario, no una copia estática.
- El **servidor es la autoridad**: incluso saltándose la comprobación del navegador, la API
  responde 409 y `Booking.clean()` rechaza la reserva en el panel.
- La **política acordada se respeta de extremo a extremo**: un bloque puede solaparse con una
  reserva; la reserva no se toca ni se cancela; borrar el bloque no afecta a la reserva.
- Los **permisos del panel** funcionan por modelo: un `is_staff` sin permisos no ve ni el listado
  (403), y un usuario normal es expulsado con 302.

### 5.2 Observaciones (no bloquean ISSUE-07)

| # | Observación | Dónde | Impacto |
|---|---|---|---|
| O-1 | `api_reservas` expone el **nombre de usuario** del cliente a cualquier visitante (el calendario es público) | `reservas/views.py:api_reservas` | Es una decisión previa al proyecto, ajena a ISSUE-07. Si el equipo lo considera dato personal, conviene ofuscar el nombre (p. ej. "Reservado") en una issue aparte. |
| O-2 | `favicon.ico` devuelve 404 en todas las páginas | proyecto | Cosmético, preexistente. |
| O-3 | El panel admin no muestra enlace de borrado por fila; hay que usar la acción "Delete selected" | Django admin | Comportamiento estándar de Django 5 con `list_display` explícito. No es un defecto, pero conviene que el equipo lo sepa. |
| O-4 | `manage.py makemigrations --check` sigue reportando `0002_alter_availability_options.py` | `reservas/migrations/` | Deriva **preexistente** en `main` (las `Meta.options` de `Availability` nunca se capturaron en `0001_initial`). Ajeno a ISSUE-07. |
| O-5 | La comprobación visual del calendario cubre el rango visible de la semana | `calendario_full.html` | El endpoint devuelve **todos** los bloqueos del recurso (ignora el rango que envía FullCalendar), así que el cliente los conserva todos en memoria. Aun así, el servidor sigue siendo la autoridad. |

### 5.3 Limitaciones de estas pruebas

- **No son tests automatizados**: se ejecutaron de forma interactiva con Playwright MCP y se
  documentaron paso a paso. Para que el equipo los repita en cada entrega habría que convertir
  este documento en un script de Playwright (`playwright test`), lo que añadiría dependencias de
  Node al proyecto.
- **Solo Chromium**: no se probó Firefox ni WebKit.
- **Sin tests de accesibilidad ni de responsive** en el calendario.
- **Zona horaria única**: todo se validó con el navegador en `America/Bogota` (UTC-5). No se
  comprobó el comportamiento con el navegador en UTC ni en una zona con cambio de hora.
- No se ejercitó la **reserva recurrente** (`repeat_weeks > 0`) desde el navegador: solo se
  verificó el rechazo de un bloqueo en la primera ocurrencia.
- No se probó el flujo de **cancelación** de reservas (pertenece a ISSUE-06).

---

## 6. Relación con los tests automatizados

| Criterio de ISSUE-07 | Test automatizado (`reservas/tests.py`) | Prueba E2E |
|---|---|---|
| Solo administradores autorizados | `AdminBloqueosTests` (6 tests: no staff, staff sin/con permiso, permisos por modelo) | E2E-15 |
| Intervalos inválidos rechazados | `AvailabilityCleanTests` (4 tests) | E2E-11 |
| Un bloque no se puede reservar (UI ni API) | `BookingCleanTests.test_clean_rechaza_solape_con_bloqueo`, `ApiCrearReservaTests.test_bloqueo_devuelve_409` | E2E-05, E2E-10 |
| El calendario refleja los cambios | (no era testeable sin navegador) | **E2E-14** |
| Política documentada | (no aplica) | E2E-13 (comportamiento) + `README.md` (texto) |
| Tests de validación y rechazo | 37 tests en total | Complementa a ellos |
