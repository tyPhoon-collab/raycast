import pathlib
import sys
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bash_to_nushell import ConversionError, convert  # noqa: E402


def multiline(value):
    return textwrap.dedent(value).strip()


class BashToNushellTest(unittest.TestCase):
    def test_line_continuations(self):
        bash_command = multiline(
            """\
            curl \\
              -H "Accept: application/json" \\
              https://example.com
            """
        )
        expected_nu_command = 'curl -H "Accept: application/json" https://example.com'

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_top_level_and_becomes_separate_commands(self):
        bash_command = "cd app && npm install && npm test"
        expected_nu_command = multiline(
            """
            cd app
            npm install
            npm test
            """
        )

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_quotes_are_not_converted(self):
        bash_command = 'echo "$FOO && >" && echo done'
        expected_nu_command = multiline(
            """
            echo "$FOO && >"
            echo done
            """
        )

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_export(self):
        bash_command = "export FOO=bar"
        expected_nu_command = '$env.FOO = "bar"'

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_unset(self):
        bash_command = "unset FOO"
        expected_nu_command = "hide-env FOO"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_env_references(self):
        bash_command = "echo $FOO ${BAR:-fallback} $?"
        expected_nu_command = (
            'echo $env.FOO ($env.BAR? | default "fallback") $env.LAST_EXIT_CODE'
        )

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_redirections(self):
        bash_command = "cmd > out.txt 2> err.txt"
        expected_nu_command = "cmd out> out.txt err> err.txt"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_dev_null_redirection(self):
        bash_command = "cmd > /dev/null 2>&1"
        expected_nu_command = "cmd out+err>| ignore"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_stderr_dev_null_redirection(self):
        bash_command = "cmd 2> /dev/null"
        expected_nu_command = "cmd err> /dev/null"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_stdout_and_stderr_to_same_file(self):
        bash_command = "cmd > output.log 2>&1"
        expected_nu_command = "cmd out+err> output.log"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_stdout_and_stderr_append_to_same_file(self):
        bash_command = "cmd >> output.log 2>&1"
        expected_nu_command = "cmd out+err>> output.log"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_stdout_and_stderr_pipe(self):
        bash_command = "command 2>&1 | less"
        expected_nu_command = "command out+err>| less"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_existing_nushell_env_reference_is_not_rewritten(self):
        bash_command = "echo $env.FOO"
        expected_nu_command = "echo $env.FOO"

        actual_nu_command = convert(bash_command)

        self.assertEqual(actual_nu_command, expected_nu_command)

    def test_unsupported_or_fails(self):
        bash_command = "cmd || echo failed"

        with self.assertRaisesRegex(ConversionError, r"Unsupported \|\|"):
            convert(bash_command)

    def test_unsupported_command_substitution_fails(self):
        bash_command = "echo $(pwd)"

        with self.assertRaisesRegex(ConversionError, "command substitution"):
            convert(bash_command)


if __name__ == "__main__":
    unittest.main()
