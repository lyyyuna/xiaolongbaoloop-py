__all__ = [
    'instantiate_coroutine'
]


import inspect, functools, threading
import collections.abc
from contextlib import contextmanager


_locals = threading.local()


@contextmanager
def running(kernel):
    if getattr(_locals, 'running', False):
        raise RuntimeError('only one xiaolongbaoloop kernel per thread is allowed')
    _locals.running = True
    _locals.kernel = kernel
    try:
        yield
    finally:
        _locals.running = False
        _locals.kernel = None


def iscoroutinefunction(func):
    if isinstance(func, functools.partial):
        return iscoroutinefunction(func.func)
    if hasattr(func, '__func__'):
        return iscoroutinefunction(func.__func__)
    return inspect.iscoroutinefunction(func) or hasattr(func, '_awaitable') or inspect.isasyncgenfunction(func)


def instantiate_coroutine(corofunc, *args, **kwargs):
    # 已经是 coroutine 了
    if isinstance(corofunc, collections.abc.Coroutine) or inspect.isgenerator(corofunc):
        assert not args and not kwargs, 'arguments cannot be passed to an already instantiated coroutine'
        return corofunc
        
    if not iscoroutinefunction(corofunc) and not getattr(corofunc, '_async_thread', False):
        coro = corofunc(*args, **kwargs)
        if not isinstance(coro, collections.abc.Coroutine):
            raise TypeError(f'could not create coroutine from {corofunc}')
        return coro

    async def context():
        return corofunc(*args, **kwargs)

    try:
        context().send(None)
    except StopIteration as e:
        return e.value

