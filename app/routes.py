import os
from flask import request, Response, render_template, jsonify
from app import app
from app.task_manager import refresh_acestream_channels, generate_m3u_content
from app.db_setup import setup_database, ScrapedURL, AcestreamChannel

# Set the config directory
config_dir = '/app/config' if os.getenv('DOCKER_ENV') == 'true' else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))

# Setup the database
Session = setup_database(config_dir)

last_refresh_date = None
last_item_count = 0

@app.route('/list.m3u', methods=['GET'])
def get_m3u_file():
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    if refresh:
        last_refresh_date = refresh_acestream_channels(config_dir, Session)
    
    base_url = request.args.get('base_url', app.config['base_url'])
    m3u_content = generate_m3u_content(base_url, Session)
    return Response(m3u_content, mimetype='audio/x-mpegurl')

@app.route('/', methods=['GET', 'POST'])
def get_acestream_list():
    global last_refresh_date, last_item_count
    if request.method == 'POST':
        new_url = request.form.get('new_url')
        if new_url:
            if not Session.query(ScrapedURL).filter_by(url=new_url).first():
                url_record = ScrapedURL(url=new_url, status='Pending', last_processed=None)
                Session.add(url_record)
                Session.commit()
            last_refresh_date = refresh_acestream_channels(config_dir, Session)
    
    channels = Session.query(AcestreamChannel).all()
    current_item_count = len(channels)

    urls_info = Session.query(ScrapedURL).all()  # Get scraped URLs with status and last processed timestamp

    return render_template('index.html', urls=urls_info, last_refresh_date=last_refresh_date, last_item_count=last_item_count, current_item_count=current_item_count, channels=channels)

@app.route('/refresh', methods=['POST'])
def force_refresh():
    global last_refresh_date
    last_refresh_date = refresh_acestream_channels(config_dir, Session)
    return jsonify({'status': 'Refresh initiated', 'last_refresh_date': last_refresh_date})
