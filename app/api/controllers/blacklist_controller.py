from flask import request
from flask_restx import Namespace, Resource
from app.extensions import db
from app.models import BlacklistedChannel

# Definimos el namespace para la blacklist
api = Namespace('blacklist', description='Global Blacklist Channel Management')

@api.route('/')
class BlacklistList(Resource):
    def get(self):
        """Get all global blacklisted channels/patterns."""
        try:
            items = BlacklistedChannel.query.all()
            return [item.to_dict() for item in items], 200
        except Exception as e:
            api.abort(500, f"Error fetching blacklist: {str(e)}")

    def post(self):
        """Add a pattern to the global blacklist."""
        data = request.json or {}
        pattern = data.get('pattern', '').strip()
        
        if not pattern:
            api.abort(400, "Pattern is required")
            
        try:
            # Evitamos duplicados en la base de datos
            exists = BlacklistedChannel.query.filter_by(pattern=pattern).first()
            if exists:
                return exists.to_dict(), 200
                
            new_item = BlacklistedChannel(pattern=pattern)
            db.session.add(new_item)
            db.session.commit()
            
            return new_item.to_dict(), 201
        except Exception as e:
            db.session.rollback()
            api.abort(500, f"Failed to add term: {str(e)}")


@api.route('/<int:id>')
@api.param('id', 'The pattern identifier')
class BlacklistPattern(Resource):
    def delete(self, id):
        """Remove a pattern from the global blacklist."""
        item = BlacklistedChannel.query.get_or_404(id)
        try:
            db.session.delete(item)
            db.session.commit()
            return {'message': 'Pattern removed successfully'}, 200
        except Exception as e:
            db.session.rollback()
            api.abort(500, f"Failed to delete term: {str(e)}")