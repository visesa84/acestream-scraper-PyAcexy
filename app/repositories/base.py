from typing import TypeVar, Generic, Type
from ..extensions import db

T = TypeVar('T')

class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model
        self._db = db

    def get_all(self):
        return self.model.query.all()

    def get_by_id(self, id):
        return self.model.query.get(id)

    def add(self, entity: T):
        self._db.session.add(entity)
        
    def delete(self, entity: T):
        self._db.session.delete(entity)
        
    def commit(self):
        self._db.session.commit()
        
    def rollback(self):
        self._db.session.rollback()