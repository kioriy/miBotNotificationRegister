#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de migración de base de datos
Migra de la estructura antigua a la nueva estructura con campos separados
"""
import sqlite3
import os
from datetime import datetime

def migrate_database():
    """Migra la base de datos a la nueva estructura con tablas separadas"""
    db_name = "students.db"
    backup_name = f"students_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    
    # Crear backup
    if os.path.exists(db_name):
        print(f"Creando backup: {backup_name}")
        import shutil
        shutil.copy2(db_name, backup_name)
        print("Backup creado exitosamente")
    
    # Conectar a la base de datos
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Verificar si la tabla antigua existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
        if cursor.fetchone():
            # Leer datos antiguos
            cursor.execute("SELECT * FROM students")
            old_data = cursor.fetchall()
            
            if old_data:
                print(f"\nEncontrados {len(old_data)} registros para migrar")
                
                # Eliminar tabla antigua
                cursor.execute("DROP TABLE students")
                print("Tabla antigua eliminada")
                
                # Crear nuevas tablas
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id INTEGER PRIMARY KEY,
                        apellidos_autorizado TEXT NOT NULL,
                        nombre_autorizado TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
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
                print("Nuevas tablas creadas")
                
                # Migrar datos
                for row in old_data:
                    # Crear usuario si no existe
                    cursor.execute("""
                        INSERT OR IGNORE INTO users 
                        (telegram_id, apellidos_autorizado, nombre_autorizado, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        row['telegram_id'],
                        row['apellidos_autorizado'],
                        row['nombre_autorizado'],
                        row['created_at'],
                        row['updated_at']
                    ))
                    
                    # Crear estudiante
                    cursor.execute("""
                        INSERT INTO students 
                        (telegram_id, clave_instituto, apellidos_estudiante, nombre_estudiante, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        row['telegram_id'],
                        row['clave_instituto'],
                        row['apellidos_estudiante'],
                        row['nombre_estudiante'],
                        row['created_at'],
                        row['updated_at']
                    ))
                
                conn.commit()
                print(f"{len(old_data)} registros migrados exitosamente")
            else:
                print("No hay datos para migrar, creando tablas nuevas...")
                cursor.execute("DROP TABLE IF EXISTS students")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id INTEGER PRIMARY KEY,
                        apellidos_autorizado TEXT NOT NULL,
                        nombre_autorizado TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
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
                conn.commit()
                print("Nuevas tablas creadas (sin datos)")
        else:
            print("No existe tabla anterior, creando nueva estructura...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    apellidos_autorizado TEXT NOT NULL,
                    nombre_autorizado TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
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
            conn.commit()
            print("Nuevas tablas creadas")
        
        print("\nMigracion completada exitosamente")
        
    except Exception as e:
        conn.rollback()
        print(f"\nError durante la migracion: {e}")
        print(f"Puedes restaurar el backup: {backup_name}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("MIGRACIÓN DE BASE DE DATOS")
    print("=" * 60)
    migrate_database()
    print("=" * 60)
