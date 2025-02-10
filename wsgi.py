import os
from app import app
from app.tasks import Base, engine, refresh_acestream_channels

if __name__ == '__main__':
    # Ensure the database and table are created
    Base.metadata.create_all(engine)

    port = int(os.getenv('HOST_PORT', 8000))
    refresh_acestream_channels()
    app.run(host='0.0.0.0', port=port)
