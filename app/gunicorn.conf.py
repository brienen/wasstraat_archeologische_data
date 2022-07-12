
import multiprocessing

# Gunicorn config variables
loglevel = "info"
errorlog = "-"  # stderr
accesslog = "-"  # stdout
worker_tmp_dir = "/dev/shm"
graceful_timeout = 120
timeout = 120
keepalive = 5
threads = 50
workers = (multiprocessing.cpu_count() * 2) + 1
preload_app=True
max_requests = 1000
max_requests_jitter = 100