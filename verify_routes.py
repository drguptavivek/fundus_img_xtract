from app import create_app
from flask import url_for

app = create_app()

with app.test_request_context():
    routes = [
        ('grading.index', {}, 'Dashboard'),
        ('grading.remedio_glaucoma_image', {'uuid': 'test-uuid'}, 'Remedio Glaucoma Image'),
        ('grading.remedio_glaucoma_grade', {}, 'Remedio Glaucoma Grade'),
        ('grading.remedio_glaucoma_remove', {}, 'Remedio Glaucoma Remove'),
        ('grading.remedio_dr_image', {'uuid': 'test-uuid'}, 'Remedio DR Image'),
        ('grading.remedio_dr_grade', {}, 'Remedio DR Grade'),
        ('grading.remedio_dr_remove', {}, 'Remedio DR Remove'),
        ('grading.direct_image', {'uuid': 'test-uuid'}, 'Direct Image'),
        ('grading.direct_glaucoma_grade', {}, 'Direct Glaucoma Grade'),
        ('grading.direct_glaucoma_remove', {}, 'Direct Glaucoma Remove'),
    ]
    
    print("Route Mappings:")
    print("=" * 50)
    for endpoint, params, description in routes:
        try:
            url = url_for(endpoint, **params)
            print(f"{description:25} | {endpoint:35} | {url}")
        except Exception as e:
            print(f"{description:25} | {endpoint:35} | ERROR: {e}")