import sqlite3
from typing import Optional, List, Dict
from contextlib import contextmanager


class Database:
    def __init__(self, db_name: str = "students.db"):
        self.db_name = db_name
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager para manejar conexiones a la base de datos"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """Inicializa la base de datos con las tablas necesarias"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Tabla para usuarios (autorizados)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    apellidos_autorizado TEXT NOT NULL,
                    nombre_autorizado TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla para estudiantes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    clave_instituto TEXT NOT NULL,
                    apellidos_estudiante TEXT NOT NULL,
                    nombre_estudiante TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(telegram_id, apellidos_estudiante, nombre_estudiante),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)
    
    def add_user(self, telegram_id: int, apellidos_autorizado: str, nombre_autorizado: str) -> bool:
        """Agrega un nuevo usuario (autorizado) a la base de datos"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (telegram_id, apellidos_autorizado, nombre_autorizado)
                    VALUES (?, ?, ?)
                """, (telegram_id, apellidos_autorizado, nombre_autorizado))
                return True
        except sqlite3.IntegrityError:
            return False
    
    def add_student(self, telegram_id: int, clave_instituto: str, 
                   apellidos_estudiante: str, nombre_estudiante: str,
                   apellidos_autorizado: str = None, nombre_autorizado: str = None) -> bool:
        """Agrega un nuevo estudiante a la base de datos"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Si se proporcionan datos del autorizado, crear/actualizar usuario
                if apellidos_autorizado and nombre_autorizado:
                    cursor.execute("""
                        INSERT OR REPLACE INTO users (telegram_id, apellidos_autorizado, nombre_autorizado)
                        VALUES (?, ?, ?)
                    """, (telegram_id, apellidos_autorizado, nombre_autorizado))
                
                # Agregar estudiante
                cursor.execute("""
                    INSERT INTO students (telegram_id, clave_instituto, apellidos_estudiante, nombre_estudiante)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, clave_instituto, apellidos_estudiante, nombre_estudiante))
                return True
        except sqlite3.IntegrityError:
            return False
    
    def get_student(self, telegram_id: int, student_id: int = None) -> Optional[Dict]:
        """Obtiene un estudiante por su telegram_id y opcionalmente por student_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if student_id:
                cursor.execute(
                    "SELECT s.*, u.apellidos_autorizado, u.nombre_autorizado "
                    "FROM students s LEFT JOIN users u ON s.telegram_id = u.telegram_id "
                    "WHERE s.telegram_id = ? AND s.id = ?",
                    (telegram_id, student_id),
                )
            else:
                # Si no se especifica student_id, devuelve el primer estudiante (para compatibilidad)
                cursor.execute(
                    "SELECT s.*, u.apellidos_autorizado, u.nombre_autorizado "
                    "FROM students s LEFT JOIN users u ON s.telegram_id = u.telegram_id "
                    "WHERE s.telegram_id = ? ORDER BY s.created_at ASC LIMIT 1",
                    (telegram_id,),
                )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_students(self, telegram_id: int) -> List[Dict]:
        """Obtiene todos los estudiantes de un usuario por su telegram_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s.*, u.apellidos_autorizado, u.nombre_autorizado "
                "FROM students s LEFT JOIN users u ON s.telegram_id = u.telegram_id "
                "WHERE s.telegram_id = ? ORDER BY s.created_at ASC",
                (telegram_id,),
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Obtiene los datos del usuario (autorizado)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users WHERE telegram_id = ?
            """, (telegram_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_student(self, telegram_id: int, field: str, value: str, student_id: int = None) -> bool:
        """Actualiza un campo específico de un estudiante"""
        allowed_fields = ['clave_instituto', 'apellidos_estudiante', 'nombre_estudiante']
        if field not in allowed_fields:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if student_id:
                    query = f"UPDATE students SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ? AND id = ?"
                    cursor.execute(query, (value, telegram_id, student_id))
                else:
                    # Si no se especifica student_id, actualiza el primer estudiante (para compatibilidad)
                    query = f"UPDATE students SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ? AND id = (SELECT id FROM students WHERE telegram_id = ? ORDER BY created_at ASC LIMIT 1)"
                    cursor.execute(query, (value, telegram_id, telegram_id))
                return cursor.rowcount > 0
        except Exception:
            return False

    def update_user(self, telegram_id: int, field: str, value: str) -> bool:
        """Actualiza un campo del autorizado (tabla users)"""
        allowed_fields = ['apellidos_autorizado', 'nombre_autorizado']
        if field not in allowed_fields:
            return False
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = f"UPDATE users SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?"
                cursor.execute(query, (value, telegram_id))
                return cursor.rowcount > 0
        except Exception:
            return False
    
    def delete_student(self, telegram_id: int, student_id: int = None) -> bool:
        """Elimina un estudiante de la base de datos"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if student_id:
                    cursor.execute("DELETE FROM students WHERE telegram_id = ? AND id = ?", (telegram_id, student_id))
                else:
                    cursor.execute("DELETE FROM students WHERE telegram_id = ?", (telegram_id,))
                return cursor.rowcount > 0
        except Exception:
            return False
    
    def student_exists(self, telegram_id: int) -> bool:
        """Verifica si un usuario tiene al menos un estudiante registrado"""
        return self.get_student(telegram_id) is not None
    
    def get_student_count(self, telegram_id: int) -> int:
        """Obtiene el número de estudiantes registrados por un usuario"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM students WHERE telegram_id = ?", (telegram_id,))
            return cursor.fetchone()[0]
    
    def get_all_students(self) -> List[Dict]:
        """Obtiene todos los estudiantes (útil para administración)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_students_with_authorized(self) -> List[Dict]:
        """
        Obtiene una lista de estudiantes junto con el nombre y apellidos del alumno, 
        nombre y apellidos del autorizado, y chat_id.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    s.nombre_estudiante,
                    s.apellidos_estudiante,
                    s.clave_instituto,
                    u.nombre_autorizado,
                    u.apellidos_autorizado,
                    u.telegram_id as chat_id
                FROM students s
                JOIN users u ON s.telegram_id = u.telegram_id
                ORDER BY s.created_at DESC
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    "nombre_estudiante": row["nombre_estudiante"],
                    "apellidos_estudiante": row["apellidos_estudiante"],
                    "clave_instituto": row["clave_instituto"],
                    "nombre_autorizado": row["nombre_autorizado"],
                    "apellidos_autorizado": row["apellidos_autorizado"],
                    "chat_id": row["chat_id"],
                })
            return result
