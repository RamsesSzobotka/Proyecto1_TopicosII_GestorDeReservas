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

## Datos de reserva guardados

Cada usuario autenticado puede guardar en `/perfil/` sus datos de reserva para no rellenarlos en cada compra:

- **Se guarda:** nombre completo, teléfono, correo de contacto, método de pago (pago en la pista o tarjeta simulada) y, solo si elige tarjeta, los **4 últimos dígitos** como referencia.
- **NUNCA se guarda:** número completo de tarjeta, CVV ni fecha de caducidad. El pago es simulado.
- El calendario muestra qué datos se reutilizan y pide confirmación antes de reservar. Si faltan datos, redirige a `/perfil/`.
- Cada usuario solo puede ver y modificar sus propios datos (no hay URLs con id). Los datos no se exponen en el panel de administración.
