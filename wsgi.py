import os
from app import app
from app.db_setup import Base, setup_database
from app.task_manager import refresh_acestream_channels


if __name__ == '__main__':

    # Get the port from the environment variable or use the default port 8000
    port = int(os.getenv('HOST_PORT', 8000))
    app.run(host='0.0.0.0', port=port)
