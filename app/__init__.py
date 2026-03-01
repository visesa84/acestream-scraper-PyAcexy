import os
import asyncio
import threading
import logging
from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from app.extensions import db, migrate

# El task_manager se define como None y se inicializa dentro de create_app
task_manager = None

def create_app(test_config=None):
    """Create and configure the Flask app."""
    
    # Importaciones locales para evitar IMPORTACIÓN CIRCULAR al arrancar
    from app.utils.config import Config
    from app.tasks.manager import TaskManager
    from app.repositories import SettingsRepository

    global task_manager
    if not task_manager:
        task_manager = TaskManager()

    app = Flask(__name__)

    # Middleware para proxies (Docker/Nginx)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config['PREFERRED_URL_SCHEME'] = 'http'

    # Configuración de Logging
    logging_level = logging.DEBUG if os.environ.get('FLASK_ENV') == 'development' else logging.INFO
    logging.basicConfig(
        level=logging_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Configuración básica
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
    app.config['DEBUG'] = os.environ.get('FLASK_ENV') == 'development'

    # 1. Cargar Configuración Inicial (Sin tocar Base de Datos aún)
    try:
        config = Config()
        if config.database_path:
            config.database_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Config directory verified: {config.database_path.parent}")
    
        app.config['SQLALCHEMY_DATABASE_URI'] = config.database_uri
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            "connect_args": {
                "timeout": 30,
                "check_same_thread": False 
            },
            "pool_pre_ping": True
        }
    except Exception as e:
        logger.error(f"Error initializing Config: {e}")
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    # 2. Inicializar Extensiones (Crucial antes de cualquier otra cosa)
    db.init_app(app)
    migrate.init_app(app, db)

    # 3. Registrar Blueprints
    try:
        from app.api import bp as api_blueprint
        app.register_blueprint(api_blueprint, url_prefix='/api')
        
        from app.views.main import bp as main_blueprint
        app.register_blueprint(main_blueprint)
        
        # Inyectar task_manager en el blueprint para compatibilidad
        main_blueprint.task_manager = task_manager
    except Exception as e:
        logger.warning(f"Error registering blueprints: {e}")

    # 4. Inicialización con Contexto de Aplicación
    is_testing = test_config == 'testing' or os.environ.get('TESTING') == '1'
    app.config['TESTING'] = is_testing

    with app.app_context():
        try:
            # Crear tablas si no existen
            logger.info("Initializing database tables...")
            db.create_all()
            
            # Vincular el repositorio a la configuración
            settings_repo = SettingsRepository()
            config.set_settings_repository(settings_repo)
            logger.info("Settings repository linked to Config")

            # Arrancar Task Manager en segundo plano (Solo si no es test)
            if not is_testing:
                task_manager.init_app(app)

                def run_background_loop():
                    # Crear un nuevo loop de asyncio para este hilo específico
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(task_manager.start())
                    except Exception as e:
                        logger.error(f"Task Manager loop crashed: {e}")
                    finally:
                        loop.close()
                
                # Daemon=True permite que el proceso principal se cierre correctamente
                thread = threading.Thread(target=run_background_loop, name="TaskManagerThread", daemon=True)
                thread.start()
                logger.info("TaskManager background thread started successfully")

        except Exception as e:
            logger.error(f"Fatal error during app startup: {e}", exc_info=True)

    @app.route('/')
    def index():
        return redirect(url_for('main.dashboard'))

    return app
