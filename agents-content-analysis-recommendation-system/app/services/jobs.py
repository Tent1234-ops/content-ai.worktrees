import threading
import uuid
import time
from datetime import datetime
from typing import Dict, Callable

from app.runtime import get as runtime_get

_jobs: Dict[str, Dict] = {}
_queue = []
_queue_lock = threading.Lock()
_worker_thread = None
_worker_stop = threading.Event()
_job_context = threading.local()

# Optional RQ support
try:
    import redis
    from rq import Queue, Connection
    _rq_available = True
except Exception:
    _rq_available = False


def _worker_loop():
    while not _worker_stop.is_set():
        job = None
        with _queue_lock:
            if _queue:
                job = _queue.pop(0)
        if not job:
            time.sleep(0.2)
            continue
        job_id = job["job_id"]
        func = job["func"]
        args = job.get("args", [])
        kwargs = job.get("kwargs", {})
        try:
            _job_context.job_id = job_id
            _jobs[job_id]["status"] = "running"
            update_job(job_id, stage="running", progress=10, message="Starting analysis")
            result = func(*args, **kwargs)
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["stage"] = "completed"
            _jobs[job_id]["progress"] = 100
            _jobs[job_id]["message"] = "Analysis completed"
            _jobs[job_id]["updated_at"] = datetime.utcnow().isoformat()
            _jobs[job_id]["result"] = result
        except Exception as e:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["stage"] = "failed"
            _jobs[job_id]["progress"] = _jobs[job_id].get("progress", 0)
            _jobs[job_id]["message"] = "Analysis failed"
            _jobs[job_id]["updated_at"] = datetime.utcnow().isoformat()
            _jobs[job_id]["error"] = str(e)
        finally:
            _job_context.job_id = None


def start_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _worker_stop.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()


def stop_worker():
    _worker_stop.set()
    global _worker_thread
    if _worker_thread:
        _worker_thread.join(timeout=2)


def _enqueue_inprocess(func: Callable, *args, job_id: str | None = None,
                       owner_user_id: int | None = None, **kwargs) -> str:
    job_id = job_id or str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Queued for analysis",
        "result": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "owner_user_id": owner_user_id,
    }
    with _queue_lock:
        _queue.append({"job_id": job_id, "func": func, "args": args, "kwargs": kwargs})
    start_worker()
    return job_id


def _enqueue_rq(func: Callable, *args, redis_url: str = None, job_id: str | None = None,
                owner_user_id: int | None = None, **kwargs) -> str:
    if not _rq_available:
        raise RuntimeError("RQ/redis not available in this environment. Install rq and redis package to enable this backend.")
    if not redis_url:
        raise RuntimeError("redis_url must be provided in runtime configuration to use RQ backend")

    # Connect and enqueue using RQ. We serialize by referencing a module-level callable via import path.
    # For safety in this environment, we only support enqueueing callables that are module-level functions (picklable by rq).
    q = None
    try:
        from redis import Redis
        redis_conn = Redis.from_url(redis_url)
        q = Queue(connection=redis_conn)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Redis at {redis_url}: {e}")

    # RQ returns job id
    job = q.enqueue(func, *args, job_timeout=-1, job_id=job_id, **kwargs)
    job.meta["owner_user_id"] = owner_user_id
    job.save_meta()
    return job.get_id()


def enqueue(func: Callable, *args, _job_id: str | None = None,
            _owner_user_id: int | None = None, **kwargs) -> str:
    """Enqueue a callable for background execution and return job_id

    Backends supported: inprocess, rq
    """
    backend = runtime_get("job_backend") or "inprocess"
    if backend == "inprocess":
        return _enqueue_inprocess(func, *args, job_id=_job_id,
                                  owner_user_id=_owner_user_id, **kwargs)
    elif backend == "rq":
        redis_url = runtime_get("redis_url")
        return _enqueue_rq(func, *args, redis_url=redis_url, job_id=_job_id,
                           owner_user_id=_owner_user_id, **kwargs)
    else:
        raise RuntimeError(f"Background backend '{backend}' not implemented")


def update_job(job_id: str, *, stage: str, progress: int, message: str | None = None) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job["stage"] = stage
    job["progress"] = max(0, min(100, int(progress)))
    if message is not None:
        job["message"] = message
    job["updated_at"] = datetime.utcnow().isoformat()


def update_current_job(*, stage: str, progress: int, message: str | None = None) -> None:
    job_id = getattr(_job_context, "job_id", None)
    if job_id:
        update_job(job_id, stage=stage, progress=progress, message=message)


def get_status(job_id: str, *, requester_user_id: int | None = None,
               requester_role: str | None = None) -> Dict:
    backend = runtime_get("job_backend") or "inprocess"
    if backend == "inprocess":
        job = _jobs.get(job_id)
        if job is None:
            return {"status": "not_found"}
        owner = job.get("owner_user_id")
        if requester_user_id is not None and requester_role != "admin" and owner != requester_user_id:
            return {"status": "not_found"}
        return job
    elif backend == "rq":
        if not _rq_available:
            return {"status": "error", "error": "rq/redis not available"}
        try:
            from redis import Redis
            from rq.job import Job
            redis_url = runtime_get("redis_url")
            conn = Redis.from_url(redis_url)
            job = Job.fetch(job_id, connection=conn)
            owner = job.meta.get("owner_user_id")
            if requester_user_id is not None and requester_role != "admin" and owner != requester_user_id:
                return {"status": "not_found"}
            return {"status": job.get_status(), "result": job.result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    else:
        return {"status": "not_supported"}


# Ensure worker is started when module imported and backend is inprocess
if runtime_get("job_backend") == "inprocess":
    start_worker()
