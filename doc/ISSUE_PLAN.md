# Plan de Issues para Revisión Humana

**Estado:** Borrador. No se ha creado ningún issue en GitHub.

**Fuente:** `doc/DSaIA-Proyecto1.pdf`, especialmente páginas 2-3:

- Tres historias de usuario obligatorias.
- Al menos dos historias de usuario adicionales.
- Desarrollo, pruebas y validación para cada historia de usuario.
- Evidencia de Git, issues, commits identificables, ramas, pull requests,
  pruebas automatizadas, uso de IA, respuestas incorrectas de la IA, cambios
  rechazados de la IA y decisiones humanas.
- Tres estudiantes rotando los roles Developer, Reviewer y QA.

## 1. Línea base actual

La aplicación seleccionada es un sistema de reservas en Django. El código
actual ya contiene:

- Modelos `Resource`, `Booking` y `Availability`.
- Vistas de login y logout.
- Un calendario de recursos basado en FullCalendar.
- Verificaciones básicas de solape y reservas recurrentes semanales.
- Registros en el Django Admin para recursos, reservas y bloques.

La línea base también necesita endurecimiento técnico antes del trabajo de
features:

- El endpoint de reserva tiene validación de entrada incompleta y captura toda
  excepción como una respuesta JSON con apariencia de éxito.
- El endpoint de reserva está exento de CSRF.
- La validación de reservas no comprueba todas las reglas de negocio, como
  intervalos válidos y bloques administrativos.
- El módulo de tests existente no tiene pruebas automatizadas.
- La aplicación no contiene actualmente un formulario de pago ni un perfil de
  pago guardado del usuario.
- La previsión de la demanda no está implementada.

Estas observaciones se incluyen para evitar escribir issues que asuman que una
funcionalidad está completa cuando solo está parcialmente presente.

## 2. Decisiones humanas requeridas antes de la implementación

### Interpretación de los datos de pago

La historia obligatoria dice:

> Como usuario recurrente, quiero reservar directamente usando mis datos
> guardados, para no tener que rellenar el formulario de pago en cada compra.

El proyecto actual no tiene proveedor de pagos ni formulario de pago. La
interpretación segura recomendada es almacenar solo datos de reserva/contacto
no sensibles y, si los pagos son realmente necesarios, usar un token de
proveedor o checkout alojado. La aplicación no debe almacenar números de
tarjeta, CVV ni otras credenciales de pago en bruto.

El equipo debe confirmar una de estas opciones antes de crear el issue de
feature:

1. **Recomendada:** perfil y datos de contacto del usuario guardados, con una
   referencia de pago simulada o con token de proveedor.
2. Integrar un proveedor de pagos aprobado sin almacenar datos de tarjeta en
   bruto.

La lista de issues asume la opción 1 hasta que el equipo decida lo contrario.

## 3. Lista propuesta de issues

Los números de issues son marcadores de posición. Asignar los números reales
de GitHub solo después de la aprobación humana.

### ISSUE-01 — Analizar y estabilizar la línea base de reservas

**Tipo:** Fundación técnica  
**Responsable sugerido:** Student A  
**Depende de:** Ninguno

**Objetivo:** Dejar ejecutable la aplicación existente y establecer la línea
base compartida antes de desarrollar las ramas de features.

**Alcance:**

- Verificar la configuración actual de Django, migraciones, URLs, plantillas
  y Admin.
- Corregir solo los defectos de línea base que impidan ejecutar o probar de
  forma segura.
- Definir las reglas de reserva soportadas: intervalo válido, existencia del
  recurso, autenticación, manejo de zona horaria y comportamiento ante
  conflictos.
- Registrar la línea base inicial de pruebas y comprobaciones de calidad.
- No implementar ninguna historia de usuario en este issue.

**Criterios de aceptación:**

- El proyecto arranca con la configuración local documentada.
- Las migraciones y las comprobaciones de sistema de Django finalizan
  correctamente.
- Las reglas de reserva acordadas están escritas en el issue y reflejadas en
  tests o notas de validación.
- No se elimina funcionalidad existente.
- Las limitaciones y defectos conocidos de la línea base están documentados.

### ISSUE-02 — Endurecer la creación de reservas y las reservas recurrentes

**Tipo:** Reserva central  
**Responsable sugerido:** Student A  
**Depende de:** ISSUE-01

**Objetivo:** Hacer fiables y seguras las reservas únicas y recurrentes.

**Alcance:**

- Validar campos JSON, ID del recurso, fechas y horas, comportamiento de zona
  horaria, orden del intervalo y el límite de semanas de repetición.
- Rechazar solapes y bloques administrativos de forma consistente.
- Asegurar que una serie recurrente no deje registros parciales cuando una
  ocurrencia entre en conflicto.
- Reemplazar el manejo amplio de excepciones por respuestas de error
  explícitas y seguras para el cliente.
- Conservar la protección CSRF o documentar y justificar el mecanismo de
  protección seleccionado.

**Criterios de aceptación:**

- Los usuarios no autenticados no pueden crear reservas.
- Intervalos inválidos, invertidos, faltantes o con formato malo se rechazan
  con un error de cliente claro.
- Una reserva que solape una reserva existente o un bloque se rechaza.
- Una petición recurrente es atómica: o crea todas las ocurrencias válidas o
  no crea ninguna.
- Las respuestas exitosas contienen las ocurrencias creadas en una forma
  documentada.
- Los tests automatizados cubren casos normales, de frontera, de conflicto y
  de error.

### ISSUE-03 — Implementar los datos de reserva guardados del usuario

**Tipo:** Historia de usuario obligatoria  
**Responsable sugerido:** Student B  
**Depende de:** ISSUE-01 y la decisión de pago anterior

**Historia de usuario:** Como usuario recurrente, quiero reservar directamente
usando mis datos guardados, para no tener que rellenar el formulario de pago
en cada compra.

**Alcance:**

- Añadir un flujo de perfil o de datos de reserva orientado al usuario según
  la interpretación aprobada.
- Rellenar previamente el flujo de reserva para usuarios autenticados.
- Permitir al usuario revisar y actualizar sus propios datos guardados.
- Mantener los datos de pago sensibles fuera de la base de datos.
- Definir el comportamiento para usuarios con datos guardados incompletos.

**Criterios de aceptación:**

- Un usuario recurrente autenticado puede completar una reserva sin volver a
  introducir los campos aprobados guardados.
- El usuario puede revisar y actualizar sus propios datos guardados.
- Otro usuario no puede leer ni modificar esos datos.
- La interfaz indica claramente qué datos se están reutilizando.
- Datos faltantes o inválidos producen un mensaje de validación accionable.
- Los tests cubren primer uso, uso repetido, actualización, control de
  acceso y datos inválidos.

### ISSUE-04 — Entregar el calendario dinámico de disponibilidad

**Tipo:** Historia de usuario obligatoria  
**Responsable sugerido:** Student B  
**Depende de:** ISSUE-01 e ISSUE-02

**Historia de usuario:** Como cliente, quiero ver un calendario dinámico con
los días disponibles y ocupados, para elegir mi fecha rápidamente sin
intentos fallidos.

**Alcance:**

- Mostrar las reservas ocupadas y los bloques administrativos de forma
  distinguible.
- Mostrar fechas u horarios disponibles según las reglas de reserva acordadas.
- Actualizar los datos después de una reserva exitosa o rechazada.
- Manejar la navegación del calendario y el formato de zona horaria de forma
  consistente.
- Mantener la validación del servidor como autoritativa; el calendario no
  debe ser la única protección contra conflictos.

**Criterios de aceptación:**

- El calendario muestra las reservas y bloques actuales del recurso
  seleccionado.
- Los estados disponibles y ocupados son visualmente distinguibles y están
  explicados.
- Seleccionar un intervalo ocupado o bloqueado evita un intento de reserva
  engañoso.
- Un conflicto concurrente sigue siendo rechazado por el servidor y se
  muestra claramente.
- Los datos del calendario se limitan al recurso seleccionado.
- Los tests cubren serialización de eventos, rangos de navegación/fechas y
  UX de conflictos.

### ISSUE-05 — Añadir previsión de la demanda para administradores

**Tipo:** Historia de usuario obligatoria  
**Responsable sugerido:** Student C  
**Depende de:** ISSUE-01 e ISSUE-02

**Historia de usuario:** Como administrador del sistema, quiero ver gráficos
de previsión de la demanda basados en el histórico, para ajustar los precios y
el inventario de forma inteligente.

**Alcance:**

- Definir el conjunto mínimo de datos históricos y el horizonte de previsión.
- Agregar reservas por recurso y un periodo de tiempo documentado.
- Exponer una vista o endpoint solo para administradores.
- Renderizar gráficos con etiquetas, unidades, rangos de fechas y estados sin
  datos.
- Documentar que el resultado es una estimación, no una decisión automática de
  precios.

**Criterios de aceptación:**

- Solo los administradores autorizados pueden acceder a la previsión.
- El gráfico se basa en el histórico de reservas persistido e identifica el
  recurso y el periodo seleccionados.
- Datos vacíos o un historial insuficiente producen un estado comprensible.
- La agregación es determinista y está probada con fixtures conocidas.
- La interfaz no cambia precios ni inventario automáticamente.
- Los tests cubren permisos, agregación, rangos de fechas y comportamiento
  sin datos.

### ISSUE-06 — Añadir autogestión y cancelación de reservas

**Tipo:** Historia de usuario adicional 1  
**Responsable sugerido:** Student C  
**Depende de:** ISSUE-02

**Historia de usuario:** Como cliente, quiero ver y cancelar mis próximas
reservas, para gestionar cambios sin contactar a un administrador.

**Alcance:**

- Añadir una página o endpoint que liste las reservas del usuario
  autenticado.
- Mostrar recurso, fecha, hora, estado y contexto de serie recurrente cuando
  aplique.
- Definir un límite de cancelación y si las reservas pasadas pueden
  modificarse.
- Permitir la cancelación solo al propietario de la reserva o a un
  administrador autorizado.
- Hacer visible la cancelación en el calendario y en los datos de previsión.

**Criterios de aceptación:**

- Los usuarios ven solo sus propias reservas.
- Las reservas pasadas o ya canceladas no pueden cancelarse de nuevo.
- La regla de límite se aplica y se comunica.
- Una cancelación exitosa elimina la reserva de la disponibilidad futura.
- El acceso no autorizado y los IDs inválidos se manejan sin filtrar datos.
- Los tests cubren propiedad, límite, cancelación repetida e impacto en el
  calendario.

### ISSUE-07 — Mejorar la gestión administrativa de recursos y bloques

**Tipo:** Historia de usuario adicional 2  
**Responsable sugerido:** Student A  
**Depende de:** ISSUE-01 e ISSUE-02

**Historia de usuario:** Como administrador, quiero gestionar recursos y
bloques de indisponibilidad con validación, para que los clientes no reserven
capacidad no disponible.

**Alcance:**

- Validar los intervalos de bloque y las referencias a recursos en Django
  Admin.
- Prevenir bloques inválidos o invertidos.
- Hacer que la creación y actualización de bloques sea visible en el
  calendario del cliente.
- Definir cómo la edición o eliminación de un bloque afecta a las reservas
  existentes.
- Preservar el flujo de trabajo existente del Admin donde sea posible.

**Criterios de aceptación:**

- Solo los administradores autorizados pueden crear, editar o eliminar
  recursos y bloques.
- Los intervalos de bloque inválidos se rechazan.
- Un intervalo bloqueado no puede reservarse desde la UI ni desde la API.
- El calendario refleja los cambios de bloques después de actualizar.
- El equipo documenta la política para los bloques que solapan reservas
  existentes.
- Los tests cubren la validación de Admin/modelo y el rechazo de reservas.

### ISSUE-08 — Construir la suite automatizada de pruebas y regresión

**Tipo:** Calidad y QA  
**Responsable sugerido:** Student B  
**Depende de:** ISSUE-02, ISSUE-03, ISSUE-04, ISSUE-05, ISSUE-06 e ISSUE-07

**Objetivo:** Proporcionar evidencia repetible de que cada historia de usuario
fue desarrollada, probada y validada.

**Alcance:**

- Añadir tests de modelo, vista/API, permisos y de plantillas/integración
  relevantes.
- Incluir casos normales, de frontera, de conflicto, de autorización y sin
  datos.
- Ejecutar la suite en una configuración local limpia.
- Registrar los comandos y resultados reales.

**Criterios de aceptación:**

- Cada historia de usuario tiene tests automatizados mapeados a sus criterios
  de aceptación.
- La suite se ejecuta con un comando documentado.
- Los tests no dependen del estado de la base de datos local del
  desarrollador.
- Los fallos se investigan en lugar de ocultarse o eliminarse.
- El informe final incluye el resultado real de aprobado/fallido.

### ISSUE-09 — Documentar el proyecto en un README.md

**Tipo:** Documentación  
**Responsable sugerido:** Student C  
**Depende de:** ISSUE-01 a ISSUE-08

**Objetivo:** Dejar el repositorio autoexplicativo con un `README.md`
completo y verificable.

**Alcance:**

- Redactar o mejorar el `README.md` del repositorio: descripción del
  proyecto.
- Documentar cómo instalarlo y ejecutarlo (requisitos, configuración,
  migraciones, servidor de desarrollo).
- Documentar las historias de usuario implementadas (las tres obligatorias y
  las dos adicionales) y cómo probarlas.
- Añadir una guía de uso básico para los flujos principales (reserva,
  calendario, cancelación, previsión).
- Incluir cualquier configuración necesaria (base de datos, variables,
  Admin).

**Criterios de aceptación:**

- El `README.md` contiene descripción, instalación, ejecución, HU
  implementadas, guía de uso y configuración.
- Los pasos de instalación y ejecución son verificables en una configuración
  local limpia siguiendo solo el README.
- Cada una de las cinco historias de usuario aparece documentada con su forma
  de probarla.
- La guía de uso coincide con el comportamiento real de la aplicación.
- No hay pasos obsoletos ni instrucciones que dependan de conocimiento
  externo al repositorio.

## 4. Distribución sugerida entre tres estudiantes

La siguiente distribución equilibra la propiedad de la implementación
manteniendo los roles rotativos requeridos. La propiedad no elimina la
necesidad de revisión y QA por parte de otro estudiante.

| Estudiante | Issues principales de implementación | Enfoque inicial de Developer |
|---|---|---|
| Student A | ISSUE-01, ISSUE-02, ISSUE-07 | Fundación backend y reglas de reserva |
| Student B | ISSUE-03, ISSUE-04, ISSUE-08 | Flujo de usuario, calendario y tests automatizados |
| Student C | ISSUE-05, ISSUE-06, ISSUE-09 | Previsión, autogestión y documentación |

### Rotación de roles

Rotear los tres roles por sprint o grupo de issues. Ningún estudiante debe
permanecer como Developer, Reviewer o QA en todos los issues.

| Sprint | Developer | Reviewer | QA |
|---|---|---|---|
| Sprint 1: ISSUE-01 e ISSUE-02 | Student A | Student B | Student C |
| Sprint 2: ISSUE-03 e ISSUE-04 | Student B | Student C | Student A |
| Sprint 3: ISSUE-05 e ISSUE-06 | Student C | Student A | Student B |
| Sprint 4: ISSUE-07 e ISSUE-08 | Student A | Student B | Student C |
| Sprint 5: ISSUE-09 e integración final | Student B | Student C | Student A |

Antes de asignar nombres reales, el equipo debe confirmar que esta rotación
se ajusta a su disponibilidad.

## 5. Orden de dependencias

```text
ISSUE-01
  -> ISSUE-02
       -> ISSUE-03
       -> ISSUE-04
       -> ISSUE-05
       -> ISSUE-06
       -> ISSUE-07

ISSUE-02 + ISSUE-03 + ISSUE-04 + ISSUE-05 + ISSUE-06 + ISSUE-07
  -> ISSUE-08
       -> ISSUE-09
```

ISSUE-05 depende directamente de ISSUE-01 e ISSUE-02 (en el diagrama,
ISSUE-01 llega vía ISSUE-02, que ya depende de ISSUE-01). Los issues pueden
desarrollarse en paralelo después de ISSUE-02 cuando sus dependencias
listadas estén completas. La integración y la pasada final de QA deben
esperar a todos los issues de features.

## 6. Plantilla recomendada de issues de GitHub

Usar esta estructura cuando el equipo humano apruebe y cree cada issue:

```markdown
## Historia de usuario / objetivo

## Contexto

## Alcance

## Criterios de aceptación
- [ ] ...

## Pruebas y validación

## Dependencias

## Fuera de alcance

## Evidencia
- Rama:
- Commits:
- Pull request:
- Entrada del AI Development Log:
```

## 7. Checklist de revisión humana

- [ ] Confirmar la interpretación de los datos de pago.
- [ ] Confirmar las dos historias de usuario adicionales.
- [ ] Confirmar la propiedad de los issues y la rotación de roles.
- [ ] Confirmar la política de cancelación y la política de solape de bloques.
- [ ] Confirmar el horizonte de previsión y los datos históricos mínimos.
- [ ] Confirmar la rama base (`main` u otra rama acordada).
- [ ] Crear los issues de GitHub solo después de aprobar este documento.
