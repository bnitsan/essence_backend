from retry import retry
from timeout_decorator import timeout, TimeoutError
from multiprocessing import Process, Manager

def run(func, args, kwargs, return_value, exception):
    try:
        return_value.value = func(*args, **kwargs)
    except TimeoutError:
        exception.value = True

def run_with_timeout(func, args, kwargs, timeout_seconds, return_value, exception):
    process = Process(target=run, args=(func, args, kwargs, return_value, exception))
    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError

    if exception.value:
        raise TimeoutError

    return return_value.value

def retry_on_timeout(retries=3, timeout_seconds=10):
    def decorator_retry_on_timeout(func):
        @retry(TimeoutError, tries=retries)
        def wrapper(*args, **kwargs):
            with Manager() as manager:
                return_value = manager.Value('i', None)
                exception = manager.Value('b', False)

                return run_with_timeout(func, args, kwargs, timeout_seconds, return_value, exception)

        return wrapper
    return decorator_retry_on_timeout