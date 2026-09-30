RQ / Redis setup (local dev)

1) Install Redis
   - Docker (recommended):
       docker run -p 6379:6379 --name local-redis -d redis:7
   - Windows: use WSL or Redis MSI builds; Docker is easiest.

2) Install Python deps
   pip install rq redis

3) Configure runtime
   - In Admin Settings API (PUT /admin/settings) set job_backend='rq' and redis_url='redis://localhost:6379/0'

4) Start worker
   - From repo root:
       python scripts/start_rq_worker.py --redis redis://localhost:6379/0 --queue default
   - Or run with rq directly:
       rq worker --with-scheduler

5) Notes
   - Our jobs module supports both in-process queue and RQ. If redis not available, leave job_backend='inprocess'.
   - For production, run Redis as a managed service and supervise RQ workers.
