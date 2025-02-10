import os
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime

Base = declarative_base()

class AcestreamChannel(Base):
    __tablename__ = 'acestream_channels'
    id = Column(String, primary_key=True)
    name = Column(String)
    added_at = Column(DateTime, default=datetime.utcnow)
    last_processed = Column(DateTime)

class ScrapedURL(Base):
    __tablename__ = 'scraped_urls'
    url = Column(Text, primary_key=True)
    status = Column(String)
    last_processed = Column(DateTime)

def setup_database(config_dir):

    # Ensure the config directory exists
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    db_path = os.path.join(config_dir, 'acestream_channels.db')
    print(f"Database path: {db_path}")  # Debugging line to print the database path
    engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    return Session
