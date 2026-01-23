---
name: review-py-tests
description: Review pytest test files for best practices including test strategy, configuration, coverage, mocking, fixtures, parametrization, and debugging. Use when user says "review tests", "review pytest", or asks to analyze test files.
---

# Pytest Best Practices and Code Examples

A comprehensive guide extracted from pytest documentation covering test strategy, configuration, coverage, mocking, CI/CD, debugging, plugins, and advanced parametrization.

---

## Table of Contents

1. [Test Strategy Best Practices](#test-strategy-best-practices)
2. [Configuration Files](#configuration-files)
3. [Coverage](#coverage)
4. [Mocking](#mocking)
5. [tox and CI](#tox-and-ci)
6. [Testing Scripts and Applications](#testing-scripts-and-applications)
7. [Debugging Test Failures](#debugging-test-failures)
8. [Third-Party Plugins](#third-party-plugins)
9. [Building Plugins](#building-plugins)
10. [Advanced Parametrization](#advanced-parametrization)
11. [Key Best Practices Summary](#key-best-practices-summary)

---

## Test Strategy Best Practices

### Feature Prioritization Criteria

When deciding which features to test first, prioritize based on:

- **Recent** — New features, recently modified code
- **Core** — Essential functions (USPs) that must work
- **Risk** — Areas with third-party code or limited team familiarity
- **Problematic** — Functionality that frequently breaks
- **Expertise** — Features understood by limited people

### Test Case Generation Criteria

For each feature, generate test cases using these criteria:

- Start with a non-trivial "happy path" test case
- Look at interesting sets of input
- Look at interesting starting states
- Look at interesting end states
- Cover all possible error states

### Testing Strategy Template

```
• Test the behaviors and features accessible through the end user interface
• Test those features through the API as much as possible
• Test the CLI enough to verify the API is getting properly called
• Test core features thoroughly: add, count, delete, finish, list, start, update
• Include cursory tests for config and version
• Test third-party dependencies with subsystem tests
```

---

## Configuration Files

### pytest.ini Example

```ini
[pytest]
addopts = --strict-markers --strict-config -ra
testpaths = tests
markers =
    smoke: subset of tests
    exception: check for expected exceptions
```

### pyproject.toml Example

```toml
[tool.pytest.ini_options]
addopts = [
    "--strict-markers",
    "--strict-config",
    "-ra"
]
testpaths = "tests"
markers = [
    "smoke: subset of tests",
    "exception: check for expected exceptions"
]
```

### tox.ini with pytest section

```ini
[tox]
; tox specific settings

[pytest]
addopts = --strict-markers --strict-config -ra
testpaths = tests
markers =
    smoke: subset of tests
    exception: check for expected exceptions
```

### setup.cfg Example

```ini
[tool:pytest]
addopts = --strict-markers --strict-config -ra
testpaths = tests
markers =
    smoke: subset of tests
    exception: check for expected exceptions
```

### Key Configuration Settings Explained

| Setting | Purpose |
|---------|---------|
| `--strict-markers` | Raise error for unregistered markers (catches typos) |
| `--strict-config` | Raise error for config file parsing issues |
| `-ra` | Show extra test summary for all except passing tests |
| `testpaths` | Where to look for tests (saves startup time) |

### conftest.py Purpose

- Store fixtures and hook functions
- Can have multiple conftest.py files (one per subdirectory)
- Fixtures defined in conftest.py apply to tests in that directory and below

### Avoiding Test File Name Collision with __init__.py

```
tests/
├── api/
│   ├── __init__.py      # Allows duplicate names
│   └── test_add.py
└── cli/
    ├── __init__.py      # Allows duplicate names
    └── test_add.py      # Same name, no conflict
```

---

## Coverage

### Running coverage with pytest-cov

```bash
# Simple report
pytest --cov=cards ch7

# Show missing lines in terminal
pytest --cov=cards --cov-report=term-missing ch7

# Generate HTML report
pytest --cov=cards --cov-report=html ch7
```

### Running coverage directly (without pytest-cov)

```bash
# Run tests with coverage
coverage run --source=cards -m pytest ch7

# Show simple report
coverage report

# Show missing lines
coverage report --show-missing

# Generate HTML report
coverage html
```

### Coverage configuration (.coveragerc)

```ini
[paths]
source =
    src
    .tox/*/site-packages
```

For local development with cards_proj:

```ini
[paths]
source =
    cards_proj/src/cards
    */site-packages/cards
```

### Excluding code from coverage

```python
if __name__ == '__main__':  # pragma: no cover
    main()
```

### Including test code in coverage

This catches duplicate test names:

```bash
pytest --cov=cards --cov=ch7 ch7
```

### Running coverage on a directory (not installed package)

```bash
pytest --cov=ch9/some_code ch9/some_code/test_some_code.py

# Or from within the directory
cd ch9
pytest --cov=some_code some_code
```

### Running coverage on a single file

```python
# single_file.py
def foo():
    return "foo"

def main():
    print(foo())

if __name__ == "__main__":  # pragma: no cover
    main()

# Test code in same file
def test_foo():
    assert foo() == "foo"

def test_main(capsys):
    main()
    captured = capsys.readouterr()
    assert captured.out == "foo baz\n"
```

```bash
# Run coverage on single file (no .py extension for --cov)
pytest --cov=single_file single_file.py
```

### Adding imports only for testing in scripts

```python
if __name__ == '__main__':  # pragma: no cover
    main()
else:
    import pytest  # Available when running tests
```

---

## Mocking

### Testing with Typer's CliRunner

```python
from typer.testing import CliRunner
from cards.cli import app

runner = CliRunner()

def test_typer_runner():
    result = runner.invoke(app, ["version"])
    print(f"version: {result.stdout}")

    result = runner.invoke(app, ["list", "-o", "brian"])
    print(f"list:\n{result.stdout}")
```

### Helper function for CLI testing

```python
import shlex

def cards_cli(command_string):
    command_list = shlex.split(command_string)
    result = runner.invoke(app, command_list)
    output = result.stdout.rstrip()
    return output

def test_cards_cli():
    result = cards_cli("version")
    result = cards_cli("list -o brian")
```

### Mocking an attribute

```python
from unittest import mock
import cards

def test_mock_version():
    with mock.patch.object(cards, "__version__", "1.2.3"):
        result = runner.invoke(app, ["version"])
        assert result.stdout.rstrip() == "1.2.3"
```

### Mocking a class - exploring the mock object

```python
def test_mock_CardsDB():
    with mock.patch.object(cards, "CardsDB") as MockCardsDB:
        print(f"      class: {MockCardsDB}")
        print(f"return_value: {MockCardsDB.return_value}")
        with cards.cli.cards_db() as db:
            print(f"     object: {db}")
```

Output:
```
      class: <MagicMock name='CardsDB' id='...'>
return_value: <MagicMock name='CardsDB()' id='...'>
     object: <MagicMock name='CardsDB()' id='...'>
```

### Mocking a class method's return value

```python
def test_mock_path():
    with mock.patch.object(cards, "CardsDB") as MockCardsDB:
        MockCardsDB.return_value.path.return_value = "/foo/"
        with cards.cli.cards_db() as db:
            print(f"{db.path=}")      # The mock object
            print(f"{db.path()=}")    # '/foo/'
```

### Mock fixture with autospec

```python
@pytest.fixture()
def mock_cardsdb():
    with mock.patch.object(cards, "CardsDB", autospec=True) as CardsDB:
        yield CardsDB.return_value

def test_config(mock_cardsdb):
    mock_cardsdb.path.return_value = "/foo/"
    result = runner.invoke(app, ["config"])
    assert result.stdout.rstrip() == "/foo/"
```

### Making sure functions are called correctly

```python
def test_add_with_owner(mock_cardsdb):
    cards_cli("add some task -o brian")
    expected = cards.Card("some task", owner="brian", state="todo")
    mock_cardsdb.add_card.assert_called_with(expected)
```

### Creating error conditions with side_effect

```python
def test_delete_invalid(mock_cardsdb):
    mock_cardsdb.delete_card.side_effect = cards.api.InvalidCardId
    out = cards_cli("delete 25")
    assert "Error: Invalid card id 25" in out
```

### Why autospec=True matters

```python
# BAD - accepts any method/params (hides bugs)
def test_bad_mock():
    with mock.patch.object(cards, "CardsDB") as CardsDB:
        db = CardsDB("/some/path")
        db.path()          # good
        db.path(35)        # invalid arguments - NO ERROR!
        db.not_valid()     # invalid function - NO ERROR!

# GOOD - validates against real interface
def test_good_mock():
    with mock.patch.object(cards, "CardsDB", autospec=True) as CardsDB:
        db = CardsDB("/some/path")
        db.path(35)        # TypeError: too many positional arguments
        db.not_valid()     # AttributeError: Mock object has no attribute
```

### Testing at multiple layers to avoid mocking

```python
# With mocking (tests implementation)
def test_add_with_owner(mock_cardsdb):
    cards_cli("add some task -o brian")
    expected = cards.Card("some task", owner="brian", state="todo")
    mock_cardsdb.add_card.assert_called_with(expected)

# Without mocking (tests behavior) - PREFERRED
def test_add_with_owner(cards_db):
    """A card shows up in the list with expected contents."""
    cards_cli("add some task -o brian")
    expected = cards.Card("some task", owner="brian", state="todo")
    all_cards = cards_db.list_cards()
    assert len(all_cards) == 1
    assert all_cards[0] == expected
```

---

## tox and CI

### Basic tox.ini

```ini
[tox]
envlist = py310
isolated_build = True

[testenv]
deps =
    pytest
    faker
commands = pytest
```

### Multiple Python versions

```ini
[tox]
envlist = py37, py38, py39, py310
isolated_build = True
skip_missing_interpreters = True
```

### Running tox

```bash
# Run all environments
tox

# Run specific environment
tox -e py310

# Run environments in parallel
tox -p

# Use alternate config file
tox -c tox_multiple_pythons.ini
```

### With coverage report

```ini
[testenv]
deps =
    pytest
    faker
    pytest-cov
commands = pytest --cov=cards
```

### With minimum coverage threshold

```ini
[testenv]
deps =
    pytest
    faker
    pytest-cov
commands = pytest --cov=cards --cov=tests --cov-fail-under=100
```

### Passing pytest parameters through tox

```ini
[testenv]
deps =
    pytest
    faker
    pytest-cov
commands = pytest --cov=cards --cov=tests --cov-fail-under=100 {posargs}
```

```bash
# Pass arguments after --
tox -e py310 -- -k test_version --no-cov
tox -e py310 -- -v
tox -e py310 -- --pdb --no-cov
```

### GitHub Actions workflow

Create `.github/workflows/main.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.7", "3.8", "3.9", "3.10"]

    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python }}

      - name: Install Tox and any other packages
        run: pip install tox

      - name: Run Tox
        run: tox -e py
```

---

## Testing Scripts and Applications

### Testing a simple script with subprocess

```python
from subprocess import run

def test_hello():
    result = run(["python", "hello.py"], capture_output=True, text=True)
    output = result.stdout
    assert output == "Hello, World!\n"
```

### tox.ini for scripts (no package to build)

```ini
[tox]
envlist = py39, py310
skipsdist = true

[testenv]
deps = pytest
commands = pytest
```

### Making a script importable

```python
# hello.py
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
```

### Testing importable script with capsys

```python
import hello

def test_main(capsys):
    hello.main()
    output = capsys.readouterr().out
    assert output == "Hello, World!\n"
```

### Breaking up script into testable functions

```python
# hello.py
def full_output():
    return "Hello, World!"

def main():
    print(full_output())

if __name__ == "__main__":
    main()
```

```python
# test_hello.py
import hello

def test_full_output():
    assert hello.full_output() == "Hello, World!"

def test_main(capsys):
    hello.main()
    output = capsys.readouterr().out
    assert output == "Hello, World!\n"
```

### Separating code into src and tests directories

```
project/
├── src/
│   └── hello.py
├── tests/
│   └── test_hello.py
└── pytest.ini
```

### pytest.ini with pythonpath

```ini
[pytest]
addopts = -ra
testpaths = tests
pythonpath = src
```

### Understanding sys.path during tests

```python
import sys

def test_sys_path():
    print("sys.path: ")
    for p in sys.path:
        print(p)
```

Output shows:
- `/path/to/project/tests` (added by pytest)
- `/path/to/project/src` (added by pythonpath setting)
- `.../site-packages` (pip installed packages)

### Testing with requirements.txt dependencies

**requirements.txt:**
```
typer==0.3.2
```

**Script using Typer:**
```python
# hello.py
import typer
from typing import Optional

def full_output(name: str):
    return f"Hello, {name}!"

app = typer.Typer()

@app.command()
def main(name: Optional[str] = typer.Argument("World")):
    print(full_output(name))

if __name__ == "__main__":
    app()
```

**Tests using Typer's CliRunner:**
```python
import hello
from typer.testing import CliRunner

def test_full_output():
    assert hello.full_output("Foo") == "Hello, Foo!"

runner = CliRunner()

def test_hello_app_no_name():
    result = runner.invoke(hello.app)
    assert result.stdout == "Hello, World!\n"

def test_hello_app_with_name():
    result = runner.invoke(hello.app, ["Brian"])
    assert result.stdout == "Hello, Brian!\n"
```

### tox.ini with requirements.txt

```ini
[tox]
envlist = py39, py310
skipsdist = true

[testenv]
deps =
    pytest
    -rrequirements.txt
commands = pytest

[pytest]
addopts = -ra
testpaths = tests
pythonpath = src
```

---

## Debugging Test Failures

### Installing package in editable mode

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -U pip

# Install package in editable mode with test dependencies
pip install -e "./cards_proj/[test]"
```

### pyproject.toml with optional test dependencies

```toml
[project.optional-dependencies]
test = [
    "pytest",
    "faker",
    "tox",
    "coverage",
    "pytest-cov",
]
```

### Useful pytest debugging flags

**Test selection flags:**

| Flag | Purpose |
|------|---------|
| `--lf` | Run only last failed tests |
| `--ff` | Run all tests, failed first |
| `-x` | Stop after first failure |
| `--maxfail=2` | Stop after 2 failures |
| `-nf` | Run all tests, newest files first |
| `--sw` | Stepwise: stop at failure, resume from there |
| `--sw-skip` | Stepwise but skip first failure |

**Output control flags:**

| Flag | Purpose |
|------|---------|
| `-v` | Verbose: show all test names |
| `--tb=short` | Shorter traceback |
| `--tb=no` | No traceback |
| `--tb=long` | Full traceback |
| `--tb=line` | One line per failure |
| `-l` | Show local variables in traceback |

**Debugger flags:**

| Flag | Purpose |
|------|---------|
| `--pdb` | Start pdb at failure point |
| `--trace` | Start pdb at beginning of each test |
| `--pdbcls=IPython.terminal.debugger:TerminalPdb` | Use IPython debugger |

### Combining flags for debugging workflow

```bash
# Re-run failed tests with no traceback
pytest --lf --tb=no

# Re-run first failed test, stop, show locals
pytest --lf -x -l --tb=short

# Re-run failed tests, start debugger at beginning
pytest --lf --trace

# Re-run failed tests, start debugger at failure
pytest --lf --pdb
```

### Common pdb commands

```
# Help
h(elp)              - List all commands
h(elp) command      - Help on specific command
q(uit)              - Exit debugger

# Navigation / Location
l(ist)              - List 11 lines around current line
l(ist) .            - Same, but reset to current position
l(ist) first,last   - List specific line range
ll                  - List entire current function
w(here)             - Print stack trace

# Inspection
p(rint) expr        - Evaluate and print expression
pp expr             - Pretty print (good for data structures)
a(rgs)              - Print arguments of current function

# Execution
s(tep)              - Step into function
n(ext)              - Step over (stay in current function)
r(eturn)            - Continue until function returns
c(ontinue)          - Continue to next breakpoint
unt(il) lineno      - Continue until specific line number
```

### Debugging session example

```python
# Start debugger at test
$ pytest --lf --trace

(Pdb) ll                           # See the whole function
(Pdb) until 8                      # Run until line 8
(Pdb) step                         # Step into function call
(Pdb) ll                           # See where we are
(Pdb) return                       # Run until function returns
(Pdb) pp done_cards                # Inspect variable
(Pdb) step                         # Step back to calling code
(Pdb) pp the_list                  # Inspect return value
(Pdb) exit                         # Exit debugger
```

### Using pdb with tox

```bash
# Start debugger at failure within tox environment
tox -e py310 -- --pdb --no-cov

# Re-run failed tests with debugger at start
tox -e py310 -- --lf --trace --no-cov

# Re-run just one test with verbose output
tox -e py310 -- --lf --tb=no --no-cov -v
```

### Using breakpoint() in code

```python
def some_function():
    x = calculate_something()
    breakpoint()  # Debugger will stop here
    return x
```

```bash
# Run pytest - will stop at breakpoint() automatically
pytest
```

### Using IPython debugger

```bash
pip install ipython

# With --pdb flag
pytest --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb

# With --trace flag
pytest --lf --trace --pdbcls=IPython.terminal.debugger:TerminalPdb

# With breakpoint() in code
pytest --pdbcls=IPython.terminal.debugger:TerminalPdb
```

---

## Third-Party Plugins

### Useful Plugins by Category

**Test run flow:**
| Plugin | Purpose |
|--------|---------|
| `pytest-order` | Specify test order with markers |
| `pytest-randomly` | Randomize test order |
| `pytest-repeat` | Repeat tests multiple times |
| `pytest-rerunfailures` | Re-run flaky tests |
| `pytest-xdist` | Run tests in parallel |

**Output enhancement:**
| Plugin | Purpose |
|--------|---------|
| `pytest-instafail` | Show failures immediately |
| `pytest-sugar` | Progress bar, green checkmarks |
| `pytest-html` | Generate HTML reports |

**Web development:**
| Plugin | Purpose |
|--------|---------|
| `pytest-selenium` | Browser-based testing |
| `pytest-splinter` | Higher-level browser testing |
| `pytest-django` | Django testing |
| `pytest-flask` | Flask testing |

**Fake data:**
| Plugin | Purpose |
|--------|---------|
| `Faker` | Generate fake data |
| `model-bakery` | Django model fake data |
| `pytest-factoryboy` | Factory Boy fixtures |
| `pytest-mimesis` | Fast fake data |

**Extended functionality:**
| Plugin | Purpose |
|--------|---------|
| `pytest-cov` | Coverage reporting |
| `pytest-benchmark` | Timing benchmarks |
| `pytest-timeout` | Prevent long-running tests |
| `pytest-asyncio` | Test async functions |
| `pytest-bdd` | Behavior-driven development |
| `pytest-freezegun` | Freeze time |
| `pytest-mock` | Wrapper around unittest.mock |

### Running tests in parallel with pytest-xdist

```bash
pip install pytest-xdist

# Run on 4 CPUs
pytest --count=10 -n=4 test_parallel.py

# Run on all available CPUs (usually best)
pytest -n=auto test_parallel.py

# Watch files and re-run failures
pytest --looponfail
```

### Randomizing test order with pytest-randomly

```bash
pip install pytest-randomly

# Tests now run in random order automatically
pytest -v
```

### Repeating tests with pytest-repeat

```bash
pip install pytest-repeat

# Run each test 10 times
pytest --count=10 test_file.py

# Combine with parallel execution
pytest --count=10 -n=auto test_file.py
```

---

## Building Plugins

### Hook functions overview

```python
# pytest_configure - Initial configuration
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow")

# pytest_addoption - Register command-line options
def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="include slow tests")

# pytest_collection_modifyitems - Modify collected tests
def pytest_collection_modifyitems(config, items):
    # items is list of test Node objects
    pass
```

### Complete local conftest plugin example

```python
# conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")

def pytest_addoption(parser):
    parser.addoption(
        "--slow", action="store_true", help="include tests marked slow"
    )

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="need --slow option to run")
        for item in items:
            if item.get_closest_marker("slow"):
                item.add_marker(skip_slow)
```

### Usage of the slow marker plugin

```python
# test_slow.py
import pytest

def test_normal():
    pass

@pytest.mark.slow
def test_slow():
    pass
```

```bash
# Skip slow tests (default)
pytest -v
# test_normal PASSED
# test_slow SKIPPED (need --slow option to run)

# Include slow tests
pytest -v --slow
# test_normal PASSED
# test_slow PASSED

# Run only slow tests
pytest -v -m slow --slow
# test_slow PASSED
```

### Plugin directory structure

```
pytest_skip_slow/
├── examples/
│   └── test_slow.py
├── tests/
│   ├── conftest.py
│   └── test_plugin.py
├── pytest_skip_slow.py
├── pyproject.toml
├── README.md
├── LICENSE
└── tox.ini
```

### Plugin module with docstring and version

```python
# pytest_skip_slow.py
"""
A pytest plugin to skip `@pytest.mark.slow` tests by default.
Include the slow tests with `--slow`.
"""
import pytest

__version__ = "0.0.1"

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")

def pytest_addoption(parser):
    parser.addoption(
        "--slow", action="store_true", help="include tests marked slow"
    )

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="need --slow option to run")
        for item in items:
            if item.get_closest_marker("slow"):
                item.add_marker(skip_slow)
```

### pyproject.toml for pytest plugin

```toml
[build-system]
requires = ["flit_core >=3.2,<4"]
build-backend = "flit_core.buildapi"

[project]
name = "pytest-skip-slow"
authors = [{name = "Your Name", email = "your.name@example.com"}]
readme = "README.md"
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Framework :: Pytest"
]
dynamic = ["version", "description"]
dependencies = ["pytest>=6.2.0"]
requires-python = ">=3.7"

[project.urls]
Home = "https://github.com/okken/pytest-skip-slow"

[project.entry-points.pytest11]
skip_slow = "pytest_skip_slow"

[project.optional-dependencies]
test = ["tox"]

[tool.flit.module]
name = "pytest_skip_slow"
```

**Key points:**
- `name` uses dashes: `pytest-skip-slow`
- Module name uses underscores: `pytest_skip_slow`
- Entry point section: `[project.entry-points.pytest11]`
- Classifier: `"Framework :: Pytest"`

### Building and installing the plugin

```bash
# Install flit
pip install flit

# Initialize (creates pyproject.toml template)
flit init

# Build the package
flit build
# Creates: dist/pytest-skip-slow-0.0.1-py3-none-any.whl
#          dist/pytest-skip-slow-0.0.1.tar.gz

# Install the wheel to test
pip install dist/pytest_skip_slow-0.0.1-py3-none-any.whl

# Or install in editable mode for development
pip install -e .
```

### Testing plugins with pytester

**Enable pytester in conftest.py:**
```python
# tests/conftest.py
pytest_plugins = ["pytester"]
```

**Test file:**
```python
# tests/test_plugin.py
import pytest

@pytest.fixture()
def examples(pytester):
    pytester.copy_example("examples/test_slow.py")

def test_skip_slow(pytester, examples):
    result = pytester.runpytest("-v")
    result.stdout.fnmatch_lines([
        "*test_normal PASSED*",
        "*test_slow SKIPPED (need --slow option to run)*",
    ])
    result.assert_outcomes(passed=1, skipped=1)

def test_run_slow(pytester, examples):
    result = pytester.runpytest("--slow")
    result.assert_outcomes(passed=2)

def test_run_only_slow(pytester, examples):
    result = pytester.runpytest("-v", "-m", "slow", "--slow")
    result.stdout.fnmatch_lines(["*test_slow PASSED*"])
    outcomes = result.parseoutcomes()
    assert outcomes["passed"] == 1
    assert outcomes["deselected"] == 1

def test_help(pytester):
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(
        ["*--slow * include tests marked slow*"]
    )
```

### pytester methods

```python
# Create files
pytester.makefile()           # Any file type
pytester.makepyfile()         # Python file
pytester.makeconftest()       # conftest.py
pytester.makeini()            # tox.ini
pytester.makepyprojecttoml()  # pyproject.toml
pytester.maketxtfile()        # Text file
pytester.mkdir()              # Directory
pytester.mkpydir()            # Directory with __init__.py
pytester.copy_example()       # Copy from project directory

# Run pytest
result = pytester.runpytest("-v", "--slow")

# Check results
result.stdout.fnmatch_lines(["*pattern*"])
result.assert_outcomes(passed=1, skipped=1)
outcomes = result.parseoutcomes()  # Returns dict
```

### tox.ini for testing plugin across versions

```ini
[pytest]
testpaths = tests

[tox]
envlist = py{37,38,39,310}-pytest{62,70}
isolated_build = True

[testenv]
deps =
    pytest62: pytest==6.2.5
    pytest70: pytest==7.0.0
commands = pytest {posargs:tests}
description = Run pytest
```

```bash
# Run all environments in parallel with minimal output
tox -q --parallel
```

### Publishing plugins

**Option 1: Git repository**
```bash
pip install git+https://github.com/okken/pytest-skip-slow
```

**Option 2: Shared directory**
```bash
cp dist/*.whl path/to/my_packages/
pip install pytest-skip-slow --no-index --find-links=path/to/my_packages/
```

**Option 3: PyPI**
- See Python packaging documentation
- See Flit upload documentation

---

## Advanced Parametrization

### Basic parametrization with string values

```python
@pytest.mark.parametrize("start_state", ["done", "in prog", "todo"])
def test_finish(cards_db, start_state):
    c = Card("write a book", state=start_state)
    index = cards_db.add_card(c)
    cards_db.finish(index)
    card = cards_db.get_card(index)
    assert card.state == "done"
```

### Parametrization with objects (default numbered IDs)

```python
@pytest.mark.parametrize(
    "starting_card",
    [
        Card("foo", state="todo"),
        Card("foo", state="in prog"),
        Card("foo", state="done"),
    ],
)
def test_card(cards_db, starting_card):
    index = cards_db.add_card(starting_card)
    cards_db.finish(index)
    card = cards_db.get_card(index)
    assert card.state == "done"
```

Results in: `test_card[starting_card0]`, `test_card[starting_card1]`, `test_card[starting_card2]`

### Custom ID with str function

```python
card_list = [
    Card("foo", state="todo"),
    Card("foo", state="in prog"),
    Card("foo", state="done"),
]

@pytest.mark.parametrize("starting_card", card_list, ids=str)
def test_id_str(cards_db, starting_card):
    ...
```

Results in verbose output (full Card repr)

### Custom ID function

```python
def card_state(card):
    return card.state

@pytest.mark.parametrize("starting_card", card_list, ids=card_state)
def test_id_func(cards_db, starting_card):
    ...
```

Results in: `test_id_func[todo]`, `test_id_func[in prog]`, `test_id_func[done]`

### Custom ID with lambda

```python
@pytest.mark.parametrize(
    "starting_card", card_list, ids=lambda c: c.state
)
def test_id_lambda(cards_db, starting_card):
    ...
```

### Using pytest.param for individual IDs

```python
c_list = [
    Card("foo", state="todo"),
    pytest.param(Card("foo", state="in prog"), id="special"),
    Card("foo", state="done"),
]

@pytest.mark.parametrize("starting_card", c_list, ids=card_state)
def test_id_param(cards_db, starting_card):
    ...
```

Results in: `test_id_param[todo]`, `test_id_param[special]`, `test_id_param[done]`

### Using an ID list

```python
id_list = ["todo", "in prog", "done"]

@pytest.mark.parametrize("starting_card", card_list, ids=id_list)
def test_id_list(cards_db, starting_card):
    ...
```

### Using dictionary for IDs and values (keeps them synchronized)

```python
text_variants = {
    "Short": "x",
    "With Spaces": "x y z",
    "End In Spaces": "x   ",
    "Mixed Case": "SuMmArY wItH MiXeD cAsE",
    "Unicode": "¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾",
    "Newlines": "a\nb\nc",
    "Tabs": "a\tb\tc",
}

@pytest.mark.parametrize(
    "variant", text_variants.values(), ids=text_variants.keys()
)
def test_summary_variants(cards_db, variant):
    i = cards_db.add_card(Card(summary=variant))
    c = cards_db.get_card(i)
    assert c.summary == variant
```

### Dynamic parameter generation with function

```python
def text_variants():
    variants = {
        "Short": "x",
        "With Spaces": "x y z",
        "End in Spaces": "x   ",
        "Mixed Case": "SuMmArY wItH MiXeD cAsE",
        "Unicode": "¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾",
        "Newlines": "a\nb\nc",
        "Tabs": "a\tb\tc",
    }
    for key, value in variants.items():
        yield pytest.param(value, id=key)

@pytest.mark.parametrize("variant", text_variants())
def test_summary(cards_db, variant):
    i = cards_db.add_card(Card(summary=variant))
    c = cards_db.get_card(i)
    assert c.summary == variant
```

### Multiple parameters in tuple/list form

```python
@pytest.mark.parametrize(
    "summary, owner, state",
    [
        ("short", "First", "todo"),
        ("short", "First", "in prog"),
        # ... more combinations
    ],
)
def test_add_lots(cards_db, summary, owner, state):
    i = cards_db.add_card(Card(summary, owner=owner, state=state))
    card = cards_db.get_card(i)
    expected = Card(summary, owner=owner, state=state)
    assert card == expected
```

### Stacking parameters for matrix testing

```python
summaries = ["short", "a bit longer"]
owners = ["First", "First M. Last"]
states = ["todo", "in prog", "done"]

@pytest.mark.parametrize("state", states)
@pytest.mark.parametrize("owner", owners)
@pytest.mark.parametrize("summary", summaries)
def test_stacking(cards_db, summary, owner, state):
    """Creates 2 x 2 x 3 = 12 test cases"""
    i = cards_db.add_card(Card(summary, owner=owner, state=state))
    card = cards_db.get_card(i)
    expected = Card(summary, owner=owner, state=state)
    assert card == expected
```

### Indirect parametrization (parameter goes to fixture first)

```python
@pytest.fixture()
def user(request):
    role = request.param
    print(f"\nLog in as {role}")
    yield role
    print(f"\nLog out {role}")

@pytest.mark.parametrize(
    "user", ["admin", "team_member", "visitor"], indirect=["user"]
)
def test_access_rights(user):
    print(f"Test access rights for {user}")
```

### Selecting subset of fixture parameters

```python
@pytest.fixture(params=["admin", "team_member", "visitor"])
def user(request):
    role = request.param
    print(f"\nLog in as {role}")
    yield role
    print(f"\nLog out {role}")

# Uses all parameters
def test_everyone(user):
    ...

# Uses only subset
@pytest.mark.parametrize("user", ["admin"], indirect=["user"])
def test_just_admin(user):
    ...
```

### Optional indirect fixture with default value

```python
@pytest.fixture()
def user(request):
    # Use getattr with default for non-parametrized tests
    role = getattr(request, "param", "visitor")
    print(f"\nLog in as {role}")
    return role

# Works without parameters (uses default "visitor")
def test_unspecified_user(user):
    ...

# Works with parameters
@pytest.mark.parametrize(
    "user", ["admin", "team_member"], indirect=["user"]
)
def test_admin_and_team_member(user):
    ...
```

---

## Key Best Practices Summary

### 1. Configuration

- Use `--strict-markers` to catch marker typos
- Use `--strict-config` to catch config file errors
- Set `testpaths` to speed up test collection

### 2. Coverage

- Include test code in coverage to catch duplicate test names
- Use `# pragma: no cover` for `if __name__ == '__main__'` blocks
- Set minimum coverage with `--cov-fail-under`

### 3. Mocking

- Always use `autospec=True` to prevent mock drift
- Prefer testing behavior over implementation
- Consider testing at multiple layers to avoid mocking

### 4. tox

- Use `isolated_build = True` for pyproject.toml projects
- Use `skipsdist = true` for scripts without packaging
- Use `{posargs}` to pass pytest arguments through tox

### 5. Scripts

- Make scripts importable with `if __name__ == "__main__"`
- Use `pythonpath` for src/tests directory layouts
- Use `-rrequirements.txt` in tox deps for dependencies

### 6. Debugging

- Use `--lf` to re-run only failed tests
- Use `--lf --trace` to debug from test start
- Use `--pdb` to debug at failure point
- Use `-l` to show local variables in tracebacks

### 7. Plugins

- Use pytester fixture to test plugins
- Entry point section must be `[project.entry-points.pytest11]`
- Include `"Framework :: Pytest"` classifier

### 8. Parametrization

- Use custom ID functions for readable test names with objects
- Use dictionaries to keep IDs and values synchronized
- Use indirect parametrization when fixtures need to process values
- Use `getattr(request, "param", default)` for optional indirect fixtures

---

## Quick Reference

### Most Common pytest Commands

```bash
# Basic runs
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest -x                       # Stop on first failure
pytest --lf                     # Run last failed only
pytest -k "pattern"             # Run tests matching pattern
pytest -m "marker"              # Run tests with marker

# Debugging
pytest --pdb                    # Debug at failure
pytest --trace                  # Debug at start
pytest -l --tb=short            # Show locals, short traceback

# Coverage
pytest --cov=mypackage          # Run with coverage
pytest --cov-report=html        # Generate HTML report

# Parallel
pytest -n=auto                  # Run in parallel (pytest-xdist)
```

### Essential Configuration Template

```ini
# pytest.ini
[pytest]
addopts = --strict-markers --strict-config -ra
testpaths = tests
pythonpath = src
markers =
    slow: marks tests as slow
    integration: marks integration tests
```

### Essential tox.ini Template

```ini
[tox]
envlist = py39, py310, py311
isolated_build = True

[testenv]
deps =
    pytest
    pytest-cov
    -rrequirements.txt
commands = pytest --cov=src --cov-fail-under=80 {posargs}

[pytest]
addopts = --strict-markers -ra
testpaths = tests
pythonpath = src
```
