__all__ = ['_trap_sleep']


from types import coroutine


@coroutine
def _sleep(seconds):
    yield ('_trap_sleep', seconds)

