import pytest
from app import create_app
from app.extensions import db
from app.models import ScrapedURL, AcestreamChannel
from app.utils.config import Config
import sqlalchemy

@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False
    })
    return app

@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()

@pytest.fixture
def db_session(app):
    """Create database session for testing."""
    with app.app_context():
        db.create_all()
        
        # Create a new connection for each test
        connection = db.engine.connect()
        transaction = connection.begin()
        
        # Bind session to connection
        options = dict(bind=connection, binds={})
        session = db.create_scoped_session(options=options)
        
        # Make session available to all models
        db.session = session
        
        yield session
        
        # Rollback transaction and close connection
        session.close()
        transaction.rollback()
        connection.close()
        
        # Clean up tables
        db.drop_all()

@pytest.fixture
def config():
    """Provide test configuration."""
    test_config = Config()
    test_config._config = {
        "urls": [],
        "base_url": "acestream://"
    }
    return test_config