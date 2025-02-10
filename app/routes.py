from flask import request, Response, render_template, jsonify
from app import app
from app.tasks import refresh_acestream_channels, generate_m3u_content, Session, AcestreamChannel, ScrapedURL, load_urls_from_config

last_refresh_date = None
last_item_count = 0

@app.route('/list.m3u', methods=['GET'])
def get_m3u_file():
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    if refresh:
        refresh_acestream_channels()
    
    base_url = request.args.get('base_url', app.config['base_url'])
    m3u_content = generate_m3u_content(base_url)
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
            refresh_acestream_channels()
    
    channels = Session.query(AcestreamChannel).all()
    current_item_count = len(channels)

    urls_info = Session.query(ScrapedURL).all()  # Get scraped URLs with status and last processed timestamp

    return render_template('index.html', urls=urls_info, last_refresh_date=last_refresh_date, last_item_count=last_item_count, current_item_count=current_item_count, channels=channels)
