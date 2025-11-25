# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Descripción del Proyecto

Este es un bot de Telegram para la gestión de registro de estudiantes construido con python-telegram-bot v21.10. El bot permite a usuarios autorizados registrar múltiples estudiantes con información del instituto y gestionar los registros a través de una interfaz interactiva con teclados inline.

## Ejecutar el Bot

```bash
# Activar entorno virtual
source .venv/bin/activate  # macOS/Linux
# o
.venv\Scripts\activate  # Windows

# Ejecutar el bot
python bot.py
```

El bot utiliza un mecanismo de bloqueo basado en archivos para prevenir que múltiples instancias se ejecuten simultáneamente (ver bot.py:1073-1080).

## Configuración del Entorno

Crear un archivo `.env` con:
```
TELEGRAM_BOT_TOKEN=tu_token_aquí
```

El token se obtiene de [@BotFather](https://t.me/botfather) en Telegram.

## Arquitectura de Base de Datos

El sistema usa SQLite con un **diseño relacional de dos tablas**:

### Tabla: `users`
- Almacena información del usuario autorizado (uno por telegram_id)
- Clave primaria: `telegram_id`
- Campos: `apellidos_autorizado`, `nombre_autorizado`, timestamps

### Tabla: `students`
- Almacena registros de estudiantes (múltiples por telegram_id)
- Clave foránea a `users.telegram_id`
- Restricción única: (telegram_id, apellidos_estudiante, nombre_estudiante)
- Campos: `clave_instituto`, `apellidos_estudiante`, `nombre_estudiante`, timestamps

**Patrón Arquitectónico Clave**: Un usuario de Telegram (autorizado) puede registrar múltiples estudiantes, todos compartiendo la misma información de contacto autorizado de la tabla `users`. Al agregar un nuevo estudiante después del primero, el bot solo solicita la información del estudiante (3 campos), no la información del contacto autorizado (database.py:68-90).

## Gestión de Estado y Flujo de Conversación

El bot usa `ConversationHandler` con tres flujos de conversación separados:

### 1. Flujo de Registro Inicial (bot.py:1089-1103)
Estados: `CLAVE_INSTITUTO` → `APELLIDOS_ESTUDIANTE` → `NOMBRE_ESTUDIANTE` → `APELLIDOS_AUTORIZADO` → `NOMBRE_AUTORIZADO`

Puntos de entrada:
- `register_start` - Nuevo registro
- `continue_register` - Reanudar registro interrumpido
- `restart_register` - Limpiar y reiniciar

**Importante**: La bandera `registration_in_progress` en `context.user_data` rastrea registros activos (bot.py:138, 454, 484).

### 2. Flujo de Nuevo Estudiante (bot.py:1106-1116)
Estados: `NEW_CLAVE_INSTITUTO` → `NEW_APELLIDOS_ESTUDIANTE` → `NEW_NOMBRE_ESTUDIANTE`

Solo solicita información del estudiante, reutiliza el contacto autorizado de la tabla `users` (bot.py:688-703).

### 3. Flujo de Edición (bot.py:1119-1127)
Estado único: `EDIT_VALUE`

Usa `context.user_data` para almacenar `edit_field` y `edit_student_id` para rastrear qué campo de qué estudiante actualizar.

## Patrones Críticos de Callbacks

### Formato de Callback Data
- Selección de estudiante: `edit_student_{student_id}`
- Selección de campo: `edit_field_{nombre_campo}_{tipo_campo}_{student_id}`
- Ejemplos: `edit_field_clave_instituto_estudiante_5`, `edit_field_nombre_autorizado_autorizado_5`

### Manejo de BadRequest
Cada manejador de callback query incluye try-catch para consultas expiradas (bot.py:365-373, patrón repetido en todo el código):

```python
try:
    await query.answer()
except BadRequest as e:
    if "Query is too old" in str(e) or "query id is invalid" in str(e):
        logger.warning(f"Callback query expired...")
        return ConversationHandler.END
```

## Lógica de Actualización de Base de Datos

**Distinción crítica** en `edit_value_receive` (bot.py:923-964):

- Si se edita `apellidos_autorizado` o `nombre_autorizado`: actualiza tabla `users` (afecta TODOS los estudiantes)
- Si se editan campos de estudiante: actualiza estudiante específico en tabla `students` vía `student_id`

El bot enruta inteligentemente las actualizaciones:
```python
if field in ("apellidos_autorizado", "nombre_autorizado"):
    updated = db.update_user(telegram_id, field, new_value)
elif student_id:
    updated = db.update_student(telegram_id, f"{field}_estudiante", new_value, student_id)
```

## Rastreo del Estado del Usuario

El bot rastrea el progreso del registro a través de:

1. Estado en base de datos: `db.student_exists(telegram_id)` - Ha completado el registro
2. Estado en contexto: `context.user_data['registration_in_progress']` - Actualmente registrándose
3. Presencia de datos: Verificación de datos parciales en `context.user_data` (bot.py:169-172, 376-379)

El comando `/start` maneja todos estos estados para mostrar las opciones apropiadas (continuar, reiniciar o comenzar nuevo).

## Sistema de Migración

`migrate_db.py` maneja las migraciones de esquema de base de datos. Realiza:
- Crea respaldos con timestamp antes de migrar
- Migra de la antigua estructura de tabla única a la nueva estructura de dos tablas
- Preserva todos los timestamps de los registros originales

Ejecutar migraciones manualmente cuando se necesiten cambios de esquema.

## Comandos Importantes

- `/start` - Punto de entrada principal, consciente del estado (muestra diferentes menús según el estado de registro)
- `/miId` - Retorna el ID de Telegram del usuario
- `/miEstado` - Reporte de estado detallado mostrando progreso del registro, útil para depurar estados atascados
- `/cancel` - Sale de la conversación actual, limpia `context.user_data`

## Logging

Usa el módulo logging de Python con nivel INFO. Todas las operaciones registran en consola. Es crítico revisar los logs al depurar problemas de estado de conversación.

## Errores Comunes

1. **Múltiples instancias del bot**: El archivo de bloqueo previene esto, pero asegurar limpieza apropiada con atexit (bot.py:1080)
2. **Consultas callback expiradas**: Siempre manejar excepciones BadRequest en manejadores de callback
3. **Persistencia de datos de contexto**: `context.user_data` se limpia al finalizar la conversación - asegurar que datos críticos se guarden en BD antes de limpiar
4. **Mapeo de nombres de campos**: Los campos de estudiante en BD son `apellidos_estudiante`, pero pueden referenciarse solo como `apellidos` en algunos contextos - cuidado con las transformaciones de nombres de campo
