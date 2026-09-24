"""The entry script's only extra behaviour: keep a double-clicked .exe window open until Enter."""
import contextlib
import io
import sys
import unittest
from unittest import mock

import network_diag


class FakeStdin:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


@contextlib.contextmanager
def environment(frozen, argv, tty=True, main_result=0):
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(sys, "frozen", frozen, create=True))
        stack.enter_context(mock.patch.object(sys, "argv", argv))
        stack.enter_context(mock.patch.object(sys, "stdin", FakeStdin(tty)))
        main = stack.enter_context(mock.patch.object(network_diag, "main", return_value=main_result))
        prompt = stack.enter_context(mock.patch("builtins.input", return_value=""))
        yield main, prompt


class DoubleClickedExe(unittest.TestCase):
    def test_python_script_is_just_main(self):
        with environment(False, ["network_diag.py"], main_result=3) as (main, prompt):
            self.assertEqual(network_diag.run(), 3)
        prompt.assert_not_called()

    def test_frozen_exe_without_arguments_waits_for_enter(self):
        with environment(True, ["network_diag.exe"], main_result=0) as (main, prompt):
            self.assertEqual(network_diag.run(), 0)
        prompt.assert_called_once()

    def test_frozen_exe_with_arguments_behaves_like_a_normal_command(self):
        with environment(True, ["network_diag.exe", "--duration", "60"]) as (main, prompt):
            network_diag.run()
        prompt.assert_not_called()

    def test_frozen_exe_with_redirected_input_does_not_hang(self):
        with environment(True, ["network_diag.exe"], tty=False) as (main, prompt):
            network_diag.run()
        prompt.assert_not_called()

    def test_error_is_shown_before_the_window_would_close(self):
        with environment(True, ["network_diag.exe"]) as (main, prompt):
            main.side_effect = RuntimeError("boom")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = network_diag.run()
        self.assertEqual(code, 1)
        self.assertIn("RuntimeError: boom", err.getvalue())
        prompt.assert_called_once()

    def test_closed_input_at_the_prompt_is_harmless(self):
        with environment(True, ["network_diag.exe"], main_result=0) as (main, prompt):
            prompt.side_effect = EOFError
            self.assertEqual(network_diag.run(), 0)

    def test_importing_the_entry_script_does_not_start_the_program(self):
        self.assertTrue(callable(network_diag.run))  # imported above without running main()


if __name__ == "__main__":
    unittest.main()
