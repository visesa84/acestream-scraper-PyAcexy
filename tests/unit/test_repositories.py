import pytest
from datetime import datetime
from app.repositories import URLRepository, ChannelRepository
from app.models import ScrapedURL, AcestreamChannel

def test_url_repository_update_status(db_session):
    repo = URLRepository()
    url = "http://test.com"
    
    # Create URL object first
    url_obj = ScrapedURL(url=url)
    db_session.add(url_obj)
    db_session.commit()
    
    # Now test the update
    repo.update_status(url, "pending")
    url_obj = repo.get_by_url(url)
    assert url_obj is not None
    assert url_obj.status == "pending"
    assert url_obj.error_count == 0

def test_channel_repository_crud(db_session):
    repo = ChannelRepository()
    
    # Test create/update
    channel = repo.update_or_create(
        channel_id="test123",
        name="Test Channel",
        source_url="http://test.com"
    )
    repo.commit()
    
    assert channel.id == "test123"
    assert channel.name == "Test Channel"
    
    # Test get
    channels = repo.get_by_source("http://test.com")
    assert len(channels) == 1
    assert channels[0].id == "test123"
    
    # Test delete
    repo.delete_by_source("http://test.com")
    repo.commit()
    
    channels = repo.get_by_source("http://test.com")
    assert len(channels) == 0