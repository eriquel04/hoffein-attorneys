"""Initialize the application schema and optional test accounts."""

from pathlib import Path

import mysql.connector

import app


def initialize_database():
    schema_path = Path(__file__).with_name("schema.sql")
    schema = schema_path.read_text(encoding="utf-8")

    connection = app.get_db_connection()
    cursor = connection.cursor()

    try:
        for statement in schema.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)

        connection.commit()
    finally:
        cursor.close()
        connection.close()

    app.ensure_organization_tables()
    app.create_test_accounts()
    app.create_lawyer_profile()


if __name__ == "__main__":
    initialize_database()
    print("Database initialization completed.")
