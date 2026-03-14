import os
import asyncio
import threading
import logging
import fasteners
import time
from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from app.extensions import db, migrate
from app.tasks.recorder import process_recordings

# El task_manager se define como None y se inicializa dentro de create_app
task_manager = None

def create_app(test_config=None):
    """Create and configure the Flask app."""
    
    # Importaciones locales para evitar IMPORTACIÓN CIRCULAR
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

    # 1. Cargar Configuración Inicial
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

    # 2. Inicializar Extensiones
    db.init_app(app)
    migrate.init_app(app, db)

    # 3. Registrar Blueprints
    from app.api import bp as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # Importamos el blueprint y el módulo para inyectar el manager
    from app.views.main import bp as main_blueprint
    import app.views.main as main_module
    
    # Inyectar el task_manager global en el módulo de vistas
    main_module.task_manager = task_manager
    app.register_blueprint(main_blueprint)

    # 4. Inicialización con Contexto de Aplicación
    is_testing = test_config == 'testing' or os.environ.get('TESTING') == '1'
    app.config['TESTING'] = is_testing

    with app.app_context():
        try:
            try:
                logger.info("Initializing database tables...")
                db.create_all()
            except Exception as e:
                logger.info("Tables already exist.")
            
            settings_repo = SettingsRepository()
            config.set_settings_repository(settings_repo)

            # Arrancar Task Manager con BLOQUEO DE PROCESO
            if not is_testing:
                task_manager.init_app(app)

                def run_background_loop():
                    from app.tasks.recorder import process_recordings # Importación local
                    
                    lock = fasteners.InterProcessLock('/tmp/task_manager.lock')
                    got_lock = lock.acquire(blocking=False)
                    
                    if not got_lock:
                        logger.info("[Worker] TaskManager/Recorder is already active. Skipping.")
                        return

                    logger.info("[MANAGER] Lock acquired! Starting background loops.")
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    async def combined_tasks():
                        # TaskManager
                        # Si tu task_manager.start() es un bucle infinito, lo lanzamos como tarea
                        asyncio.create_task(task_manager.start())
                        
                        # El Grabador
                        while True:
                            try:
                                # Ejecutamos el grabador en un hilo separado para no bloquear el bucle asíncrono
                                await loop.run_in_executor(None, process_recordings, app)
                            except Exception as e:
                                logger.error(f"Error in recording worker: {e}")
                            
                            # Esperar 60 segundos antes de la siguiente revisión
                            await asyncio.sleep(60)

                    try:
                        loop.run_until_complete(combined_tasks())
                    except Exception as e:
                        logger.error(f"Background loop crashed: {e}")
                    finally:
                        if lock.exists():
                            lock.release()
                        loop.close()
                
                thread = threading.Thread(
                    target=run_background_loop, 
                    name="TaskManagerThread", 
                    daemon=True
                )
                thread.start()

        except Exception as e:
            logger.error(f"Fatal error during app startup: {e}", exc_info=True)

    @app.route('/')
    def index():
        # Ahora main.dashboard existirá porque el Blueprint se registró correctamente
        return redirect(url_for('main.dashboard'))

    return app
