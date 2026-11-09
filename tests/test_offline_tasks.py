"""Unit tests for Sarathi's autonomous offline task execution and fallback engine."""

import pytest
from llm.client import LLMClient
from llm.memory import ConversationMemory


def test_offline_task_system_diagnostics():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("What is my CPU and battery status?")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "Diagnostics report" in response or "CPU" in response
    assert "Parth" in response


def test_offline_task_volume_control():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("Set volume to 45 percent")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "volume set to 45 percent" in response.lower()
    assert "Parth" in response


def test_offline_task_volume_mute():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("Mute the sound")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "muted" in response.lower()


def test_offline_task_time_and_date():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("What time is it right now?")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "current time is" in response
    assert "Parth" in response


def test_offline_task_capabilities():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("Who are you and what can you do offline?")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "Sarathi" in response
    assert "offline" in response.lower()


def test_offline_task_general_fallback():
    client = LLMClient()
    memory = ConversationMemory()
    memory.add_user_message("Write me a poem about Mars")

    generator = client._offline_fallback_generator(memory)
    tokens = list(generator)
    response = "".join(tokens)

    assert "offline" in response.lower()
    assert "Parth" in response


def test_is_network_error_detection():
    import socket
    import httpx

    sock_err = socket.gaierror(11001, "getaddrinfo failed")
    assert LLMClient._is_network_error(sock_err) is True

    conn_err = httpx.ConnectError("Failed to establish a new connection")
    assert LLMClient._is_network_error(conn_err) is True

    generic_err = ValueError("Invalid argument")
    assert LLMClient._is_network_error(generic_err) is False
