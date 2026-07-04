#!/usr/bin/env python3

import argparse
import json
import re
import sys


CONTROL_FLOW_PATTERN = re.compile(
    r"(^|\n)\s*(if|for|while|until|case|select|function)\b"
)
FUNCTION_DEFINITION_PATTERN = re.compile(r"\w+\s*\(\s*\)\s*\{")
EXPORT_PATTERN = re.compile(
    r"\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)\s*",
    flags=re.DOTALL,
)
UNSET_PATTERN = re.compile(r"\s*unset\s+([A-Za-z_][A-Za-z0-9_]*)\s*")
ENV_FALLBACK_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)[:-]-(.*?)\}")
ENV_BRACED_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
ENV_BARE_PATTERN = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


class ConversionError(Exception):
    pass


def quote_nu_string(value):
    return json.dumps(value)


def is_escaped(text, index):
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def normalize_line_continuations(text):
    logical_lines = []
    pending = ""

    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\") and not is_escaped(stripped, len(stripped) - 1):
            pending += stripped[:-1].strip() + " "
            continue

        logical_lines.append((pending + line.strip()).strip())
        pending = ""

    if pending:
        logical_lines.append(pending.strip())

    return "\n".join(line for line in logical_lines if line)


def scan_state(text):
    quote = None
    paren = bracket = brace = 0
    states = []

    for index, char in enumerate(text):
        states.append((quote, paren, bracket, brace))

        if quote:
            if char == quote and not is_escaped(text, index):
                quote = None
            continue

        if char in ("'", '"') and not is_escaped(text, index):
            quote = char
        elif char == "(":
            paren += 1
        elif char == ")":
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}":
            brace -= 1

        if min(paren, bracket, brace) < 0:
            raise ConversionError("Unsupported or unbalanced closing bracket")

    if quote:
        raise ConversionError("Unclosed quote")
    if paren or bracket or brace:
        raise ConversionError("Unbalanced brackets or braces")

    return states


def is_unquoted_top_level(states, index):
    quote, paren, bracket, brace = states[index]
    return quote is None and paren == 0 and bracket == 0 and brace == 0


def reject_unsupported(text):
    states = scan_state(text)
    stripped = text.strip()

    if CONTROL_FLOW_PATTERN.search(stripped):
        raise ConversionError("Unsupported Bash control flow")
    if FUNCTION_DEFINITION_PATTERN.search(stripped):
        raise ConversionError("Unsupported Bash function definition")

    for index, char in enumerate(text):
        if states[index][0] is not None:
            continue

        if text.startswith("<<", index):
            raise ConversionError("Unsupported heredoc")
        if text.startswith("$" + "(", index):
            raise ConversionError("Unsupported command substitution")
        if text.startswith("<(", index) or text.startswith(">(", index):
            raise ConversionError("Unsupported process substitution")
        if char == chr(96):
            raise ConversionError("Unsupported legacy command substitution")

        if is_unquoted_top_level(states, index):
            if text.startswith("||", index):
                raise ConversionError("Unsupported ||; rewrite manually for Nushell")
            if text.startswith("|&", index):
                raise ConversionError("Unsupported |&")
            if char == "&":
                previous_char = text[index - 1] if index else ""
                next_char = text[index + 1] if index + 1 < len(text) else ""
                if previous_char in (">", "&") or next_char == "&":
                    continue
                raise ConversionError("Unsupported background command or bare &")


def convert_top_level_and(text):
    states = scan_state(text)
    output = []
    index = 0

    while index < len(text):
        if text.startswith("&&", index) and is_unquoted_top_level(states, index):
            output.append(";")
            index += 2
            continue

        output.append(text[index])
        index += 1

    return "".join(output)


def read_shell_word(text, index):
    start = index
    quote = None

    while index < len(text):
        char = text[index]
        if quote:
            if char == quote and not is_escaped(text, index):
                quote = None
            index += 1
            continue

        if char in ("'", '"') and not is_escaped(text, index):
            quote = char
            index += 1
            continue
        if char.isspace() or char in ";&|":
            break
        index += 1

    return text[start:index], index


def convert_redirections(command):
    states = scan_state(command)
    output = []
    index = 0

    while index < len(command):
        if not is_unquoted_top_level(states, index):
            output.append(command[index])
            index += 1
            continue

        if command.startswith("2>&1", index):
            after_redirect = index + len("2>&1")
            while after_redirect < len(command) and command[after_redirect].isspace():
                after_redirect += 1

            if after_redirect < len(command) and command[after_redirect] == "|":
                output.append("out+err>|")
                index = after_redirect + 1
                continue

            raise ConversionError("Unsupported standalone 2>&1")

        op = None
        replacement = None
        if command.startswith("2>>", index):
            op = "2>>"
            replacement = "err>>"
        elif command.startswith("2>", index):
            op = "2>"
            replacement = "err>"
        elif command.startswith(">>", index):
            op = ">>"
            replacement = "out>>"
        elif command[index] == ">" and not command.startswith(">=", index):
            op = ">"
            replacement = "out>"

        if not op:
            output.append(command[index])
            index += 1
            continue

        target_start = index + len(op)
        while target_start < len(command) and command[target_start].isspace():
            target_start += 1

        if target_start >= len(command):
            raise ConversionError(f"Missing redirection target after {op}")

        target, target_end = read_shell_word(command, target_start)
        if not target:
            raise ConversionError(f"Missing redirection target after {op}")

        if target == "/dev/null":
            after_target = target_end
            while after_target < len(command) and command[after_target].isspace():
                after_target += 1
            if op in (">", ">>") and command.startswith("2>&1", after_target):
                output.append("out+err>| ignore")
                index = after_target + len("2>&1")
            else:
                output.append("| ignore" if op in (">", ">>") else f"{replacement} /dev/null")
                index = target_end
            continue

        after_target = target_end
        while after_target < len(command) and command[after_target].isspace():
            after_target += 1
        if op in (">", ">>") and command.startswith("2>&1", after_target):
            combined = "out+err>>" if op == ">>" else "out+err>"
            output.append(f"{combined} {target}")
            index = after_target + len("2>&1")
            continue

        output.append(f"{replacement} {target}")
        index = target_end

    return "".join(output)


def convert_env_references(text):
    output = []
    index = 0
    quote = None

    while index < len(text):
        char = text[index]

        if quote:
            output.append(char)
            if char == quote and not is_escaped(text, index):
                quote = None
            index += 1
            continue

        if char in ("'", '"') and not is_escaped(text, index):
            quote = char
            output.append(char)
            index += 1
            continue

        if char == "$" and not is_escaped(text, index):
            if text.startswith("$env.", index):
                output.append("$env.")
                index += len("$env.")
                continue

            if text.startswith("$?", index):
                output.append("$env.LAST_EXIT_CODE")
                index += 2
                continue

            fallback = ENV_FALLBACK_PATTERN.match(text[index:])
            if fallback:
                name, value = fallback.groups()
                value = value.strip()
                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ("'", '"')
                ):
                    value = value[1:-1]
                output.append(f"($env.{name}? | default {quote_nu_string(value)})")
                index += fallback.end()
                continue

            braced = ENV_BRACED_PATTERN.match(text[index:])
            if braced:
                output.append(f"$env.{braced.group(1)}")
                index += braced.end()
                continue

            bare = ENV_BARE_PATTERN.match(text[index:])
            if bare:
                output.append(f"$env.{bare.group(1)}")
                index += bare.end()
                continue

        output.append(char)
        index += 1

    return "".join(output)


def convert_env_assignment_value(value):
    value = convert_env_references(value.strip())
    if not value:
        return quote_nu_string("")
    if value.startswith(('"', "'", "$env.", "(", "[")):
        return value
    return quote_nu_string(value)


def convert_export_or_unset(command):
    export_match = EXPORT_PATTERN.fullmatch(command)
    if export_match:
        name, value = export_match.groups()
        return f"$env.{name} = {convert_env_assignment_value(value)}"

    unset_match = UNSET_PATTERN.fullmatch(command)
    if unset_match:
        return f"hide-env {unset_match.group(1)}"

    return command


def split_commands(text):
    states = scan_state(text)
    commands = []
    start = 0

    for index, char in enumerate(text):
        if char in (";", "\n") and is_unquoted_top_level(states, index):
            command = text[start:index].strip()
            if command:
                commands.append(command)
            start = index + 1

    tail = text[start:].strip()
    if tail:
        commands.append(tail)

    return commands


def convert_simple_command(command):
    command = convert_export_or_unset(command)
    command = convert_redirections(command)
    command = convert_env_references(command)
    return command.strip()


def convert(text):
    bash_command = normalize_line_continuations(text)
    reject_unsupported(bash_command)

    nu_like_command = convert_top_level_and(bash_command)
    commands = split_commands(nu_like_command)
    if not commands:
        raise ConversionError("No command found")

    return "\n".join(convert_simple_command(command) for command in commands)


def main():
    parser = argparse.ArgumentParser(
        description="Convert simple Bash commands to Nushell syntax."
    )
    parser.add_argument("input", nargs="?", help="Bash command to convert")
    args = parser.parse_args()

    input_text = args.input if args.input is not None else sys.stdin.read()

    try:
        print(convert(input_text))
    except ConversionError as error:
        print(f"Cannot convert: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
