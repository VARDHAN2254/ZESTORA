from worker import celery, ping


def test_celery_app():
    assert celery.main == "zestora_worker"
    assert celery.conf.task_serializer == "json"


def test_ping_task():
    # Execute task directly in-process
    result = ping()
    assert result == "pong"
