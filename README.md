# Bot de Registro de Estudiantes para Telegram

Bot de Telegram que permite registrar estudiantes con sus datos personales y del instituto, con funcionalidad completa de CRUD (Crear, Leer, Actualizar, Eliminar) mediante menús interactivos.

## 🚀 Características

- ✅ Registro de estudiantes con:
  - Clave del instituto
  - Apellidos y nombre del estudiante
  - Apellidos y nombre del autorizado
  - ID de Telegram (automático)
  
- 📋 Visualización de datos registrados
- ✏️ Edición de cualquier campo mediante menús inline
- 🗑️ Eliminación de registro con confirmación
- 🆔 Comando `/miId` para obtener el ID de Telegram
- 💾 Base de datos SQLite local
- 🎨 Interfaz con menús InlineKeyboardMarkup

## 📋 Requisitos

- Python 3.8 o superior
- Token de Bot de Telegram (obtenido de [@BotFather](https://t.me/botfather))

## 🔧 Instalación

### 1. Clonar o descargar el proyecto

```bash
cd miBotNotificationRegister
```

### 2. Crear entorno virtual con uv (recomendado)

```bash
uv venv
source botRegister/bin/activate  # En Linux/Mac
# o
botRegister\Scripts\activate  # En Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar el token del bot

Crea un archivo `.env` en la raíz del proyecto:

```bash
cp .env.example .env
```

Edita el archivo `.env` y agrega tu token:

```
TELEGRAM_BOT_TOKEN=6061799324:AAEcfontKz7QXUKkPHmolU24encwXrZY9gs
```

Para obtener un token:
1. Abre Telegram y busca [@BotFather](https://t.me/botfather)
2. Envía el comando `/newbot`
3. Sigue las instrucciones
4. Copia el token que te proporciona

## 🎮 Uso

### Iniciar el bot

```bash
python bot.py
```

### Comandos disponibles

- `/start` - Inicia el bot y muestra el menú principal
- `/miId` - Muestra tu ID de Telegram y datos de usuario
- `/cancel` - Cancela cualquier operación en curso

### Flujo de uso

1. **Registro inicial**:
   - Envía `/start`
   - Presiona "📝 Registrarme"
   - Ingresa la clave del instituto
   - Ingresa los apellidos del estudiante
   - Ingresa el nombre del estudiante
   - Ingresa los apellidos del autorizado
   - Ingresa el nombre del autorizado
   - ✅ ¡Registro completado!

2. **Ver datos**:
   - Presiona "📋 Ver mis datos" desde el menú principal

3. **Editar datos**:
   - Presiona "✏️ Editar datos"
   - Selecciona el campo a modificar
   - Ingresa el nuevo valor
   - ✅ Datos actualizados

4. **Eliminar registro**:
   - Presiona "🗑️ Eliminar registro"
   - Confirma la eliminación
   - ✅ Registro eliminado

## 📁 Estructura del proyecto

```
miBotNotificationRegister/
├── bot.py              # Código principal del bot
├── database.py         # Gestión de base de datos SQLite
├── migrate_db.py       # Script de migración de base de datos
├── requirements.txt    # Dependencias del proyecto
├── .env               # Configuración (token del bot)
├── .env.example       # Ejemplo de configuración
├── .gitignore         # Archivos ignorados por git
├── README.md          # Este archivo
└── students.db        # Base de datos (se crea automáticamente)
```

## 🗄️ Base de datos

El bot utiliza SQLite con la siguiente estructura:

**Tabla: students**
- `id` - ID único (autoincremental)
- `telegram_id` - ID de Telegram del usuario (único)
- `clave_instituto` - Clave del instituto
- `apellidos_estudiante` - Apellidos del estudiante
- `nombre_estudiante` - Nombre del estudiante
- `apellidos_autorizado` - Apellidos del autorizado
- `nombre_autorizado` - Nombre del autorizado
- `created_at` - Fecha de creación
- `updated_at` - Fecha de última actualización

## 🛠️ Tecnologías utilizadas

- **python-telegram-bot** (v20.7) - Framework para bots de Telegram
- **python-dotenv** (v1.0.0) - Gestión de variables de entorno
- **SQLite3** - Base de datos (incluido en Python)

## 📝 Notas

- La base de datos se crea automáticamente al iniciar el bot
- Cada usuario de Telegram solo puede tener un registro (identificado por `telegram_id`)
- Los datos se almacenan localmente en el archivo `students.db`
- El bot debe estar ejecutándose para responder a los mensajes

## 🔒 Seguridad

- ⚠️ Nunca compartas tu token de bot
- ⚠️ No subas el archivo `.env` a repositorios públicos
- ⚠️ El archivo `.gitignore` ya está configurado para proteger datos sensibles

## 🐛 Solución de problemas

### El bot no responde
- Verifica que el bot esté ejecutándose (`python bot.py`)
- Verifica que el token en `.env` sea correcto
- Revisa los logs en la consola

### Error de base de datos
- Verifica que tengas permisos de escritura en el directorio
- Si persiste, elimina `students.db` y reinicia el bot

### Error de importación
- Verifica que hayas instalado las dependencias: `pip install -r requirements.txt`
- Verifica que el entorno virtual esté activado

## 📄 Licencia

Este proyecto es de código abierto y está disponible para uso educativo y personal.

## 👨‍💻 Autor

Desarrollado como proyecto de ejemplo para gestión de estudiantes mediante bot de Telegram.
