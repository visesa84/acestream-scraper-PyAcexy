from flask import Blueprint, render_template, request, Response, current_app, redirect, url_for
from datetime import datetime, timezone
import logging

bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

# Referencia global para el manager
task_manager = None

@bp.route('/')
def index():
    from ..utils.config import Config
    config = Config()
    if config.settings_repo and config.settings_repo.is_setup_completed():
        return render_template('dashboard.html')
    return redirect(url_for('main.setup'))

@bp.route('/dashboard')
def dashboard():
    return index()

@bp.route('/setup')
def setup():
    from ..utils.config import Config
    config = Config()
    if config.is_initialized():
        return redirect(url_for('main.index'))
    return render_template('setup.html')

@bp.route('/playlist.m3u')
def get_playlist():
    from ..utils.config import Config
    from ..services import PlaylistService
    from ..repositories import URLRepository
    
    config = Config()
    if not config.is_initialized() and not current_app.testing:
        return redirect(url_for('main.setup'))
        
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    search = request.args.get('search', None)
    base_url_param = request.args.get('base_url', None)
    
    if refresh and task_manager:
        url_repository = URLRepository()
        urls = url_repository.get_enabled()
        for url in urls:
            task_manager.add_url(url.url)
    
    playlist_service = PlaylistService()
    if base_url_param:
        original_base_url = playlist_service.config.base_url
        playlist_service.config.base_url = base_url_param
        playlist = playlist_service.generate_playlist(search_term=search)
        playlist_service.config.base_url = original_base_url
    else:
        playlist = playlist_service.generate_playlist(search_term=search)
    
    return Response(playlist, mimetype="audio/x-mpegurl")

@bp.route('/search')
def search():
    from ..utils.config import Config
    config = Config()
    if not config.settings_repo or not config.settings_repo.is_setup_completed():
        return redirect(url_for('main.setup'))
    return render_template('search.html')

@bp.route('/config')
def config():
    return render_template('config.html')

@bp.route('/tv-channels')
def tv_channels():
    from ..utils.config import Config
    config = Config()
    if not config.settings_repo or not config.settings_repo.is_setup_completed():
        return redirect(url_for('main.setup'))
    return render_template('tv_channels.html')

@bp.route('/tv-channels/<int:tv_channel_id>')
def tv_channel_detail(tv_channel_id):
    from ..utils.config import Config
    config = Config()
    if not config.settings_repo or not config.settings_repo.is_setup_completed():
        return redirect(url_for('main.setup'))
    return render_template('tv_channel_detail.html', tv_channel_id=tv_channel_id)

@bp.route('/streams')
def streams():
    from ..utils.config import Config
    config = Config()
    if not config.settings_repo or not config.settings_repo.is_setup_completed():
        return redirect(url_for('main.setup'))
    return render_template('streams.html')

@bp.route('/epg')
def epg_management():
    from ..utils.config import Config
    config = Config()
    if not config.settings_repo or not config.settings_repo.is_setup_completed():
        return redirect(url_for('main.setup'))
    return render_template('epg.html')
