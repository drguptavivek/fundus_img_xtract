from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from models import Session, ImageGrading, EncounterFile, DirectImageUpload
from auth.roles import roles_required

bp = Blueprint('api_gradings', __name__, url_prefix='/api')

@bp.route('/gradings')
@login_required
@roles_required("admin", "resident", "ophthalmologist")
def get_gradings():
    """API endpoint to fetch filtered and paginated gradings data"""
    db = Session()
    try:
        page = request.args.get('page', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        
        # Filter parameters
        gfor = (request.args.get('gfor') or 'all').strip().lower()
        task_type = (request.args.get('task_type') or 'all').strip().lower()
        
        # Build query
        my_q = (
            db.query(ImageGrading)
              .options(
                  joinedload(ImageGrading.image),
                  joinedload(ImageGrading.direct_image)
              )
              .filter(ImageGrading.grader_user_id == getattr(current_user, 'id', None))
              .order_by(ImageGrading.updated_at.desc())
        )
        
        # Apply filters
        if gfor and gfor != 'all':
            my_q = my_q.filter(ImageGrading.graded_for == gfor)
            
        if task_type and task_type != 'all':
            # Filter by task type (dual grading tasks vs direct gradings)
            if task_type == 'dual':
                # Only show gradings that are part of a dual grading task
                my_q = my_q.filter(ImageGrading.task_id.isnot(None))
            elif task_type == 'single':
                # Only show gradings that are NOT part of a dual grading task
                my_q = my_q.filter(ImageGrading.task_id.is_(None))
        
        # Get total count and paginated results
        total_mine = my_q.count()
        items_mine = (
            my_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        
        # Convert items to JSON-serializable format
        gradings_data = []
        for g in items_mine:
            gradings_data.append({
                'id': g.id,
                'graded_at': (g.updated_at or g.created_at).strftime('%Y-%m-%d %H:%M') if g.updated_at or g.created_at else '-',
                'image_uuid': g.image.uuid if g.image else (g.direct_image.uuid if g.direct_image else None),
                'graded_for': g.graded_for,
                'impression': g.impression,
                'remarks': g.remarks or '',
                'image_type': 'encounter' if g.image else ('direct' if g.direct_image else None),
                'revise_url': get_revise_url(g)
            })
        
        # Prepare response
        response_data = {
            'gradings': gradings_data,
            'total': total_mine,
            'page': page,
            'total_pages': total_pages_mine,
            'has_prev': page > 1,
            'has_next': page < total_pages_mine,
            'prev_url': f"/api/gradings?gfor={gfor}&task_type={task_type}&page={page-1}" if page > 1 else None,
            'next_url': f"/api/gradings?gfor={gfor}&task_type={task_type}&page={page+1}" if page < total_pages_mine else None
        }
        
        return jsonify(response_data)
        
    finally:
        db.close()

def get_revise_url(grading):
    """Helper function to generate revise URL for a grading"""
    if grading.image and grading.image.uuid:
        if grading.graded_for == 'glaucoma':
            return f"/grading/remedio/glaucoma/{grading.image.uuid}"
        else:
            return f"/grading/remedio/dr/{grading.image.uuid}"
    elif grading.direct_image and grading.direct_image.uuid:
        return f"/grading/direct/{grading.direct_image.uuid}"
    return None