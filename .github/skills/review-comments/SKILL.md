---
name: review-comments
description: Review and clean up code comments - remove redundant, obvious, outdated, or incorrect comments while preserving valuable documentation. Use when user says "review comments" on any code file.
---

# Comment & Docstring Review

Review code comments and docstrings for quality. Remove or trim those that hurt readability.

---

## When to Use

- User says "review comments" on a file
- User asks to "clean up comments" or "audit comments"
- User wants to improve code documentation quality

---

## Part 1: Inline Comments

### ❌ REMOVE These Comments

#### 1. Obvious/Redundant Comments
Comments that restate what the code clearly does:
```python
# BAD: Increment counter
counter += 1

# BAD: Return the user
return user

# BAD: Loop through items
for item in items:
```

#### 2. Commented-Out Code
Dead code that should be deleted, not commented:
```python
# BAD:
# old_value = calculate_old_way(x)
# if old_value > threshold:
#     do_something()
new_value = calculate_new_way(x)
```

#### 3. TODO/FIXME Without Context
Vague todos that will never be actionable:
```python
# BAD: TODO: fix this
# BAD: FIXME: refactor later
# BAD: TODO
```

#### 4. Misleading/Outdated Comments
Comments that no longer match the code:
```python
# BAD: Returns a list of users (but function now returns dict)
def get_users() -> dict[str, User]:
```

#### 5. Section Separators Without Value
```python
# BAD:
##################################
# IMPORTS
##################################
import os
```

#### 6. Change Log Comments
Version control handles this:
```python
# BAD: Added by John on 2024-01-15
# BAD: Modified to fix bug #123
```

---

### ✅ KEEP These Comments

#### 1. Why Comments (Intent/Reasoning)
```python
# GOOD: Use insertion sort for small arrays - faster than quicksort under n=10
if len(arr) < 10:
    insertion_sort(arr)
```

#### 2. Non-Obvious Behavior
```python
# GOOD: PostgreSQL's ON CONFLICT doesn't trigger Column.onupdate
update_set["updated_at"] = datetime.now(UTC)
```

#### 3. External References
```python
# GOOD: Algorithm from https://example.com/paper.pdf Section 3.2
```

#### 4. Workarounds/Hacks with Justification
```python
# GOOD: Workaround for httpx bug #1234 - remove after v0.25
await asyncio.sleep(0.1)
```

#### 5. Complex Regex/Algorithm Explanation
```python
# GOOD: Match URLs with optional port: scheme://host[:port]/path
URL_PATTERN = r"^(https?):\/\/([^:\/]+)(?::(\d+))?(\/.*)?$"
```

#### 6. Warning Comments
```python
# GOOD: WARNING: This function is not thread-safe
# GOOD: SECURITY: Input must be sanitized before calling
```

---

## Part 2: Docstrings

### The Redundancy Test

For each line in a docstring, ask: **"Does this add information beyond the function signature?"**

```python
# SIGNATURE:
async def upsert_on_conflict[T](
    db: AsyncSession,
    model: type[T],
    values: dict[str, Any],
    index_elements: list[str],
    update_fields: list[str],
    *,
    returning: bool = False,
) -> T | None:
```

#### ❌ REMOVE from Args (redundant with types):
```python
# BAD - type already says AsyncSession:
db: The async database session

# BAD - type already says type[T]:
model: The SQLAlchemy model class

# BAD - return type is T | None:
Returns:
    The upserted model instance if returning=True, else None
```

#### ✅ KEEP in Args (adds semantic meaning):
```python
# GOOD - explains what the keys/values represent:
values: Column name -> value mapping for insert.

# GOOD - clarifies purpose beyond "list of strings":
index_elements: Columns forming the unique constraint to match on.
```

### Docstring Trimming Rules

#### 1. Skip Args That Are Self-Documenting
If parameter name + type tells the whole story, omit it:
```python
# SKIP: db: AsyncSession - obvious
# SKIP: model: type[T] - obvious
# SKIP: user_id: str - obvious
```

#### 2. Skip Redundant Returns Section
If return type annotation is clear, skip Returns:
```python
# SKIP when signature has -> User | None
# The type hint says it all

# KEEP when behavior is conditional:
Returns:
    The upserted row if returning=True, else None.
```

#### 3. Compress Verbose Explanations
```python
# BEFORE (verbose):
Note:
    This function does NOT commit. The caller (typically the get_db
    dependency) is responsible for committing the transaction.

# AFTER (concise):
Note:
    Does NOT commit. Caller owns the transaction.
```

#### 4. Keep Non-Obvious Warnings
```python
# KEEP - critical gotcha:
Warning:
    Column.onupdate triggers are NOT applied during ON CONFLICT DO UPDATE.
```

### Docstring Quality Checklist

| Section | Keep If... | Remove If... |
|---------|-----------|--------------|
| Summary line | Always keep | Never (required) |
| Args: param | Adds meaning beyond type hint | Just restates the type |
| Returns: | Explains conditional behavior | Just restates return type |
| Raises: | Documents exceptions to handle | Obvious from code |
| Note: | Important contract/behavior | Obvious from implementation |
| Warning: | Gotcha that could bite callers | Already well-known |
| Example: | Complex usage pattern | Simple/obvious usage |

### Before/After Example

```python
# ❌ BEFORE (verbose, redundant):
def upsert_on_conflict[T](
    db: AsyncSession,
    model: type[T],
    values: dict[str, Any],
    index_elements: list[str],
    update_fields: list[str],
    *,
    returning: bool = False,
) -> T | None:
    """
    Perform an upsert (INSERT ... ON CONFLICT DO UPDATE).

    Args:
        db: The async database session
        model: The SQLAlchemy model class
        values: Dict of column name -> value for the insert
        index_elements: Column names that form the unique constraint
        update_fields: Column names to update on conflict
        returning: If True, return the upserted row (saves a round-trip)

    Returns:
        The upserted model instance if returning=True, else None

    Note:
        This function does NOT commit. The caller (typically the get_db
        dependency) is responsible for committing the transaction.
    """
```

```python
# ✅ AFTER (concise, no redundancy):
def upsert_on_conflict[T](
    db: AsyncSession,
    model: type[T],
    values: dict[str, Any],
    index_elements: list[str],
    update_fields: list[str],
    *,
    returning: bool = False,
) -> T | None:
    """
    Perform an upsert (INSERT ... ON CONFLICT DO UPDATE).

    Args:
        values: Column name -> value mapping for insert.
        index_elements: Columns forming the unique constraint to match on.
        update_fields: Columns to update when conflict occurs.
        returning: Return the upserted row (saves a SELECT round-trip).

    Note:
        Does NOT commit. Caller owns the transaction.
    """
```

**What was removed:**
- `db` and `model` args (type hints are sufficient)
- `Returns:` section (return type `T | None` is clear, conditional behavior moved to `returning` arg description)
- Verbose phrasing trimmed throughout

---

## Review Process

### Step 1: Read the File
Read the entire file to understand context before judging.

### Step 2: Analyze Each Comment/Docstring

For inline comments:
- Does it explain WHY, not WHAT?
- Does it match the current code?

For docstrings:
- Does each Args entry add info beyond the type hint?
- Is the Returns section redundant with the return type?
- Can verbose explanations be compressed?

### Step 3: Propose Changes

```markdown
## Comment Review: [filename]

### Removed
| Location | Content | Reason |
|----------|---------|--------|
| Line 45 | `# increment i` | Obvious |
| Docstring Args | `db: The async database session` | Redundant with type hint |

### Trimmed
| Location | Before | After |
|----------|--------|-------|
| Docstring Note | "This function does NOT commit. The caller..." | "Does NOT commit. Caller owns the transaction." |

### Kept
- Warning section (critical gotcha about onupdate)
- Args for values, index_elements (add semantic meaning)
```

### Step 4: Apply Changes
Use multi_replace_string_in_file to apply all changes efficiently.

---

## Language-Specific Notes

### Python
- Docstrings required on public functions (PEP 257)
- Skip Args that match `param_name: TypeHint` pattern exactly
- `# type: ignore` needs explanation
- `# noqa` needs rule name

### TypeScript/JavaScript
- JSDoc on exported functions
- Skip `@param` when TS types are present
- `// @ts-ignore` needs justification

### Terraform
- `#` comments for non-obvious configs
- Document why defaults are overridden

---

## Example Trigger Phrases

- "review comments"
- "clean up comments"
- "audit comments in this file"
- "trim docstrings"
- "remove redundant documentation"
