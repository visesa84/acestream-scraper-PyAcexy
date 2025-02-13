import os
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from app.utils.config import Config

app = Flask(__name__)
config = Config()
app.config['SQLALCHEMY_DATABASE_URI'] = config.database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

from app.models import AcestreamChannel, ScrapedURL