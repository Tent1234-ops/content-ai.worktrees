import sys
from app.database.db import SessionLocal
from app.database.models import User
from app.services.dashboard import build_dashboard_overview
from app.runtime import set as runtime_set

print('python start')
s = SessionLocal()
try:
    user = s.query(User).first()
    print('user', user.user_id if user else 'none')
    if not user:
        sys.exit(0)
    runtime_set('dashboard_live', True)
    overview = build_dashboard_overview(db=s, current_user=user, region='TH', trend_mode='auto', trend_limit=3)
    print('overview keys', list(overview.keys()))
    print('youtube trends count', overview['youtube_trends']['total'], 'mode', overview['youtube_trends']['mode'])
    print('platform summaries', overview['platform_summaries'])
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    s.close()
