#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migración de base de datos a versión 2
Agrega campos: grado, grupo, nivel_escolar, datos_estudiante, datos_autorizado
"""
import sqlite3
import os
from datetime import datetime

def migrate_database_v2():
    """Migra la base de datos agregando los nuevos campos"""
    db_name = "students.db"
    backup_name = f"students_backup_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    # Crear backup
    if os.path.exists(db_name):
        print(f"Creando backup: {backup_name}")
        import shutil
        shutil.copy2(db_name, backup_name)
        print("Backup creado exitosamente")
    else:
        print("No existe base de datos para migrar")
        return

    # Conectar a la base de datos
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        print("\n" + "="*60)
        print("MIGRACIÓN DE BASE DE DATOS A VERSIÓN 2")
        print("="*60)

        # Verificar si las columnas ya existen
        cursor.execute("PRAGMA table_info(students)")
        students_columns = [col[1] for col in cursor.fetchall()]

        cursor.execute("PRAGMA table_info(users)")
        users_columns = [col[1] for col in cursor.fetchall()]

        # Agregar columnas a la tabla students si no existen
        new_student_columns = {
            'grado': 'TEXT',
            'grupo': 'TEXT',
            'nivel_escolar': 'TEXT',
            'datos_estudiante': "TEXT DEFAULT '{}'"
        }

        for col_name, col_type in new_student_columns.items():
            if col_name not in students_columns:
                print(f"Agregando columna '{col_name}' a tabla students...")
                cursor.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}")
                print(f"✓ Columna '{col_name}' agregada")
            else:
                print(f"⊘ Columna '{col_name}' ya existe en students")

        # Agregar columna a la tabla users si no existe
        if 'datos_autorizado' not in users_columns:
            print(f"Agregando columna 'datos_autorizado' a tabla users...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN datos_autorizado TEXT DEFAULT '{{}}'")
            print(f"✓ Columna 'datos_autorizado' agregada")
        else:
            print(f"⊘ Columna 'datos_autorizado' ya existe en users")

        # Verificar si necesitamos reordenar nombre_estudiante y apellidos_estudiante
        # (el nuevo orden es: nombre_estudiante, apellidos_estudiante)
        cursor.execute("PRAGMA table_info(students)")
        columns_info = cursor.fetchall()
        nombre_idx = next((i for i, col in enumerate(columns_info) if col[1] == 'nombre_estudiante'), None)
        apellidos_idx = next((i for i, col in enumerate(columns_info) if col[1] == 'apellidos_estudiante'), None)

        if nombre_idx is not None and apellidos_idx is not None and apellidos_idx < nombre_idx:
            print("\nReordenando columnas nombre_estudiante y apellidos_estudiante...")
            # Necesitamos recrear la tabla con el orden correcto
            cursor.execute("""
                CREATE TABLE students_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    clave_instituto TEXT NOT NULL,
                    nombre_estudiante TEXT NOT NULL,
                    apellidos_estudiante TEXT NOT NULL,
                    grado TEXT,
                    grupo TEXT,
                    nivel_escolar TEXT,
                    datos_estudiante TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(telegram_id, apellidos_estudiante, nombre_estudiante),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)

            # Copiar datos
            cursor.execute("""
                INSERT INTO students_new
                SELECT id, telegram_id, clave_instituto, nombre_estudiante, apellidos_estudiante,
                       grado, grupo, nivel_escolar, datos_estudiante, created_at, updated_at
                FROM students
            """)

            # Reemplazar tabla
            cursor.execute("DROP TABLE students")
            cursor.execute("ALTER TABLE students_new RENAME TO students")
            print("✓ Columnas reordenadas correctamente")

        conn.commit()
        print("\n" + "="*60)
        print("MIGRACIÓN COMPLETADA EXITOSAMENTE")
        print("="*60)
        print(f"\nBase de datos actualizada a versión 2")
        print(f"Backup guardado en: {backup_name}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error durante la migración: {e}")
        print(f"La base de datos no fue modificada")
        print(f"Puedes restaurar el backup si es necesario: {backup_name}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database_v2()
