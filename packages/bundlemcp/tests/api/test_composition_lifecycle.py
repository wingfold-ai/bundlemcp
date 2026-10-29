"""The background jobs the composition root starts run with the app and stop with it."""

import asyncio

from bundlemcp.api.jobs import audit_purger, invocation_sweep_job, session_sweep_job

from tests.conftest import serving

JOB_TASKS = {
    invocation_sweep_job.TASK_NAME,
    session_sweep_job.TASK_NAME,
    audit_purger.TASK_NAME,
}


def _job_tasks() -> list[asyncio.Task]:
    return [task for task in asyncio.all_tasks() if task.get_name() in JOB_TASKS]


async def test_ses10_ops5_background_jobs_run_while_serving_and_stop_with_the_app(engine, redis):
    """SES-10, OPS-5: each sweep and purge job runs while the app serves and is gone after."""
    async with serving(engine, redis):
        running = _job_tasks()
        assert sorted(task.get_name() for task in running) == sorted(JOB_TASKS)
        assert not any(task.done() for task in running)
    await asyncio.sleep(0)
    assert all(task.done() for task in running)
    assert _job_tasks() == []
