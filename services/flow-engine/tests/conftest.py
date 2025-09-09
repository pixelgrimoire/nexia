import sys
import types

# Provide a tiny fake redis module for unit tests that don't need a real redis server.
if 'redis' not in sys.modules:
    fake_redis = types.ModuleType('redis')
    class _FakeRedis:
        @staticmethod
        def from_url(*a, **k):
            return _FakeRedis()
    fake_redis.Redis = _FakeRedis
    sys.modules['redis'] = fake_redis
