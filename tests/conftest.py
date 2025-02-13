import pytest
from app import create_app
from app.extensions import db
from app.models import ScrapedURL, AcestreamChannel

@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
    })
    
    # Create tables before yielding app
    with app.app_context():
        db.create_all()  # This line ensures tables are created
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()

@pytest.fixture
def db_session(app):
    """Create database session for testing."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        
        # Create a session bound to the connection
        session = db.create_scoped_session(
            options={"bind": connection, "binds": {}}
        )
        
        # Set the session for the db
        db.session = session
        
        yield session
        
        # Cleanup
        transaction.rollback()
        connection.close()
        session.remove()