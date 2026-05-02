from backend.app.infra.redis_client import get_redis

def main():
    r = get_redis()
    keys = r.keys('rq:job:*')
    print('rq job keys count:', len(keys))
    for k in keys:
        kstr = k.decode() if isinstance(k, bytes) else k
        print(kstr, 'type=', r.type(k))

if __name__ == '__main__':
    main()
