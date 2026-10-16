"""The session sweeper runs with the app and stops with it (SES-10)."""

import asyncio

from bundlemcp.api.jobs.session_sweep_job import TASK_NAME

from tests.conftest import serving


def _sweep_tasks() -> list[asyncio.Task]:
    return [task for task in asyncio.all_tasks() if task.get_name() == TASK_NAME]


async def test_ses10_app_shutdown_stops_the_sweeper(engine, redis):
    """SES-10: the sweep loop starts with the app and is cancelled cleanly at shutdown."""
    async with serving(engine, redis):
        [task] = _sweep_tasks()
        assert not task.done()
    await asyncio.sleep(0)
    assert task.done() and task.cancelled()
    assert _sweep_tasks() == []
