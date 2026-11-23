A program is a set of instructions a computer can follow. A programming
language gives people a way to write those instructions. A cloud engineer
can use a program to repeat a task, inspect results, or change resources
without performing every action by hand.

## Read a small program

Python is a programming language used for automation. This example stores
a service name and prints it:

```python
service = "journal-api"
print(service)
```

`service` is a variable: a name for a value. The text between quotes is a
string. `print` displays the value. The output is:

```text
journal-api
```

When you complete the next step, install Python and do the Day 1 exercises.
Then run the examples in this lesson as well.

## Read JSON

Cloud services often return data from an API, an interface that lets one
program request information from another. A common format for this data is
JSON. JSON represents an object as named values. Here is a small example:

```json
{"service": "journal-api", "healthy": true, "requests": 128}
```

The object has three names: `service`, `healthy`, and `requests`. Their
values are text, a true-or-false value, and a number.

Save the following as `read_service.py` after you install Python:

```python
import json

response = '{"service": "journal-api", "healthy": true, "requests": 128}'
data = json.loads(response)

print(data["service"])
print(data["requests"])
```

Run it with your system's Python command, for example
`python read_service.py` or `python3 read_service.py`. The output is:

```text
journal-api
128
```

`json.loads` converts the JSON text into Python data. The square brackets
select values by name. This example uses local sample data; it does not
contact an API. Try changing the request count, then run the script again.
If you get an error, check the quotes, braces, and spelling.

## Connect programming to cloud work

Imagine checking the health of ten services. A script can read each
response and report which services need attention. Automation makes a
repeatable task easier to perform, but you still need to understand and
check what the program does.
