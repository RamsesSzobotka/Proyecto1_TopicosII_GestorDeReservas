# 🏟️ Gestor de Reservas de Pistas y Salas

Un sistema web desarrollado con **Django** para gestionar reservas de recursos como pistas de pádel, tenis, fútbol o salas multiusos.  
Incluye un **calendario interactivo con FullCalendar**, gestión de usuarios, validación de solapamientos, reservas recurrentes, bloqueos administrativos y un panel de administración completo.

---

## **Características principales**

### **Modelos implementados**
- **Resource** – Representa cada recurso o pista disponible (pádel, fútbol, etc.).
- **Booking** – Registra las reservas de usuarios para un recurso.
- **Availability (Bloqueos)** – Define franjas horarias en las que una pista no está disponible (bloqueos administrativos).
- **User (Autenticación)** – Gestión de usuarios con login/logout.

### **Funcionalidades clave**
- 📅 **Calendario de disponibilidad** con **FullCalendar**.
- ⛔ **Evita solapamiento de reservas** automáticamente.
- 🔁 **Reservas recurrentes** (opción de repetir semanalmente).
- 🔒 **Bloqueos de recursos** gestionados desde el panel de administración.
- 👨💼 **Panel de administración Django Admin** para gestionar usuarios, recursos, reservas y bloqueos.
- 🔔 **Notificaciones al usuario** al crear reservas o cuando se produce un conflicto.

---

## **Tecnologías utilizadas**

- **Backend:** Django 5 (Python 3.12)
- **Frontend:** HTML5, CSS3, JavaScript (con integración de FullCalendar)
- **Base de datos:** SQLite (por defecto, fácil de cambiar a MySQL o PostgreSQL)
- **Autenticación:** Sistema de usuarios de Django
- **UI:** Diseño minimalista con **navbar**, cards y calendario interactivo

---

## Enfoque del Proyecto

Este proyecto está centrado principalmente en el aprendizaje y la práctica de **Django**.  
Mi objetivo ha sido entender la arquitectura del framework, el manejo de vistas, URLs, modelos, templates y la interacción con la base de datos.  

Por este motivo, el **diseño visual** no ha sido la prioridad en esta fase del desarrollo, ya que mi atención ha estado enfocada en construir una aplicación funcional y bien estructurada en cuanto a lógica y backend.



## **Instalación**

### **1. Clonar el repositorio**

git clone https://github.com/tu-usuario/gestor-reservas.git
cd gestor-reservas
2. Crear entorno virtual

python -m venv .venv
source .venv/bin/activate  # En Linux/Mac
.venv\Scripts\activate     # En Windows

3. Instalar dependencias
pip install -r requirements.txt

4. Migrar la base de datos
python manage.py makemigrations
python manage.py migrate

6. Crear un superusuario (para acceder al panel admin)
python manage.py createsuperuser

8. Ejecutar el servidor
python manage.py runserver
Accede en tu navegador a http://127.0.0.1:8000/

Uso de la aplicación
Panel de administración:
Accede a http://127.0.0.1:8000/admin/ para crear recursos (pistas) y gestionar reservas manualmente.

Home Page (Listado de recursos):
Verás todas las pistas (pádel, fútbol, tenis, etc.) con cards interactivas y un botón para ver el calendario de cada una.

Calendario interactivo:

Selecciona un bloque de tiempo disponible para hacer una reserva.

El sistema valida solapamientos y bloqueos.

Se pueden crear reservas recurrentes (pregunta cuántas semanas repetir).

#### Calendario de disponibilidad

- **Leyenda:** blanco = disponible (horario 09:00-21:00), verde = ocupado (reserva), azul = tu reserva, rojo = bloqueado por el administrador.
- **Vistas:** mes, semana y día. En la vista de mes, un clic en un día abre su detalle por horas; solo se reservan franjas horarias.
- **Zona horaria:** los horarios se muestran en la zona horaria local de tu navegador (indicada bajo la leyenda). El servidor sigue validando cada reserva; si hay conflicto se muestra el mensaje y el calendario se recarga.
- **Privacidad:** quien no es el titular ni staff ve las reservas ajenas solo como "Ocupado".

## Política de bloques administrativos

Los **bloqueos** son intervalos que el administrador crea desde el panel de administración
(`/admin/reservas/availability/`) para dejar un recurso indisponible.

- **Intervalo inválido:** un bloqueo debe terminar después de empezar (`end_time > start_time`).
  Los bloques invertidos o de duración cero se rechazan al guardar.
- **Reservas existentes (la reserva gana):** se puede guardar un bloque que se solape con
  reservas ya creadas. Las reservas existentes **no se modifican ni se cancelan**; el bloqueo
  solo impide **nuevas** reservas en esa franja. El panel avisa de cuántas reservas quedan
  solapadas al guardar el bloque.
- **Edición de un bloque:** se aplica la misma regla. Si se acorta o se mueve, las reservas
  que quedan fuera del nuevo intervalo se mantienen intactas.
- **Eliminación de un bloque:** al borrarlo solo desaparece el bloqueo. Las reservas que se
  solapaban con él **se conservan**.
- **Crear una reserva sobre un bloqueo:** el panel de administración rechaza la reserva y la
  API responde `409 Conflict` con el detalle del conflicto. El servidor es la autoridad: la
  comprobación del calendario en el navegador es solo una ayuda visual.


## Mis reservas y cancelación

Los usuarios autenticados tienen la página **Mis reservas** (`/mis-reservas/`, enlace en la página de inicio). Lista solo sus propias reservas: primero las próximas y luego el historial (pasadas y canceladas), con recurso, fecha, hora, estado y, si pertenece a una reserva recurrente, "Serie: ocurrencia N de M". Las horas se muestran en UTC.

- **Cancelación lógica:** cancelar no borra la reserva; queda con estado `cancelada` (con quién y cuándo) y deja de ocupar la franja. Desaparece del calendario, de la validación de solapamientos y de la previsión de demanda, y ese horario se puede volver a reservar.
- **Regla de límite:** el cliente puede cancelar hasta **2 horas antes** del inicio (constante `LIMITE_CANCELACION` en `reservas/models.py`). Una reserva que ya empezó, ya pasó o ya está cancelada no se puede cancelar de nuevo. La regla se muestra en la página y en el mensaje de error.
- **Administradores:** un usuario `is_staff` puede cancelar cualquier reserva (también ajena) mientras no haya empezado, sin el margen de 2 horas, con `POST /reservas/<id>/cancelar/`.
- **Series:** las reservas creadas con repetición semanal comparten un identificador de serie. Se puede cancelar **solo una ocurrencia** (`alcance=una`) o **esa y las siguientes** de la serie (`alcance=serie`); en ese caso solo se cancelan las futuras que sigan activas y cumplan el límite.
- **Seguridad:** la cancelación es solo `POST` con token CSRF y exige sesión. Una reserva inexistente o ajena (para un usuario que no es administrador) responde el mismo `404`, sin revelar si existe.
