# Informe del repositorio — Gestor de Reservas

**Repositorio:** [Proyecto1_TopicosII_GestorDeReservas](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas) (privado)
**Rama principal:** `main`
**Stack:** Django 5.2.4 (Python), SQLite, plantillas Django + CSS propio, FullCalendar,
Chart.js, Bootstrap Icons y SweetAlert2 por CDN
**Tablero Kanban:** https://github.com/users/RamsesSzobotka/projects/4

Sistema web para reservar pistas y salas: calendario de disponibilidad, reservas únicas y
recurrentes, bloqueos administrativos, perfil con datos guardados, autogestión/cancelación
de reservas, previsión de demanda para administradores y una interfaz visual unificada.

---

## 1. Historias de usuario

| # | Historia de usuario | Issue | Estado | Responsable | Pull request |
|---|---|---|---|---|---|
| HU-1 | Como **usuario recurrente**, quiero reservar directamente usando mis datos guardados, para no rellenar el formulario de pago en cada compra. | [#3](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/3) | Cerrado | Cesar Garcia (@CesarGarcia08) | [#17](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/17) |
| HU-2 | Como **cliente**, quiero ver un calendario dinámico con los días disponibles y ocupados, para elegir mi fecha sin intentos fallidos. | [#4](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/4) | Cerrado | Cesar Garcia (@CesarGarcia08) | [#16](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/16) |
| HU-3 | Como **administrador**, quiero ver gráficos de previsión de la demanda basados en el histórico, para ajustar precios e inventario. | [#5](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/5) | Cerrado | Gerald (@Gerxld) | [#13](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/13) |
| HU-4 (adicional 1) | Como **cliente**, quiero ver y cancelar mis próximas reservas, para gestionar cambios sin contactar a un administrador. | [#6](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/6) | Cerrado | Gerald (@Gerxld) | [#14](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/14) → [#15](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/15) |
| HU-5 (adicional 2) | Como **administrador**, quiero gestionar recursos y bloqueos de indisponibilidad con validación, para que no se reserve capacidad no disponible. | [#7](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/7) | Cerrado | Ramses Szobotka (@RamsesSzobotka) | [#12](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/12) |

> HU-4 tiene dos PR porque el #14 se fusionó por error en `feature/5-prevision-demanda` y no en
> `main`; el #15 lleva el mismo contenido a `main`.
>
> GitHub tiene **9 pull requests en total (#10–#18)** y este informe referencia esos mismos 9.
> El #14 y el #15 son dos PR distintos con el mismo contenido, no un commit repetido.
> Cada issue documenta su propio registro de IA en
> [doc/AI_Development_Log.log](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/AI_Development_Log.log).

---

## 2. Issues de soporte (no son historias de usuario)

| Issue | Tipo | Estado | Responsable | Pull request |
|---|---|---|---|---|
| [#1](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/1) Estabilizar la línea base | Fundación técnica | Cerrado | Ramses Szobotka (@RamsesSzobotka) | [#10](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/10) |
| [#2](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/2) Endurecer reservas y recurrencia | Reserva central | Cerrado | Ramses Szobotka (@RamsesSzobotka) | [#11](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/11) |
| [#8](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/8) Suite de pruebas y regresión | Calidad / QA | Cerrado | Cesar Garcia (@CesarGarcia08) | [#18](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/18) |
| [#9](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/issues/9) Rediseñar la interfaz de la aplicación | Interfaz / diseño | Cerrado | Gerald (@Gerxld) | [#19](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/19) |

---

## 3. Reparto de trabajo

| Integrante | Issues resueltos |
|---|---|
| Ramses Szobotka (@RamsesSzobotka) | #1, #2, #7 |
| Cesar Garcia (@CesarGarcia08) | #3, #4, #8 |
| Gerald (@Gerxld) | #5, #6 y #9 |

Issues cerrados con PR fusionado: 9 de 9. El #9 cerró el rediseño visual de la aplicación
mediante el PR #19.

---

## 4. Evidencia y documentación

| Documento | Contenido |
|---|---|
| [`doc/AI_Development_Log.log`](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/AI_Development_Log.log) | Registro de uso de IA, decisiones humanas, respuestas incorrectas y sugerencias rechazadas. Cada línea incluye el issue, la actividad, las validaciones y la referencia al commit/PR |
| [`doc/PRUEBAS.md`](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/PRUEBAS.md) | Comandos, resultados reales y matriz criterio → test |
| [`doc/PRUEBAS_E2E_PLAYWRIGHT.md`](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/PRUEBAS_E2E_PLAYWRIGHT.md) | Pruebas end-to-end manuales en navegador |
| [`doc/ISSUE_PLAN.md`](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/ISSUE_PLAN.md) | Plan original de issues, dependencias y rotación de roles |
| [`doc/capturas/`](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/tree/main/doc/capturas) | Capturas de evidencia de pruebas y del rediseño de interfaz del issue #9 |

### Cambios del issue #9 — Rediseño de interfaz

El issue #9 se reorientó desde la documentación del README al rediseño visual de la
aplicación y quedó cerrado con el [PR #19](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/pull/19).
Los cambios principales fueron:

- Se creó una hoja de estilos compartida en `reservas/static/css/style.css`, con variables
  de color, tipografía, tarjetas, tablas, badges, alertas, botones y formularios.
- `base.html` pasó a ser el layout común, con navbar, estado activo, mensajes flash y
  bloques compartidos para las siete plantillas de la aplicación.
- Se rediseñaron las vistas de inicio, login, calendario, mis reservas, perfil y previsión,
  manteniendo los textos, la lógica de negocio y los flujos existentes.
- Se sustituyeron emojis y glifos de flecha por iconos de Bootstrap Icons.
- Se reemplazaron las llamadas nativas `alert()`, `confirm()` y `prompt()` por diálogos
  SweetAlert2, incluyendo confirmaciones para crear y cancelar reservas y cancelar series.
- Se añadieron trece capturas `v2-interfaz-*.png`, incluida evidencia de uso en pantalla
  pequeña y de los diálogos integrados.

Validaciones declaradas en el PR: `python manage.py check` sin problemas, `python manage.py
test` con 190 pruebas ejecutadas y 9 fallos esperados, y búsqueda regex sin llamadas nativas
a `alert`, `confirm` o `prompt` en HTML/JavaScript.

Las entradas están en orden cronológico y cada línea indica el issue al que pertenece; el archivo
no tiene secciones por issue, por lo que se localizan con búsqueda (`#3`, `#4`, …) dentro del
[log de IA](https://github.com/RamsesSzobotka/Proyecto1_TopicosII_GestorDeReservas/blob/main/doc/AI_Development_Log.log).

---

## 5. Tablero Kanban

https://github.com/users/RamsesSzobotka/projects/4
