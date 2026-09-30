"""LOCAL TEST ONLY: real content routes backed by a temporary SQLite database.

Run with uvicorn bound to 127.0.0.1, never expose this fixture as the main API.
The authenticated owner is a test identity, not an account in the real database.
"""
import atexit

from tests.test_clip_revision_plans import ClipRevisionPlanTests
from app.database.models import UserContent

fixture = ClipRevisionPlanTests()
fixture.setUp()
with fixture.sessions() as db:
    db.get(UserContent, fixture.content_id).title = 'TEST FIXTURE: Phone review'
    db.commit()
app = fixture.app
atexit.register(fixture.tearDown)


@app.get('/verification/info')
def info():
    return {'fixture': True, 'content_id': fixture.content_id, 'title': 'TEST FIXTURE: Phone review',
            'recommendation': fixture.snapshot}
