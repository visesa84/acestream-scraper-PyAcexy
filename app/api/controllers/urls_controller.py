from flask_restx import Namespace, Resource, fields, reqparse
from flask import request, current_app
from app.extensions import db
from app.models import ScrapedURL, BlacklistedChannel
from app.repositories import URLRepository, ChannelRepository
from app.services.scraper_service import clean_channel_name
from datetime import datetime, timezone
from app.tasks.manager import TaskManager
from urllib.parse import unquote
import logging

logger = logging.getLogger(__name__)

task_manager = TaskManager()

api = Namespace('urls', description='URL management')

url_input_model = api.model('URLInput', {
    'url': fields.String(required=True, description='URL to scrape')
})

url_update_model = api.model('URLUpdate', {
    'enabled': fields.Boolean(description='Whether the URL is enabled')
})

url_model = api.model('URL', {
    'id': fields.String(description='Unique identifier for the URL'),
    'url': fields.String(description='URL being scraped'),
    'url_type': fields.String(description='Type of URL (regular, zeronet)'),
    'status': fields.String(description='Current status of the URL'),
    'last_scraped': fields.DateTime(description='When the URL was last processed'),
    'enabled': fields.Boolean(description='Whether the URL is enabled'),
    'error_count': fields.Integer(description='Number of consecutive errors'),
    'last_error': fields.String(description='Last error message, if any')
})

url_repo = URLRepository()
channel_repo = ChannelRepository()

@api.route('/')
class URLList(Resource):
    @api.doc('list_urls')
    @api.marshal_list_with(url_model)
    def get(self):
        """Get list of all URLs."""
        try:
            urls = ScrapedURL.query.all()
            return urls
        except Exception as e:
            api.abort(500, str(e))
    
    @api.doc('create_url')
    @api.expect(url_input_model)
    @api.response(201, 'URL or search created and queued')
    @api.response(409, 'URL already exists')
    @api.response(400, 'Invalid input')
    def post(self):
        """Add a new URL to scrape or search channels by name."""
        data = request.json or {}
        
        try:
            input_text = data.get('url', '').strip()
            if not input_text:
                return {'error': 'URL or search term is required'}, 400
                
            url_type = data.get('url_type')

            # ----------------------------------------------------
            # 1. SI NO ES UNA URL WEB -> MODO BÚSQUEDA DE CANAL
            # ----------------------------------------------------
            is_web_url = input_text.startswith(('http://', 'https://', 'ipfs://', 'zeronet://'))
            
            if not is_web_url or url_type == 'search':
                from app.services.acestream_search_service import AcestreamSearchService
                import asyncio
                import inspect

                search_service = AcestreamSearchService()
                
                # Ejecutar barrido masivo con search_all_pages
                if inspect.iscoroutinefunction(search_service.search_all_pages):
                    raw_response = asyncio.run(search_service.search_all_pages(query=input_text))
                else:
                    raw_response = search_service.search_all_pages(query=input_text)

                if isinstance(raw_response, dict):
                    results_list = raw_response.get('results', [])
                else:
                    results_list = raw_response or []

                if not results_list:
                    return {'error': f'No Acestream channels found for query "{input_text}"'}, 404

                # Crear slug para la URL virtual
                slug = input_text.lower().replace(' ', '-')
                virtual_url = f"search://{slug}"

                # Guardar la fuente virtual
                existing = url_repo.get_by_url(virtual_url)
                if not existing:
                    url_obj = url_repo.add(virtual_url, 'search')
                    url_obj.status = 'OK'
                    url_repo.update(url_obj)
                else:
                    url_obj = existing

                # Traer patrones de la Blacklist Global
                blacklist_patterns = [b.pattern.lower().strip() for b in BlacklistedChannel.query.all()]

                added_count = 0
                ignored_count = 0
                seen_ids = set()

                # --- DESACTIVAR AUTOFLUSH TEMPORALMENTE (EVITA IntegrityError) ---
                with db.session.no_autoflush:
                    for res in results_list:
                        if not isinstance(res, dict):
                            continue
                            
                        content_id = res.get('content_id') or res.get('id') or res.get('acestream_id')
                        raw_name = res.get('name') or input_text
                        channel_name = clean_channel_name(raw_name)
                        
                        if content_id and content_id not in seen_ids:
                            name_lower = channel_name.lower().strip()
                            id_lower = content_id.lower().strip()

                            # Filtrado de Blacklist Global
                            is_blacklisted = any(
                                pattern in name_lower or pattern in id_lower 
                                for pattern in blacklist_patterns
                            )

                            if is_blacklisted:
                                logger.info(f"[Blacklist] Skipping channel: '{channel_name}' (ID: {content_id})")
                                ignored_count += 1
                                continue

                            seen_ids.add(content_id)
                            
                            channel_repo.update_or_create(
                                channel_id=content_id,
                                name=channel_name,
                                source_url=virtual_url,
                                metadata=res.get('metadata') or {}
                            )
                            added_count += 1

                channel_repo.commit()

                return {
                    'message': f'Search complete. Added {added_count} channels ({ignored_count} ignored by blacklist) for "{input_text}"',
                    'url': virtual_url,
                    'url_type': 'search',
                    'channels_added': added_count,
                    'channels_ignored': ignored_count
                }, 201

            # ----------------------------------------------------
            # 2. FLUJO NORMAL PARA URLS TRADICIONALES
            # ----------------------------------------------------
            if not url_type or url_type == 'auto':
                return {'error': "URL type must be explicitly specified as 'regular' or 'zeronet'"}, 400
            
            if url_type not in ['regular', 'zeronet']:
                return {'error': f"Invalid URL type: {url_type}. Must be 'regular' or 'zeronet'"}, 400
            
            existing = url_repo.get_by_url(input_text)
            if existing:
                api.abort(409, 'This URL already exists')
            
            url_obj = url_repo.add(input_text, url_type)
            
            try:
                task_manager.add_task('scrape_url', url_obj.url)
            except Exception as e:
                current_app.logger.error(f"Failed to queue URL for scraping: {e}")
            
            return {
                'message': 'URL added successfully and queued for processing',
                'url': url_obj.url,
                'url_type': url_obj.url_type
            }, 201
            
        except ValueError as ve:
            return {'error': str(ve)}, 400
        except Exception as e:
            logger.error(f"Error in create_url: {e}", exc_info=True)
            api.abort(500, str(e))

@api.route('/<uuid:id>')
@api.param('id', 'The URL ID to manage')
class URLItem(Resource):
    @api.doc('get_url')
    @api.marshal_with(url_model)
    @api.response(404, 'URL not found')
    def get(self, id):
        """Get details for a specific URL by ID."""
        try:
            url_obj = url_repo.get_by_id(str(id))
            if not url_obj:
                api.abort(404, 'URL not found')
            
            return url_obj
        except Exception as e:
            api.abort(500, str(e))
    
    @api.doc('update_url')
    @api.expect(url_update_model)
    @api.response(200, 'URL updated')
    @api.response(404, 'URL not found')
    def put(self, id):
        """Update a URL's properties by ID."""
        data = request.json
        
        try:
            url_obj = url_repo.get_by_id(str(id))
            if not url_obj:
                api.abort(404, 'URL not found')
            
            if 'enabled' in data:
                if data['enabled']:
                    url_obj.status = 'pending'
                else:
                    url_obj.status = 'disabled'
                url_obj.enabled = data['enabled']
                url_repo.update(url_obj)
            
            return {
                'message': 'URL updated successfully',
                'id': url_obj.id,
                'url': url_obj.url,
                'status': url_obj.status,
                'enabled': url_obj.enabled
            }
        except Exception as e:
            api.abort(500, str(e))
    
    @api.doc('delete_url')
    @api.response(204, 'URL deleted')
    @api.response(404, 'URL not found')
    def delete(self, id):
        """Delete a URL and its associated channels by ID."""
        try:
            logger.debug(f"Attempting to delete URL with ID: {id}")
            
            url_obj = url_repo.get_by_id(str(id))
            if not url_obj:
                logger.warning(f"URL not found for deletion: ID {id}")
                api.abort(404, 'URL not found')
            
            url_to_delete = url_obj.url
            
            if not channel_repo.delete_by_source(url_to_delete):
                logger.error(f"Failed to delete associated channels for URL: {url_to_delete}")
            
            if url_repo.delete(url_obj):
                logger.info(f"Successfully deleted URL: {url_to_delete} (ID: {id})")
                return '', 204
            
            logger.error(f"Failed to delete URL: {url_to_delete} (ID: {id})")
            api.abort(500, "Failed to delete URL")
            
        except Exception as e:
            logger.error(f"Error deleting URL: {e}", exc_info=True)
            api.abort(500, str(e))

@api.route('/<uuid:id>/refresh')
@api.param('id', 'The URL ID to refresh')
class URLRefresh(Resource):
    @api.doc('refresh_url')
    @api.response(200, 'URL queued for refreshing')
    @api.response(404, 'URL not found')
    @api.response(400, 'URL is disabled')
    def post(self, id):
        """Queue a specific URL for refreshing by ID."""
        try:
            url_obj = url_repo.get_by_id(str(id))
            if not url_obj:
                api.abort(404, 'URL not found')
            
            if not url_obj.enabled:
                api.abort(400, 'URL is disabled and cannot be refreshed')
            
            task_manager.add_task('scrape_url', url_obj.url)
            
            return {
                'message': 'URL queued for refreshing',
                'id': url_obj.id,
                'url': url_obj.url
            }
        except Exception as e:
            api.abort(500, str(e))

@api.route('/<path:url>/details')
@api.param('url', 'The URL string to manage')
class URLItemByUrl(Resource):
    @api.doc('get_url_by_url')
    @api.marshal_with(url_model)
    @api.response(404, 'URL not found')
    def get(self, url):
        """Get details for a specific URL (backward compatibility)."""
        try:
            decoded_url = unquote(url)
            url_obj = url_repo.get_by_url(decoded_url)
            if not url_obj:
                api.abort(404, 'URL not found')
            
            return url_obj
        except Exception as e:
            api.abort(500, str(e))

@api.route('/<path:url>/refresh')
@api.param('url', 'The URL to refresh')
class URLRefreshByUrl(Resource):
    @api.doc('refresh_url_by_url')
    @api.response(200, 'URL queued for refreshing')
    @api.response(404, 'URL not found')
    def post(self, url):
        """Queue a specific URL for refreshing (backward compatibility)."""
        try:
            decoded_url = unquote(url)
            url_obj = url_repo.get_by_url(decoded_url)
            if not url_obj:
                api.abort(404, 'URL not found')
            
            if not url_obj.enabled:
                api.abort(400, 'URL is disabled and cannot be refreshed')
            
            task_manager.add_task('scrape_url', decoded_url)
            
            return {
                'message': 'URL queued for refreshing',
                'id': url_obj.id,
                'url': decoded_url
            }
        except Exception as e:
            api.abort(500, str(e))

@api.route('/refresh')
class URLRefreshAll(Resource):
    @api.doc('refresh_all_urls')
    @api.response(200, 'Refresh process started for all enabled URLs')
    def post(self):
        """Refresca todas las URLs habilitadas de una vez."""
        try:
            enabled_urls = ScrapedURL.query.filter_by(enabled=True).all()
            
            urls_to_process = []
            for url_obj in enabled_urls:
                url_obj.status = 'processing'
                url_repo.update(url_obj)
                
                task_manager.add_task('scrape_url', url_obj.url)
                urls_to_process.append(url_obj.url)
            
            return {
                'message': f'Refresh started for {len(urls_to_process)} URLs',
                'urls': urls_to_process
            }, 200
        except Exception as e:
            logger.error(f"Error in global refresh: {e}")
            api.abort(500, str(e))