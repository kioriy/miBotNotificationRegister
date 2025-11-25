# -*- coding: utf-8 -*-
# @Author: Hugo Rafael Hernández Llamas
# @Date:   2025-10-01 03:56:11
# @Last Modified by:   Hugo Rafael Hernández Llamas
# @Last Modified time: 2025-10-01 09:05:09
import os
import json
import logging
import atexit
import tempfile
import re
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from database import Database

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Inicializar base de datos
db = Database()


# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def load_cct_data() -> Dict:
    """Carga el archivo cct.json con las claves válidas"""
    try:
        with open('cct.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Archivo cct.json no encontrado")
        return {"claves_validas": []}
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear cct.json: {e}")
        return {"claves_validas": []}


def load_datos_estudiante() -> Dict:
    """Carga el archivo datos_estudiante.json con configuraciones de flujos"""
    try:
        with open('datos_estudiante.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Archivo datos_estudiante.json no encontrado")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear datos_estudiante.json: {e}")
        return {}


def validate_cct(cct: str) -> bool:
    """Valida si una CCT existe en el catálogo"""
    cct_data = load_cct_data()
    claves_validas = [item['cct'] for item in cct_data.get('claves_validas', [])]
    return cct.upper() in claves_validas


def normalize_filename(name: str) -> str:
    """Normaliza un nombre para usarlo como nombre de archivo"""
    # Eliminar acentos y caracteres especiales
    name = name.lower().strip()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u', ' ': '_'
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Mantener solo letras, números y guiones bajos
    name = re.sub(r'[^a-z0-9_]', '', name)
    return name


async def save_photo(photo_file, cct: str, tipo: str, nombre: str) -> Optional[str]:
    """
    Guarda una foto en el sistema de archivos

    Args:
        photo_file: Archivo de foto de Telegram
        cct: Clave del centro de trabajo
        tipo: 'alumnos' o 'autorizados'
        nombre: Nombre completo para el archivo

    Returns:
        Ruta relativa del archivo guardado o None si hay error
    """
    try:
        # Crear directorio si no existe
        foto_dir = Path(f"fotos/{cct}/{tipo}")
        foto_dir.mkdir(parents=True, exist_ok=True)

        # Normalizar nombre para archivo
        nombre_archivo = normalize_filename(nombre)
        foto_path = foto_dir / f"{nombre_archivo}.jpg"

        # Descargar y guardar foto
        await photo_file.download_to_drive(str(foto_path))

        logger.info(f"Foto guardada en: {foto_path}")
        return str(foto_path)
    except Exception as e:
        logger.error(f"Error al guardar foto: {e}")
        return None


def get_grados_por_nivel(nivel: str) -> List[str]:
    """Retorna los grados disponibles según el nivel escolar"""
    grados_map = {
        'maternal': ['1', '2', '3'],
        'preescolar': ['1', '2', '3'],
        'primaria': ['1', '2', '3', '4', '5', '6'],
        'secundaria': ['1', '2', '3'],
        'bachillerato': ['1', '2', '3'],
        'universidad': ['1', '2', '3', '4', '5', '6', '7', '8']
    }
    return grados_map.get(nivel.lower(), ['1', '2', '3', '4', '5', '6'])


# ============================================================================
# ESTADOS PARA CONVERSATIONHANDLER
# ============================================================================

# Estados para el ConversationHandler de registro
(CLAVE_INSTITUTO, NOMBRE_ESTUDIANTE, APELLIDOS_ESTUDIANTE,
 NIVEL_ESCOLAR, GRADO, GRUPO,
 DATOS_DINAMICOS_ESTUDIANTE, NOMBRE_AUTORIZADO, APELLIDOS_AUTORIZADO,
 DATOS_DINAMICOS_AUTORIZADO) = range(10)

# Estados para el ConversationHandler de nuevo estudiante
NEW_CLAVE_INSTITUTO, NEW_APELLIDOS_ESTUDIANTE, NEW_NOMBRE_ESTUDIANTE = range(5, 8)

# Estados para el ConversationHandler de edición
EDIT_FIELD, EDIT_VALUE = range(8, 10)


# Bloqueo de instancia única del bot
_INSTANCE_LOCK_FILE = None


def _acquire_instance_lock(name: str = "miBotNotificationRegister"):
    """Intenta adquirir un lock de instancia única usando un archivo en temp.

    Devuelve el descriptor de archivo si se adquiere correctamente; de lo contrario, None.
    """
    try:
        lock_path = os.path.join(tempfile.gettempdir(), f"{name}.lock")
        # Abrir/crear el archivo de lock
        f = open(lock_path, "a+")
        try:
            if os.name == "nt":
                try:
                    import msvcrt
                    # Asegurar que el archivo tenga al menos 1 byte
                    f.seek(0, os.SEEK_END)
                    if f.tell() == 0:
                        f.write("0")
                        f.flush()
                    f.seek(0)
                    # Intentar lock no bloqueante de 1 byte
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    f.close()
                    return None
            else:
                try:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    f.close()
                    return None

            # Escribir el PID actual
            f.seek(0)
            f.truncate()
            f.write(str(os.getpid()))
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
            return f
        except Exception:
            f.close()
            raise
    except Exception as e:
        logger.error(f"No se pudo crear el lock de instancia: {e}")
        return None


def _release_instance_lock(f):
    """Libera el lock de instancia y elimina el archivo."""
    if not f:
        return
    try:
        if os.name == "nt":
            try:
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
            except Exception:
                pass
        path = f.name
        try:
            f.close()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start - Muestra el menú principal"""
    user = update.effective_user
    telegram_id = user.id

    # Si hay una conversación activa, cancelarla primero
    if context.user_data.get('registration_in_progress', False):
        # Limpiar el estado de conversación
        context.user_data.clear()
        await update.message.reply_text(
            "🔄 *Conversación cancelada*\n\n"
            "Se ha cancelado el proceso de registro anterior.\n"
            "Puedes comenzar un nuevo registro si lo deseas.",
            parse_mode='Markdown'
        )

    # Verificar si el usuario ya está registrado
    if db.student_exists(telegram_id):
        student_count = db.get_student_count(telegram_id)
        keyboard = [
            [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
            [InlineKeyboardButton("➕ Agregar otro estudiante", callback_data="new_student_start")],
            [InlineKeyboardButton("✏️ Editar datos", callback_data="edit_menu")],
            [InlineKeyboardButton("🗑️ Eliminar registros", callback_data="delete_confirm")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        student_text = "estudiante" if student_count == 1 else "estudiantes"
        await update.message.reply_text(
            f"¡Hola {user.first_name}! 👋\n\n"
            f"Tienes {student_count} {student_text} registrado{'' if student_count == 1 else 's'} en el sistema.\n"
            "¿Qué deseas hacer?",
            reply_markup=reply_markup
        )
    else:
        # Verificar si el usuario está en medio de un proceso de registro
        # Verificar si hay datos de registro pendientes en user_data
        has_actual_registration_data = any(key in context.user_data for key in [
            'clave_instituto', 'apellidos_estudiante', 'nombre_estudiante', 
            'apellidos_autorizado', 'nombre_autorizado'
        ])
        
        # Verificar si está en proceso de registro (flag o datos)
        is_in_registration_process = (
            context.user_data.get('registration_in_progress', False) or
            has_actual_registration_data
        )
        
        # Solo mostrar opciones de continuar/reiniciar si hay datos reales O si está en proceso
        has_registration_data = is_in_registration_process
        
        if has_registration_data:
            # Usuario tiene datos pendientes, preguntar si quiere continuar o reiniciar
            keyboard = [
                [InlineKeyboardButton("▶️ Continuar registro", callback_data="continue_register")],
                [InlineKeyboardButton("🔄 Reiniciar registro", callback_data="restart_register")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Mostrar progreso actual
            progress_msg = "📝 *Registro en progreso*\n\n"
            if 'clave_instituto' in context.user_data:
                progress_msg += "✅ Clave del instituto\n"
            else:
                progress_msg += "⏳ Clave del instituto\n"

            if 'apellidos_estudiante' in context.user_data:
                progress_msg += "✅ Apellidos del estudiante\n"
            else:
                progress_msg += "⏳ Apellidos del estudiante\n"

            if 'nombre_estudiante' in context.user_data:
                progress_msg += "✅ Nombre del estudiante\n"
            else:
                progress_msg += "⏳ Nombre del estudiante\n"

            if 'apellidos_autorizado' in context.user_data:
                progress_msg += "✅ Apellidos del autorizado\n"
            else:
                progress_msg += "⏳ Apellidos del autorizado\n"

            if 'nombre_autorizado' in context.user_data:
                progress_msg += "✅ Nombre del autorizado\n"
            else:
                progress_msg += "⏳ Nombre del autorizado\n"

            progress_msg += "\n¿Qué deseas hacer?"

            await update.message.reply_text(
                progress_msg,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            # Usuario no registrado y sin proceso activo
            keyboard = [
                [InlineKeyboardButton("📝 Registrarme", callback_data="register_start")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"¡Bienvenido {user.first_name}! 👋\n\n"
                "No estás registrado en el sistema.\n"
                "Para comenzar, presiona el botón de abajo:",
                reply_markup=reply_markup
            )


async def mi_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /miId - Devuelve el ID de Telegram del usuario"""
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Tu ID de Telegram es: `{user.id}`\n\n"
        f"Nombre: {user.first_name}\n"
        f"Usuario: @{user.username if user.username else 'No configurado'}",
        parse_mode='Markdown'
    )


async def mi_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /miEstado - Muestra el estado actual del usuario"""
    user = update.effective_user
    telegram_id = user.id
    
    # Verificar si el usuario está registrado
    if db.student_exists(telegram_id):
        students = db.get_students(telegram_id)
        student_count = len(students)
        
        message_text = f"✅ *Estado: Registrado*\n\n"
        message_text += f"👤 Usuario: {user.first_name}\n"
        message_text += f"🆔 ID: `{telegram_id}`\n"
        message_text += f"📊 Total de estudiantes: {student_count}\n\n"
        
        if student_count == 1:
            student = students[0]
            message_text += f"*Datos registrados:*\n"
            message_text += f"🏫 Instituto: {student['clave_instituto']}\n"
            message_text += f"👨‍🎓 Estudiante: {student['nombre_estudiante']} {student['apellidos_estudiante']}\n"
            message_text += f"👤 Autorizado: {student['nombre_autorizado']} {student['apellidos_autorizado']}\n"
            message_text += f"📅 Registrado: {student['created_at']}\n"
        else:
            message_text += f"*Estudiantes registrados:*\n"
            for i, student in enumerate(students, 1):
                message_text += f"{i}. {student['nombre_estudiante']} {student['apellidos_estudiante']} - {student['clave_instituto']}\n"
        
        message_text += f"\nUsa /start para ver las opciones disponibles."
        
        await update.message.reply_text(message_text, parse_mode='Markdown')
        return
    
    # Verificar si está en proceso de registro
    if context.user_data.get('registration_in_progress', False) or context.user_data.get('new_student_registration', False):
        # Determinar en qué paso está
        progress_msg = "📝 *Estado: Registro en Progreso*\n\n"
        progress_msg += f"👤 Usuario: {user.first_name}\n"
        progress_msg += f"🆔 ID: `{telegram_id}`\n\n"
        progress_msg += "*Progreso del registro:*\n"
        
        # Verificar cada paso
        if 'clave_instituto' in context.user_data:
            progress_msg += "✅ Clave del instituto\n"
        else:
            progress_msg += "⏳ *Clave del instituto* (PENDIENTE)\n"
            
        if 'apellidos_estudiante' in context.user_data:
            progress_msg += "✅ Apellidos del estudiante\n"
        else:
            progress_msg += "⏳ Apellidos del estudiante\n"
            
        if 'nombre_estudiante' in context.user_data:
            progress_msg += "✅ Nombre del estudiante\n"
        else:
            progress_msg += "⏳ Nombre del estudiante\n"
            
        if 'apellidos_autorizado' in context.user_data:
            progress_msg += "✅ Apellidos del autorizado\n"
        else:
            progress_msg += "⏳ Apellidos del autorizado\n"
            
        if 'nombre_autorizado' in context.user_data:
            progress_msg += "✅ Nombre del autorizado\n"
        else:
            progress_msg += "⏳ Nombre del autorizado\n"
        
        # Determinar qué está esperando el bot
        if 'clave_instituto' not in context.user_data:
            progress_msg += "\n🎯 *El bot está esperando:*\n"
            progress_msg += "Ingresa la **clave del instituto**\n"
            progress_msg += "Ejemplo: `INST001` o `COLEGIO123`"
        elif 'apellidos_estudiante' not in context.user_data:
            progress_msg += "\n🎯 *El bot está esperando:*\n"
            progress_msg += "Ingresa los **apellidos del estudiante**\n"
            progress_msg += "Ejemplo: `García López`"
        elif 'nombre_estudiante' not in context.user_data:
            progress_msg += "\n🎯 *El bot está esperando:*\n"
            progress_msg += "Ingresa el **nombre del estudiante**\n"
            progress_msg += "Ejemplo: `Juan Carlos`"
        elif 'apellidos_autorizado' not in context.user_data:
            progress_msg += "\n🎯 *El bot está esperando:*\n"
            progress_msg += "Ingresa los **apellidos del autorizado**\n"
            progress_msg += "Ejemplo: `Martínez Rodríguez`"
        elif 'nombre_autorizado' not in context.user_data:
            progress_msg += "\n🎯 *El bot está esperando:*\n"
            progress_msg += "Ingresa el **nombre del autorizado**\n"
            progress_msg += "Ejemplo: `María Elena`"
        
        progress_msg += "\n\n💡 *Comandos útiles:*\n"
        progress_msg += "• `/start` - Volver al menú principal\n"
        progress_msg += "• `/cancel` - Cancelar el registro\n"
        progress_msg += "• `/miEstado` - Ver este estado nuevamente"
        
        await update.message.reply_text(progress_msg, parse_mode='Markdown')
        return
    
    # Usuario no registrado y sin proceso activo
    await update.message.reply_text(
        f"❌ *Estado: No Registrado*\n\n"
        f"👤 Usuario: {user.first_name}\n"
        f"🆔 ID: `{telegram_id}`\n\n"
        f"*No estás registrado en el sistema.*\n\n"
        f"🎯 *Para comenzar:*\n"
        f"Usa `/start` para iniciar el proceso de registro.\n\n"
        f"💡 *Comandos disponibles:*\n"
        f"• `/start` - Iniciar registro\n"
        f"• `/miId` - Ver tu ID de Telegram\n"
        f"• `/miEstado` - Ver este estado",
        parse_mode='Markdown'
    )


async def continue_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Continúa el proceso de registro desde donde se quedó"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
            return ConversationHandler.END
        else:
            logger.error(f"Error answering callback query: {e}")
            return ConversationHandler.END

    # Verificar si realmente hay datos para continuar
    has_actual_data = any(key in context.user_data for key in [
        'clave_instituto', 'apellidos_estudiante', 'nombre_estudiante', 
        'apellidos_autorizado', 'nombre_autorizado'
    ])
    
    if not has_actual_data:
        # No hay datos previos, iniciar desde el principio
        try:
            await query.edit_message_text(
                "📝 *Iniciando Registro*\n\n"
                "Por favor, ingresa la *clave del instituto*:\n"
                "Recuerda que la clave debe ser única y secreta.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            await query.message.reply_text(
                "📝 *Iniciando Registro*\n\n"
                "Por favor, ingresa la *clave del instituto*:\n"
                "Recuerda que la clave debe ser única y secreta.",
                parse_mode='Markdown'
            )
        return CLAVE_INSTITUTO

    # Determinar el siguiente estado basado en los datos existentes
    if 'clave_instituto' not in context.user_data:
        await query.edit_message_text(
            "📝 *Continuando Registro*\n\n"
            "Por favor, ingresa la *clave del instituto*:",
            parse_mode='Markdown'
        )
        return CLAVE_INSTITUTO
    elif 'apellidos_estudiante' not in context.user_data:
        await query.edit_message_text(
            "📝 *Continuando Registro*\n\n"
            "Por favor, ingresa los *apellidos del estudiante*:",
            parse_mode='Markdown'
        )
        return APELLIDOS_ESTUDIANTE
    elif 'nombre_estudiante' not in context.user_data:
        await query.edit_message_text(
            "📝 *Continuando Registro*\n\n"
            "Por favor, ingresa el *nombre del estudiante*:",
            parse_mode='Markdown'
        )
        return NOMBRE_ESTUDIANTE
    elif 'apellidos_autorizado' not in context.user_data:
        await query.edit_message_text(
            "📝 *Continuando Registro*\n\n"
            "Por favor, ingresa los *apellidos del autorizado*:",
            parse_mode='Markdown'
        )
        return APELLIDOS_AUTORIZADO
    else:
        await query.edit_message_text(
            "📝 *Continuando Registro*\n\n"
            "Por favor, ingresa el *nombre del autorizado*:",
            parse_mode='Markdown'
        )
        return NOMBRE_AUTORIZADO


async def restart_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reinicia el proceso de registro desde el principio"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
            return ConversationHandler.END
        else:
            logger.error(f"Error answering callback query: {e}")
            return ConversationHandler.END

    # Limpiar datos anteriores
    context.user_data.clear()
    # Marcar que el usuario está en proceso de registro
    context.user_data['registration_in_progress'] = True

    try:
        await query.edit_message_text(
            "📝 *Reiniciando Registro*\n\n"
            "Por favor, ingresa la *clave del instituto*:",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await query.message.reply_text(
            "📝 *Reiniciando Registro*\n\n"
            "Por favor, ingresa la *clave del instituto*:",
            parse_mode='Markdown'
        )
    return CLAVE_INSTITUTO
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de registro"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")

    # Limpiar cualquier dato anterior antes de comenzar
    context.user_data.clear()
    # Marcar que el usuario está en proceso de registro
    context.user_data['registration_in_progress'] = True
    context.user_data['datos_estudiante_extra'] = {}
    context.user_data['datos_autorizado_extra'] = {}

    await query.edit_message_text(
        "📝 *Proceso de Registro*\n\n"
        "📝 **Paso 1 de 10**\n"
        "Por favor, ingresa la *clave del instituto (CCT)*:\n\n"
        "💡 *Ejemplo:* `14DPR2576Y`\n"
        "🔒 Si no conoces la clave consulta en dirección o administración del instituto.\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return CLAVE_INSTITUTO

async def clave_instituto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe y valida la clave del instituto"""
    cct = update.message.text.strip().upper()

    # Validar CCT
    if not validate_cct(cct):
        await update.message.reply_text(
            f"❌ *CCT no válida*\n\n"
            f"La clave `{cct}` no está registrada en el sistema.\n\n"
            f"🔒 Por favor, verifica la clave con la dirección o administración del instituto.\n"
            f"💡 *Ejemplo de formato:* `14DPR2576Y`\n\n"
            f"Intenta nuevamente:",
            parse_mode='Markdown'
        )
        return CLAVE_INSTITUTO

    context.user_data['clave_instituto'] = cct
    context.user_data['registration_in_progress'] = True

    await update.message.reply_text(
        "✅ *CCT válida*\n\n"
        "📝 **Paso 2 de 10**\n"
        "Ahora, ingresa el *nombre del estudiante*:\n\n"
        "💡 *Ejemplo:* `Juan Carlos` o `María Elena`\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return NOMBRE_ESTUDIANTE


async def nombre_estudiante(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre del estudiante"""
    context.user_data['nombre_estudiante'] = update.message.text.strip()
    context.user_data['registration_in_progress'] = True

    await update.message.reply_text(
        "✅ *Nombre del estudiante guardado*\n\n"
        "📝 **Paso 3 de 10**\n"
        "Ahora, ingresa los *apellidos del estudiante*:\n\n"
        "💡 *Ejemplo:* `García López` o `Martínez Rodríguez`\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return APELLIDOS_ESTUDIANTE


async def apellidos_estudiante(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe los apellidos del estudiante y pide nivel escolar"""
    context.user_data['apellidos_estudiante'] = update.message.text.strip()
    context.user_data['registration_in_progress'] = True

    # Crear opciones de nivel escolar
    niveles = [
        ['🍼 Maternal', '🎨 Preescolar'],
        ['📚 Primaria', '🎓 Secundaria'],
        ['📖 Bachillerato', '🏛️ Universidad']
    ]
    keyboard = [[InlineKeyboardButton(texto, callback_data=f"nivel_{texto.split()[1].lower()}")
                 for texto in fila] for fila in niveles]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ *Apellidos del estudiante guardados*\n\n"
        "📝 **Paso 4 de 10**\n"
        "Selecciona el *nivel escolar* del estudiante:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return NIVEL_ESCOLAR


# ============================================================================
# NUEVOS HANDLERS PARA FLUJO COMPLETO
# ============================================================================

async def nivel_escolar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de nivel escolar y pide grado"""
    query = update.callback_query
    await query.answer()

    # Extraer nivel del callback_data
    nivel = query.data.replace('nivel_', '')
    context.user_data['nivel_escolar'] = nivel

    # Obtener grados disponibles para el nivel
    grados = get_grados_por_nivel(nivel)

    # Crear botones de grado (2 por fila)
    keyboard = []
    for i in range(0, len(grados), 2):
        row = [InlineKeyboardButton(f"Grado {g}", callback_data=f"grado_{g}")
               for g in grados[i:i+2]]
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ *Nivel escolar: {nivel.capitalize()}*\n\n"
        f"📝 **Paso 5 de 10**\n"
        f"Selecciona el *grado* del estudiante:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return GRADO


async def grado_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de grado y pide grupo"""
    query = update.callback_query
    await query.answer()

    # Extraer grado del callback_data
    grado = query.data.replace('grado_', '')
    context.user_data['grado'] = grado

    # Crear botones de grupo
    grupos = ['A', 'B', 'C', 'D', 'E', 'F']
    keyboard = []
    for i in range(0, len(grupos), 3):
        row = [InlineKeyboardButton(f"Grupo {g}", callback_data=f"grupo_{g}")
               for g in grupos[i:i+3]]
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ *Grado: {grado}*\n\n"
        f"📝 **Paso 6 de 10**\n"
        f"Selecciona el *grupo* del estudiante:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return GRUPO


async def grupo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección de grupo e inicia preguntas dinámicas del estudiante"""
    query = update.callback_query
    await query.answer()

    # Extraer grupo del callback_data
    grupo = query.data.replace('grupo_', '')
    context.user_data['grupo'] = grupo

    # Cargar configuración de datos dinámicos
    cct = context.user_data.get('clave_instituto')
    datos_config = load_datos_estudiante()

    # Verificar si hay campos adicionales para este instituto
    if cct in datos_config and 'campos_estudiante' in datos_config[cct]:
        campos = datos_config[cct]['campos_estudiante']
        context.user_data['campos_estudiante_pendientes'] = campos.copy()
        context.user_data['campo_estudiante_actual'] = 0

        # Mostrar primera pregunta
        return await mostrar_pregunta_estudiante(query, context)
    else:
        # No hay campos adicionales, pasar a datos del autorizado
        await query.edit_message_text(
            f"✅ *Grupo: {grupo}*\n\n"
            f"📝 **Paso 7 de 10**\n"
            f"Ahora, ingresa el *nombre del autorizado*:\n\n"
            f"💡 *Ejemplo:* `Juan Carlos` o `María Elena`",
            parse_mode='Markdown'
        )
        return NOMBRE_AUTORIZADO


async def mostrar_pregunta_estudiante(query_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra la siguiente pregunta dinámica del estudiante"""
    campos = context.user_data.get('campos_estudiante_pendientes', [])
    idx = context.user_data.get('campo_estudiante_actual', 0)

    if idx >= len(campos):
        # Terminaron las preguntas del estudiante, pasar al autorizado
        if isinstance(query_or_update, Update):
            await query_or_update.message.reply_text(
                "📝 **Paso 7 de 10**\n"
                "Ahora, ingresa el *nombre del autorizado*:\n\n"
                "💡 *Ejemplo:* `Juan Carlos` o `María Elena`",
                parse_mode='Markdown'
            )
        else:
            await query_or_update.edit_message_text(
                "📝 **Paso 7 de 10**\n"
                "Ahora, ingresa el *nombre del autorizado*:\n\n"
                "💡 *Ejemplo:* `Juan Carlos` o `María Elena`",
                parse_mode='Markdown'
            )
        return NOMBRE_AUTORIZADO

    campo = campos[idx]
    pregunta = campo.get('pregunta', 'Ingresa el dato')

    if campo.get('tipo') == 'opcion_multiple':
        # Crear botones para opciones múltiples
        opciones = campo.get('opciones', [])
        keyboard = []
        for i in range(0, len(opciones), 2):
            row = [InlineKeyboardButton(opt, callback_data=f"opt_est_{opt}")
                   for opt in opciones[i:i+2]]
            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)

        if isinstance(query_or_update, Update):
            await query_or_update.message.reply_text(
                pregunta,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query_or_update.edit_message_text(
                pregunta,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    else:
        # Pregunta de texto o foto
        if isinstance(query_or_update, Update):
            await query_or_update.message.reply_text(pregunta, parse_mode='Markdown')
        else:
            await query_or_update.edit_message_text(pregunta, parse_mode='Markdown')

    return DATOS_DINAMICOS_ESTUDIANTE


async def datos_dinamicos_estudiante_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja las respuestas a preguntas dinámicas del estudiante"""
    campos = context.user_data.get('campos_estudiante_pendientes', [])
    idx = context.user_data.get('campo_estudiante_actual', 0)

    if idx >= len(campos):
        return await mostrar_pregunta_estudiante(update, context)

    campo = campos[idx]
    campo_nombre = campo.get('campo')

    # Guardar respuesta
    if update.message:
        if update.message.photo:
            # Es una foto
            photo = update.message.photo[-1]  # La foto de mayor resolución
            photo_file = await photo.get_file()
            cct = context.user_data.get('clave_instituto')
            nombre_completo = f"{context.user_data.get('nombre_estudiante')}_{context.user_data.get('apellidos_estudiante')}"
            foto_path = await save_photo(photo_file, cct, 'alumnos', nombre_completo)
            context.user_data['datos_estudiante_extra'][campo_nombre] = foto_path
        else:
            # Es texto
            context.user_data['datos_estudiante_extra'][campo_nombre] = update.message.text.strip()
    elif update.callback_query:
        # Es una opción múltiple
        query = update.callback_query
        await query.answer()
        valor = query.data.replace('opt_est_', '')
        context.user_data['datos_estudiante_extra'][campo_nombre] = valor

    # Avanzar al siguiente campo
    context.user_data['campo_estudiante_actual'] = idx + 1
    return await mostrar_pregunta_estudiante(update, context)


async def nombre_autorizado_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre del autorizado"""
    context.user_data['nombre_autorizado'] = update.message.text.strip()

    await update.message.reply_text(
        "✅ *Nombre del autorizado guardado*\n\n"
        "📝 **Paso 8 de 10**\n"
        "Ahora, ingresa los *apellidos del autorizado*:\n\n"
        "💡 *Ejemplo:* `García López` o `Martínez Rodríguez`",
        parse_mode='Markdown'
    )
    return APELLIDOS_AUTORIZADO


async def apellidos_autorizado_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe los apellidos del autorizado e inicia preguntas dinámicas"""
    context.user_data['apellidos_autorizado'] = update.message.text.strip()

    # Cargar configuración de datos dinámicos
    cct = context.user_data.get('clave_instituto')
    datos_config = load_datos_estudiante()

    # Verificar si hay campos adicionales para el autorizado
    if cct in datos_config and 'campos_autorizado' in datos_config[cct]:
        campos = datos_config[cct]['campos_autorizado']
        context.user_data['campos_autorizado_pendientes'] = campos.copy()
        context.user_data['campo_autorizado_actual'] = 0

        # Mostrar primera pregunta
        await update.message.reply_text(
            "✅ *Apellidos del autorizado guardados*\n",
            parse_mode='Markdown'
        )
        return await mostrar_pregunta_autorizado(update, context)
    else:
        # No hay campos adicionales, completar registro
        return await completar_registro(update, context)


async def mostrar_pregunta_autorizado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra la siguiente pregunta dinámica del autorizado"""
    campos = context.user_data.get('campos_autorizado_pendientes', [])
    idx = context.user_data.get('campo_autorizado_actual', 0)

    if idx >= len(campos):
        # Terminaron las preguntas, completar registro
        return await completar_registro(update, context)

    campo = campos[idx]
    pregunta = campo.get('pregunta', 'Ingresa el dato')

    await update.message.reply_text(pregunta, parse_mode='Markdown')
    return DATOS_DINAMICOS_AUTORIZADO


async def datos_dinamicos_autorizado_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja las respuestas a preguntas dinámicas del autorizado"""
    campos = context.user_data.get('campos_autorizado_pendientes', [])
    idx = context.user_data.get('campo_autorizado_actual', 0)

    if idx >= len(campos):
        return await completar_registro(update, context)

    campo = campos[idx]
    campo_nombre = campo.get('campo')

    # Guardar respuesta
    if update.message.photo:
        # Es una foto
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        cct = context.user_data.get('clave_instituto')
        nombre_completo = f"{context.user_data.get('nombre_autorizado')}_{context.user_data.get('apellidos_autorizado')}"
        foto_path = await save_photo(photo_file, cct, 'autorizados', nombre_completo)
        context.user_data['datos_autorizado_extra'][campo_nombre] = foto_path
    else:
        # Es texto o teléfono
        context.user_data['datos_autorizado_extra'][campo_nombre] = update.message.text.strip()

    # Avanzar al siguiente campo
    context.user_data['campo_autorizado_actual'] = idx + 1
    return await mostrar_pregunta_autorizado(update, context)


async def completar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Completa el registro guardando todos los datos en la base de datos"""
    telegram_id = update.effective_user.id

    # Guardar en la base de datos con todos los nuevos campos
    success = db.add_student(
        telegram_id=telegram_id,
        clave_instituto=context.user_data['clave_instituto'],
        nombre_estudiante=context.user_data['nombre_estudiante'],
        apellidos_estudiante=context.user_data['apellidos_estudiante'],
        grado=context.user_data.get('grado'),
        grupo=context.user_data.get('grupo'),
        nivel_escolar=context.user_data.get('nivel_escolar'),
        datos_estudiante=context.user_data.get('datos_estudiante_extra', {}),
        apellidos_autorizado=context.user_data['apellidos_autorizado'],
        nombre_autorizado=context.user_data['nombre_autorizado'],
        datos_autorizado=context.user_data.get('datos_autorizado_extra', {})
    )

    if success:
        keyboard = [
            [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
            [InlineKeyboardButton("➕ Agregar otro estudiante", callback_data="new_student_start")],
            [InlineKeyboardButton("✏️ Editar datos", callback_data="edit_menu")],
            [InlineKeyboardButton("🗑️ Eliminar registros", callback_data="delete_confirm")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "✅ *¡Registro completado exitosamente!*\n\n"
            "📚 Todos los datos han sido guardados en el sistema.\n"
            f"🏫 Instituto: {context.user_data['clave_instituto']}\n"
            f"👨‍🎓 Estudiante: {context.user_data['nombre_estudiante']} {context.user_data['apellidos_estudiante']}\n"
            f"📊 Nivel: {context.user_data.get('nivel_escolar', '').capitalize()}, Grado {context.user_data.get('grado')}, Grupo {context.user_data.get('grupo')}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Hubo un error al guardar tus datos. Por favor, intenta nuevamente."
        )

    # Limpiar datos temporales
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela el proceso de registro"""
    # Limpiar todos los datos de conversación
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ *Proceso cancelado*\n\n"
        "Se ha cancelado el proceso de registro.\n"
        "Usa /start para volver al menú principal.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def new_student_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de registro de un nuevo estudiante"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
            return ConversationHandler.END
        else:
            logger.error(f"Error answering callback query: {e}")
            return ConversationHandler.END

    # Limpiar cualquier dato anterior antes de comenzar
    context.user_data.clear()
    # Marcar que el usuario está en proceso de registro de nuevo estudiante
    context.user_data['new_student_registration'] = True

    await query.edit_message_text(
        "➕ *Agregar Nuevo Estudiante*\n\n"
        "📝 **Paso 1 de 3**\n"
        "Por favor, ingresa la *clave del instituto* para el nuevo estudiante:\n\n"
        "💡 *Ejemplo:* `INST001` o `COLEGIO123`\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return NEW_CLAVE_INSTITUTO


async def new_clave_instituto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la clave del instituto para el nuevo estudiante"""
    context.user_data['clave_instituto'] = update.message.text
    # Mantener el flag de registro en progreso
    context.user_data['new_student_registration'] = True
    
    await update.message.reply_text(
        "✅ *Clave del instituto guardada*\n\n"
        "📝 **Paso 2 de 3**\n"
        "Ahora, ingresa los *apellidos del nuevo estudiante*:\n\n"
        "💡 *Ejemplo:* `García López` o `Martínez Rodríguez`\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return NEW_APELLIDOS_ESTUDIANTE


async def new_apellidos_estudiante(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe los apellidos del nuevo estudiante"""
    context.user_data['apellidos_estudiante'] = update.message.text
    # Mantener el flag de registro en progreso
    context.user_data['new_student_registration'] = True
    
    await update.message.reply_text(
        "✅ *Apellidos del estudiante guardados*\n\n"
        "📝 **Paso 3 de 3** (Último paso)\n"
        "Por último, ingresa el *nombre del nuevo estudiante*:\n\n"
        "💡 *Ejemplo:* `Juan Carlos` o `María Elena`\n"
        "🔍 Usa `/miEstado` para ver tu progreso",
        parse_mode='Markdown'
    )
    return NEW_NOMBRE_ESTUDIANTE


async def new_nombre_estudiante(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre del nuevo estudiante y completa el registro"""
    context.user_data['nombre_estudiante'] = update.message.text
    telegram_id = update.effective_user.id
    
    # Obtener datos del autorizado existente
    user_data = db.get_user(telegram_id)
    if not user_data:
        await update.message.reply_text(
            "❌ Error: No se encontraron datos del autorizado.\n"
            "Por favor, contacta al administrador."
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # Guardar el nuevo estudiante
    success = db.add_student(
        telegram_id=telegram_id,
        clave_instituto=context.user_data['clave_instituto'],
        apellidos_estudiante=context.user_data['apellidos_estudiante'],
        nombre_estudiante=context.user_data['nombre_estudiante']
    )
    
    if success:
        keyboard = [
            [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
            [InlineKeyboardButton("➕ Agregar otro estudiante", callback_data="new_student_start")],
            [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ *¡Nuevo estudiante agregado exitosamente!*\n\n"
            f"👨‍🎓 **{context.user_data['nombre_estudiante']} {context.user_data['apellidos_estudiante']}**\n"
            f"🏫 Instituto: {context.user_data['clave_instituto']}\n"
            f"👤 Autorizado: {user_data['nombre_autorizado']} {user_data['apellidos_autorizado']}\n\n"
            "El nuevo estudiante ha sido registrado con los mismos datos del autorizado.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Hubo un error al agregar el nuevo estudiante. Por favor, intenta nuevamente."
        )
    
    # Limpiar datos temporales
    context.user_data.clear()
    return ConversationHandler.END


async def view_students(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra todos los estudiantes del usuario"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    telegram_id = update.effective_user.id
    students = db.get_students(telegram_id)
    
    if students:
        keyboard = [
            [InlineKeyboardButton("✏️ Editar datos", callback_data="edit_menu")],
            [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"📋 *Mis Estudiantes Registrados*\n\n"
        message_text += f"🆔 ID Telegram: `{telegram_id}`\n"
        message_text += f"📊 Total de estudiantes: {len(students)}\n\n"
        
        for i, student in enumerate(students, 1):
            message_text += f"*👨‍🎓 Estudiante #{i}:*\n"
            message_text += f"🏫 Instituto: {student['clave_instituto']}\n"
            message_text += f"📝 Nombre: {student['nombre_estudiante']} {student['apellidos_estudiante']}\n"

            # Mostrar nuevos campos básicos
            if student.get('nivel_escolar'):
                message_text += f"📊 Nivel: {student['nivel_escolar'].capitalize()}\n"
            if student.get('grado'):
                message_text += f"📚 Grado: {student['grado']}\n"
            if student.get('grupo'):
                message_text += f"🎯 Grupo: {student['grupo']}\n"

            # Mostrar datos adicionales del estudiante
            datos_est = student.get('datos_estudiante', {})
            if datos_est and isinstance(datos_est, dict):
                if datos_est.get('domicilio'):
                    message_text += f"📍 Domicilio: {datos_est['domicilio']}\n"
                if datos_est.get('tipo_sangre'):
                    message_text += f"🩸 Tipo de sangre: {datos_est['tipo_sangre']}\n"
                if datos_est.get('alergias'):
                    message_text += f"🤧 Alergias: {datos_est['alergias']}\n"
                if datos_est.get('medicamentos'):
                    message_text += f"💊 Medicamentos: {datos_est['medicamentos']}\n"
                if datos_est.get('foto'):
                    message_text += f"📸 Foto estudiante: ✅ Guardada\n"

            message_text += f"\n*👤 Autorizado:*\n"
            message_text += f"📝 Nombre: {student['nombre_autorizado']} {student['apellidos_autorizado']}\n"

            # Mostrar datos adicionales del autorizado
            datos_aut = student.get('datos_autorizado', {})
            if datos_aut and isinstance(datos_aut, dict):
                if datos_aut.get('telefono'):
                    message_text += f"📱 Teléfono: {datos_aut['telefono']}\n"
                if datos_aut.get('foto'):
                    message_text += f"📸 Foto autorizado: ✅ Guardada\n"

            message_text += f"📅 Registrado: {student['created_at']}\n"
            if i < len(students):
                message_text += "\n" + "─" * 30 + "\n\n"
        
        await query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(
            "❌ No se encontraron estudiantes registrados.\n\n"
            "Usa /start para registrarte."
        )


async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el menú de edición con lista de estudiantes"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    telegram_id = update.effective_user.id
    students = db.get_students(telegram_id)
    
    if not students:
        await query.edit_message_text(
            "❌ No se encontraron estudiantes para editar.\n\n"
            "Usa /start para registrarte.",
            parse_mode='Markdown'
        )
        return
    
    # Crear botones para cada estudiante
    keyboard = []
    for i, student in enumerate(students, 1):
        student_name = f"{student['nombre_estudiante']} {student['apellidos_estudiante']}"
        keyboard.append([
            InlineKeyboardButton(
                f"👨‍🎓 {student_name}", 
                callback_data=f"edit_student_{student['id']}"
            )
        ])
    
    # Agregar botones de navegación
    keyboard.extend([
        [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")],
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "✏️ *Menú de Edición*\n\n"
    message_text += f"Tienes {len(students)} estudiante{'s' if len(students) > 1 else ''} registrado{'s' if len(students) > 1 else ''}.\n"
    message_text += "Selecciona el estudiante que deseas editar:"
    
    await query.edit_message_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def edit_student_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja la selección del estudiante a editar"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    # Extraer el ID del estudiante del callback_data
    if query.data.startswith("edit_student_"):
        student_id = int(query.data.split("_")[2])
        telegram_id = update.effective_user.id
        
        # Obtener datos del estudiante
        student = db.get_student(telegram_id, student_id)
        if not student:
            await query.edit_message_text(
                "❌ No se encontró el estudiante seleccionado.",
                parse_mode='Markdown'
            )
            return
        
        # Guardar el ID del estudiante en el contexto
        context.user_data['edit_student_id'] = student_id
        
        # Crear menú de campos para editar
        keyboard = [
            [InlineKeyboardButton("🏫 Clave Instituto", callback_data=f"edit_field_clave_instituto_estudiante_{student_id}")],
            [InlineKeyboardButton("👨‍🎓 Nombre Estudiante", callback_data=f"edit_field_nombre_estudiante_{student_id}")],
            [InlineKeyboardButton("👨‍🎓 Apellidos Estudiante", callback_data=f"edit_field_apellidos_estudiante_{student_id}")],
            [InlineKeyboardButton("📊 Nivel Escolar", callback_data=f"edit_field_nivel_escolar_estudiante_{student_id}")],
            [InlineKeyboardButton("📚 Grado", callback_data=f"edit_field_grado_estudiante_{student_id}")],
            [InlineKeyboardButton("🎯 Grupo", callback_data=f"edit_field_grupo_estudiante_{student_id}")],
            [InlineKeyboardButton("👤 Nombre Autorizado", callback_data=f"edit_field_nombre_autorizado_autorizado_{student_id}")],
            [InlineKeyboardButton("👤 Apellidos Autorizado", callback_data=f"edit_field_apellidos_autorizado_autorizado_{student_id}")],
            [InlineKeyboardButton("🔙 Volver a selección", callback_data="edit_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"✏️ *Editar Estudiante*\n\n"
        message_text += f"👨‍🎓 **{student['nombre_estudiante']} {student['apellidos_estudiante']}**\n"
        message_text += f"🏫 Instituto: {student['clave_instituto']}\n"
        if student.get('nivel_escolar'):
            message_text += f"📊 Nivel: {student['nivel_escolar'].capitalize()}, Grado: {student.get('grado', 'N/A')}, Grupo: {student.get('grupo', 'N/A')}\n"
        message_text += f"👤 Autorizado: {student['nombre_autorizado']} {student['apellidos_autorizado']}\n\n"
        message_text += "Selecciona el campo que deseas modificar:"
        
        await query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )


async def edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección del campo a editar"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    # Extraer información del callback_data
    # Formato: edit_field_{nombre_campo}_{tipo}_{student_id}
    if query.data.startswith("edit_field_"):
        parts = query.data.split("_")
        field_name = parts[2]  # nombre, apellidos, clave, nivel, grado, grupo
        field_type = parts[3]  # estudiante o autorizado
        student_id = int(parts[4])

        # Mapear nombres de campos a nombres legibles
        field_map = {
            'clave': 'Clave del Instituto',
            'apellidos': 'Apellidos',
            'nombre': 'Nombre',
            'nivel': 'Nivel Escolar',
            'grado': 'Grado',
            'grupo': 'Grupo',
        }

        readable_name = field_map.get(field_name, field_name)
        type_readable = "del Estudiante" if field_type == "estudiante" else "del Autorizado"

        context.user_data['edit_field'] = field_name
        context.user_data['edit_field_type'] = field_type
        context.user_data['edit_student_id'] = student_id

        await query.edit_message_text(
            f"✏️ *Editar {readable_name} {type_readable}*\n\n"
            f"Por favor, ingresa el nuevo valor para *{readable_name}*:\n\n"
            f"Escribe /cancel para cancelar.",
            parse_mode='Markdown'
        )
        return EDIT_VALUE
    
    return ConversationHandler.END


async def edit_value_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo valor y actualiza la base de datos"""
    new_value = update.message.text
    field = context.user_data.get('edit_field')
    field_type = context.user_data.get('edit_field_type')
    student_id = context.user_data.get('edit_student_id')
    telegram_id = update.effective_user.id

    updated = False
    if field and field_type:
        if field_type == "autorizado":
            # Campos del autorizado
            field_full = f"{field}_autorizado"
            updated = db.update_user(telegram_id, field_full, new_value)
        elif field_type == "estudiante" and student_id:
            # Campos del estudiante
            if field == "clave":
                field_full = "clave_instituto"
            elif field == "nivel":
                field_full = "nivel_escolar"
            else:
                field_full = f"{field}_estudiante" if field in ["nombre", "apellidos"] else field
            updated = db.update_student(telegram_id, field_full, new_value, student_id)
    if updated:
        # Obtener datos actualizados del estudiante
        student = db.get_student(telegram_id, student_id)
        
        keyboard = [
            [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
            [InlineKeyboardButton("✏️ Editar otro campo", callback_data=f"edit_student_{student_id}")],
            [InlineKeyboardButton("✏️ Editar otro estudiante", callback_data="edit_menu")],
            [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "✅ *¡Datos actualizados correctamente!*\n\n"
        message_text += f"👨‍🎓 **{student['nombre_estudiante']} {student['apellidos_estudiante']}**\n"
        message_text += f"🏫 Instituto: {student['clave_instituto']}\n"
        if student.get('nivel_escolar'):
            message_text += f"📊 Nivel: {student['nivel_escolar'].capitalize()}, Grado: {student.get('grado', 'N/A')}, Grupo: {student.get('grupo', 'N/A')}\n"
        message_text += f"👤 Autorizado: {student['nombre_autorizado']} {student['apellidos_autorizado']}"
        
        await update.message.reply_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Hubo un error al actualizar los datos. Intenta nuevamente."
        )
    
    context.user_data.clear()
    return ConversationHandler.END


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Solicita confirmación para eliminar el registro"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Sí, eliminar", callback_data="delete_confirmed"),
            InlineKeyboardButton("❌ No, cancelar", callback_data="back_to_menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚠️ *¿Estás seguro?*\n\n"
        "Esta acción eliminará todos tus datos del sistema.\n"
        "Esta acción no se puede deshacer.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Elimina el registro del usuario"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    telegram_id = update.effective_user.id
    
    if db.delete_student(telegram_id):
        keyboard = [
            [InlineKeyboardButton("📝 Registrarme nuevamente", callback_data="register_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ *Registro eliminado*\n\n"
            "Tus datos han sido eliminados del sistema.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(
            "❌ Hubo un error al eliminar el registro."
        )


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vuelve al menú principal"""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query expired for user {query.from_user.id if query.from_user else 'unknown'}")
        else:
            logger.error(f"Error answering callback query: {e}")
    
    telegram_id = update.effective_user.id
    
    if db.student_exists(telegram_id):
        student_count = db.get_student_count(telegram_id)
        keyboard = [
            [InlineKeyboardButton("📋 Ver mis datos", callback_data="view_students")],
            [InlineKeyboardButton("➕ Agregar otro estudiante", callback_data="new_student_start")],
            [InlineKeyboardButton("✏️ Editar datos", callback_data="edit_menu")],
            [InlineKeyboardButton("🗑️ Eliminar registros", callback_data="delete_confirm")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        student_text = "estudiante" if student_count == 1 else "estudiantes"
        await query.edit_message_text(
            f"🏠 *Menú Principal*\n\n"
            f"Tienes {student_count} {student_text} registrado{'' if student_count == 1 else 's'}.\n"
            "¿Qué deseas hacer?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Registrarme", callback_data="register_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🏠 *Menú Principal*\n\n"
            "No estás registrado en el sistema.\n"
            "Para comenzar, presiona el botón de abajo:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )


def main() -> None:
    """Inicia el bot"""
    # Evitar múltiples instancias del bot
    global _INSTANCE_LOCK_FILE
    _INSTANCE_LOCK_FILE = _acquire_instance_lock("miBotNotificationRegister")
    if not _INSTANCE_LOCK_FILE:
        logger.error("Ya hay otra instancia del bot en ejecución. Saliendo.")
        return
    # Liberar el lock automáticamente al salir
    atexit.register(_release_instance_lock, _INSTANCE_LOCK_FILE)
    if not TOKEN:
        logger.error("No se encontró el token del bot. Configura TELEGRAM_BOT_TOKEN en el archivo .env")
        return
    
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler para el registro
    register_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(register_start, pattern="^register_start$"),
            CallbackQueryHandler(continue_register, pattern="^continue_register$"),
            CallbackQueryHandler(restart_register, pattern="^restart_register$")
        ],
        states={
            CLAVE_INSTITUTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, clave_instituto)],
            NOMBRE_ESTUDIANTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, nombre_estudiante)],
            APELLIDOS_ESTUDIANTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, apellidos_estudiante)],
            NIVEL_ESCOLAR: [CallbackQueryHandler(nivel_escolar_callback, pattern="^nivel_")],
            GRADO: [CallbackQueryHandler(grado_callback, pattern="^grado_")],
            GRUPO: [CallbackQueryHandler(grupo_callback, pattern="^grupo_")],
            DATOS_DINAMICOS_ESTUDIANTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, datos_dinamicos_estudiante_handler),
                MessageHandler(filters.PHOTO, datos_dinamicos_estudiante_handler),
                CallbackQueryHandler(datos_dinamicos_estudiante_handler, pattern="^opt_est_")
            ],
            NOMBRE_AUTORIZADO: [MessageHandler(filters.TEXT & ~filters.COMMAND, nombre_autorizado_nuevo)],
            APELLIDOS_AUTORIZADO: [MessageHandler(filters.TEXT & ~filters.COMMAND, apellidos_autorizado_nuevo)],
            DATOS_DINAMICOS_AUTORIZADO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, datos_dinamicos_autorizado_handler),
                MessageHandler(filters.PHOTO, datos_dinamicos_autorizado_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler para nuevo estudiante
    new_student_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(new_student_start, pattern="^new_student_start$")
        ],
        states={
            NEW_CLAVE_INSTITUTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_clave_instituto)],
            NEW_APELLIDOS_ESTUDIANTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_apellidos_estudiante)],
            NEW_NOMBRE_ESTUDIANTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_nombre_estudiante)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # ConversationHandler para edición
    edit_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_field_select, pattern="^edit_field_.*")
        ],
        states={
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("miId", mi_id))
    application.add_handler(CommandHandler("miEstado", mi_estado))
    application.add_handler(CommandHandler("cancel", cancel))
    
    # Handlers de conversación
    application.add_handler(register_conv_handler)
    application.add_handler(new_student_conv_handler)
    application.add_handler(edit_conv_handler)
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(view_students, pattern="^view_students$"))
    application.add_handler(CallbackQueryHandler(edit_menu, pattern="^edit_menu$"))
    application.add_handler(CallbackQueryHandler(edit_student_select, pattern="^edit_student_.*"))
    application.add_handler(CallbackQueryHandler(delete_confirm, pattern="^delete_confirm$"))
    application.add_handler(CallbackQueryHandler(delete_confirmed, pattern="^delete_confirmed$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    
    # Iniciar el bot
    logger.info("Bot iniciado correctamente")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
