
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "smart_parking"),
            autocommit=False
        )
        return connection

    except mysql.connector.Error as error:
        raise RuntimeError(f"Database connection failed: {error}")


def fetch_all(query, params=None):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(query, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


def fetch_one(query, params=None):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(query, params or ())
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def execute_query(query, params=None):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(query, params or ())
        connection.commit()
        return cursor.lastrowid

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
