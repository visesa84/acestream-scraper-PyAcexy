from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
# Importa event directamente desde sqlalchemy
from sqlalchemy import event

db = SQLAlchemy()
migrate = Migrate()

# En lugar de usar db.engine (que puede no estar listo), 
# usamos la clase Pool que es de donde nacen todas las conexiones.
from sqlalchemy.pool import Pool

@event.listens_for(Pool, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Esto solo se ejecuta si la base de datos es SQLite
    # Importante para no romper nada si luego cambias a Postgres
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    except Exception:
        # Si no es SQLite, ignoramos el error
        pass
