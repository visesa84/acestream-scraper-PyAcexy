import sys
import subprocess
import os
from app import create_app
from whitenoise import WhiteNoise

# 1. Migraciones
try:
    subprocess.run([sys.executable, "manage.py", "upgrade"], check=True)
except Exception as e:
    print(f"Migration error: {e}")

# 2. Crear App Flask
flask_app = create_app()

# 3. Envolver con WhiteNoise ANTES de WsgiToAsgi
# Esto servirá automáticamente /static/js/, /static/css/, etc.
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'static')
flask_app.wsgi_app = WhiteNoise(
    flask_app.wsgi_app, 
    root=static_dir,
    prefix='static/',
    max_age=31536000 
)

app = flask_app
