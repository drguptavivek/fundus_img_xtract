from flask import Blueprint

bp = Blueprint('search', __name__, url_prefix='/search')

# Import routes to register them with the blueprint
from . import route_search_images
