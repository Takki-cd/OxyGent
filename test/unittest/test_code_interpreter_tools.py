"""Unit tests for the code interpreter tools."""

import pytest

from oxygent.preset_tools import code_interpreter_tools


@pytest.mark.asyncio
async def test_execute_code_simple():
    session_id = "test_session_1"
    result = await code_interpreter_tools.execute_code(session_id, "a = 10; print(a)")
    assert "10" in result
    await code_interpreter_tools.stop_session(session_id)


@pytest.mark.asyncio
async def test_execute_code_stateful():
    session_id = "test_session_2"
    await code_interpreter_tools.execute_code(session_id, "x = 20")
    result = await code_interpreter_tools.execute_code(session_id, "print(x * 2)")
    assert "40" in result
    await code_interpreter_tools.stop_session(session_id)


@pytest.mark.asyncio
async def test_execute_code_error():
    session_id = "test_session_3"
    # No warm-up: validate first-call error behavior without preheating
    result = await code_interpreter_tools.execute_code(
        session_id, "print(undefined_variable)"
    )
    assert "NameError" in result
    await code_interpreter_tools.stop_session(session_id)
