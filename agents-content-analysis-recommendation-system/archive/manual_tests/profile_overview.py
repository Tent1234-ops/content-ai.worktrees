import time
from app.database.db import SessionLocal
from app.database.models import User
from app.services.dashboard import build_dashboard_overview
from app.runtime import set as runtime_set

s = SessionLocal()
try:
    user = s.query(User).first()
    print('user', user.user_id if user else 'none')
    if not user:
        raise SystemExit('no user')
    runtime_set('dashboard_live', True)
    start = time.time()
    overview = build_dashboard_overview(db=s, current_user=user, region='TH', trend_mode='auto', trend_limit=3)
    print('elapsed', time.time()-start)
    print('top_trends', len(overview['top_trends']), 'youtube_items', overview['youtube_trends']['total'], 'mode', overview['youtube_trends']['mode'])
    print('platform_summaries', overview['platform_summaries'])
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    s.close()
