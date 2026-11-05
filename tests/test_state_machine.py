"""Unit tests for the Finite State Machine."""

from core.state_machine import AssistantState, StateMachine


def test_state_machine_transitions():
    sm = StateMachine(AssistantState.IDLE)
    assert sm.is_idle()

    # Track callback invocations
    history = []

    def callback(old, new):
        history.append((old, new))

    sm.add_listener(callback)

    assert sm.transition_to(AssistantState.WAKE_DETECTED)
    assert sm.current_state == AssistantState.WAKE_DETECTED

    # Same state transition should return False
    assert not sm.transition_to(AssistantState.WAKE_DETECTED)

    assert sm.transition_to(AssistantState.LISTENING)
    assert sm.is_listening()

    assert sm.transition_to(AssistantState.PROCESSING)
    assert sm.transition_to(AssistantState.SPEAKING)
    assert sm.is_speaking()

    assert len(history) == 4
    assert history[0] == (AssistantState.IDLE, AssistantState.WAKE_DETECTED)
