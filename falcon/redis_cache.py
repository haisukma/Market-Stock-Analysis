import redis
import pickle
import os

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def redis_get(key):
    val = r.get(key)
    if val:
        return pickle.loads(val)
    return None

def redis_set(key, value, ttl=86400):
    r.set(key, pickle.dumps(value), ex=ttl)