import pytest
from app.models import ScrapedURL, AcestreamChannel
from app.utils.config import Config

def test_get_playlist(client, db_session, config):
    # Override config for test
    Config._instance = config
    
    # Create test channel
    channel = AcestreamChannel(
        id="123",
        name="Test Channel",
        status="active"
    )
    db_session.add(channel)
    db_session.commit()
    
    response = client.get('/playlist.m3u')
    
    assert response.status_code == 200
    assert b'#EXTM3U' in response.data
    assert b'Test Channel' in response.data
    assert b'acestream://123' in response.data  # Fixed format

def test_add_url(client, db_session):
    response = client.post('/api/urls', json={
        'url': 'http://test.com'
    })
    
    assert response.status_code == 200
    assert response.json['message'] == 'URL added successfully and queued for processing'
    
    url = ScrapedURL.query.filter_by(url='http://test.com').first()
    assert url is not None
    assert url.status == 'pending'

def test_get_playlist_with_different_base_urls(client, db_session):
    """Test playlist endpoint with different base URL configurations."""
    # Create test channel
    channel = AcestreamChannel(
        id="123",
        name="Test Channel",
        status="active"
    )
    db_session.add(channel)
    db_session.commit()
    
    # Test with different base URLs
    test_cases = [
        ("acestream://", b"acestream://123"),
        ("http://localhost:8008/ace/getstream?id=", b"http://localhost:8008/ace/getstream?id=123")
    ]
    
    for base_url, expected in test_cases:
        # Override config for this test
        Config._instance._config = {"base_url": base_url}
        
        response = client.get('/playlist.m3u')
        assert response.status_code == 200
        assert b'#EXTM3U' in response.data
        assert b'Test Channel' in response.data
        assert expected in response.data