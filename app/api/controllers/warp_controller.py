import logging
import os
from flask_restx import Namespace, Resource, fields
from flask import request
from app.services.warp_service import WarpService, WarpMode as ModeEnum

logger = logging.getLogger(__name__)

api = Namespace('warp', description='Cloudflare WARP management')

# Define models for input and output
warp_status_model = api.model('WarpStatus', {
    'running': fields.Boolean(description='Whether the WARP daemon is running'),
    'connected': fields.Boolean(description='Whether WARP is connected'),
    'mode': fields.String(description='Current WARP mode'),
    'account_type': fields.String(description='Account type: free/premium/team'),
    'ip': fields.String(description='Current IP address when connected'),
    'enabled': fields.Boolean(description='Whether WARP is enabled in the container'),
    'cf_trace': fields.Raw(description='Cloudflare trace information')
})

mode_input_model = api.model('ModeInput', {
    'mode': fields.String(required=True, description='WARP mode to set: warp/dot/proxy/off')
})

license_input_model = api.model('LicenseInput', {
    'license_key': fields.String(required=True, description='WARP license key to register')
})

response_model = api.model('WarpResponse', {
    'status': fields.String(description='Status of the operation: success/error'),
    'message': fields.String(description='Descriptive message')
})

warp_service = WarpService()

def is_warp_enabled():
    """Check if WARP is enabled in the container."""
    return os.environ.get('ENABLE_WARP', 'false').lower() == 'true'

def handle_service_error(e: Exception, operation: str):
    """Handle service errors consistently."""
    logger.error(f"Error in WARP controller - {operation}: {str(e)}")
    api.abort(500, f"Failed to {operation}: {str(e)}")

@api.route('/status')
class WarpStatus(Resource):
    @api.doc('get_warp_status')
    @api.marshal_with(warp_status_model)
    def get(self):
        """Get the current status of WARP"""
        try:
            status = warp_service.get_status() if is_warp_enabled() else {
                'running': False,
                'connected': False,
                'mode': None,
                'account_type': 'unknown',
                'ip': None
            }
            status['enabled'] = is_warp_enabled()
            return status
        except Exception as e:
            handle_service_error(e, "get WARP status")

@api.route('/connect')
class WarpConnect(Resource):
    @api.doc('connect_warp')
    @api.response(200, 'Connected successfully')
    @api.response(403, 'WARP is not enabled')
    @api.response(500, 'Connection failed')
    @api.marshal_with(response_model)
    def post(self):
        """Connect to WARP"""
        if not is_warp_enabled():
            return {'status': 'error', 'message': 'WARP is not enabled in this container'}, 403
        try:
            result = warp_service.connect()
            if result:
                return {'status': 'success', 'message': 'Connected to WARP'}, 200
            else:
                return {'status': 'error', 'message': 'Failed to connect to WARP'}, 500
        except Exception as e:
            handle_service_error(e, "connect to WARP")

@api.route('/disconnect')
class WarpDisconnect(Resource):
    @api.doc('disconnect_warp')
    @api.response(200, 'Disconnected successfully')
    @api.response(403, 'WARP is not enabled')
    @api.response(500, 'Disconnection failed')
    @api.marshal_with(response_model)
    def post(self):
        """Disconnect from WARP"""
        if not is_warp_enabled():
            return {'status': 'error', 'message': 'WARP is not enabled in this container'}, 403
        try:
            result = warp_service.disconnect()
            if result:
                return {'status': 'success', 'message': 'Disconnected from WARP'}, 200
            else:
                return {'status': 'error', 'message': 'Failed to disconnect from WARP'}, 500
        except Exception as e:
            handle_service_error(e, "disconnect from WARP")

@api.route('/mode')
class WarpModeResource(Resource):
    @api.doc('set_warp_mode')
    @api.expect(mode_input_model)
    @api.marshal_with(response_model)
    def put(self):
        """Set the WARP mode"""
        if not is_warp_enabled():
            return {'status': 'error', 'message': 'WARP is not enabled'}, 403
        
        data = request.json
        mode_str = data.get('mode', '').lower()
        
        try:
            try:
                # ModeEnum(mode_str) busca el valor en el Enum definido en warp_service
                target_mode = ModeEnum(mode_str)
            except ValueError:
                return {'status': 'error', 'message': f'Invalid mode: {mode_str}. Use: warp, dot, proxy or off'}, 400

            # Pasamos el miembro del Enum al servicio
            result = warp_service.set_mode(target_mode)
            
            if result:
                return {'status': 'success', 'message': f'WARP mode changed to {mode_str}'}, 200
            else:
                return {'status': 'error', 'message': 'Failed to apply mode (check logs)'}, 500
                
        except Exception as e:
            # Esto atrapará cualquier error de referencia como el que tuviste
            return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}, 500

@api.route('/license')
class WarpLicense(Resource):
    @api.doc('register_warp_license')
    @api.expect(license_input_model)
    @api.response(200, 'License registered successfully')
    @api.response(400, 'License key not specified')
    @api.response(403, 'WARP is not enabled')
    @api.response(500, 'Failed to register license')
    @api.marshal_with(response_model)
    def post(self):
        """Register a WARP license key"""
        if not is_warp_enabled():
            return {'status': 'error', 'message': 'WARP is not enabled in this container'}, 403
        try:
            data = request.json
            if not data or 'license_key' not in data:
                return {'status': 'error', 'message': 'License key not specified'}, 400
            
            result = warp_service.register_license(data['license_key'])
            if result:
                return {'status': 'success', 'message': 'License registered successfully'}, 200
            else:
                return {'status': 'error', 'message': 'Failed to register license'}, 500
        except Exception as e:
            handle_service_error(e, "register WARP license")
