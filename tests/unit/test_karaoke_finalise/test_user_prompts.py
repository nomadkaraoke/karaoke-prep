import pytest
from unittest.mock import patch, MagicMock

# Adjust the import path
from karaoke_gen.karaoke_finalise.karaoke_finalise import KaraokeFinalise
from .test_initialization import mock_logger, basic_finaliser, MINIMAL_CONFIG # Reuse fixtures

PROMPT_MSG = "Do you want to proceed?"
EXIT_MSG = "User aborted."

# --- prompt_user_bool Tests ---

@pytest.mark.parametrize("user_input, allow_empty, expected_result", [
    ("y", True, True),
    ("Y", True, True),
    ("yes", True, True),
    ("YES", True, True),
    ("", True, True), # Empty allowed
    ("y", False, True),
    ("Y", False, True),
    ("yes", False, True),
    ("YES", False, True),
    ("", False, False), # Empty not allowed
    ("n", True, False),
    ("N", True, False),
    ("no", True, False),
    ("NO", True, False),
    ("n", False, False),
    ("N", False, False),
    ("no", False, False),
    ("NO", False, False),
    ("maybe", True, False),
    ("maybe", False, False),
])
@patch('builtins.input')
def test_prompt_user_bool_interactive(mock_input, user_input, allow_empty, expected_result, basic_finaliser):
    """Test various inputs for prompt_user_bool in interactive mode."""
    basic_finaliser.non_interactive = False # Ensure interactive
    mock_input.return_value = user_input
    result = basic_finaliser.prompt_user_bool(PROMPT_MSG, allow_empty=allow_empty)
    assert result == expected_result
    expected_options = "[y]/n" if allow_empty else "y/[n]"
    mock_input.assert_called_once_with(f"{PROMPT_MSG} {expected_options} ")

@patch('builtins.input')
def test_prompt_user_bool_non_interactive(mock_input, basic_finaliser):
    """Test prompt_user_bool always returns True in non-interactive mode."""
    basic_finaliser.non_interactive = True # Ensure non-interactive
    result_allow_empty = basic_finaliser.prompt_user_bool(PROMPT_MSG, allow_empty=True)
    result_not_allow_empty = basic_finaliser.prompt_user_bool(PROMPT_MSG, allow_empty=False)

    assert result_allow_empty is True
    assert result_not_allow_empty is True
    mock_input.assert_not_called() # Should not prompt
    basic_finaliser.logger.info.assert_any_call(f"Non-interactive mode, automatically answering yes to: {PROMPT_MSG}")

# --- prompt_user_confirmation_or_raise_exception Tests ---

@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True)
def test_prompt_confirmation_success(mock_prompt_bool, basic_finaliser):
    """Test confirmation succeeds when prompt_user_bool returns True."""
    basic_finaliser.non_interactive = False # Ensure interactive
    # No exception should be raised
    try:
        basic_finaliser.prompt_user_confirmation_or_raise_exception(PROMPT_MSG, EXIT_MSG, allow_empty=True)
    except Exception as e:
        pytest.fail(f"Should not have raised exception: {e}")
    mock_prompt_bool.assert_called_once_with(PROMPT_MSG, allow_empty=True)

@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=False)
def test_prompt_confirmation_failure_raises(mock_prompt_bool, basic_finaliser):
    """Test confirmation raises exception when prompt_user_bool returns False."""
    basic_finaliser.non_interactive = False # Ensure interactive
    with pytest.raises(Exception, match=EXIT_MSG):
        basic_finaliser.prompt_user_confirmation_or_raise_exception(PROMPT_MSG, EXIT_MSG, allow_empty=False)
    mock_prompt_bool.assert_called_once_with(PROMPT_MSG, allow_empty=False)
    basic_finaliser.logger.error.assert_called_once_with(EXIT_MSG)

@patch.object(KaraokeFinalise, 'prompt_user_bool')
def test_prompt_confirmation_non_interactive(mock_prompt_bool, basic_finaliser):
    """Test confirmation is bypassed in non-interactive mode."""
    basic_finaliser.non_interactive = True # Ensure non-interactive
    # No exception should be raised
    try:
        basic_finaliser.prompt_user_confirmation_or_raise_exception(PROMPT_MSG, EXIT_MSG)
    except Exception as e:
        pytest.fail(f"Should not have raised exception: {e}")

    mock_prompt_bool.assert_not_called() # Prompt should be skipped
    basic_finaliser.logger.info.assert_called_once_with(f"Non-interactive mode, automatically confirming: {PROMPT_MSG}")
