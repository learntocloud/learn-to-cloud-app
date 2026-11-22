Git records changes to files in a repository. A commit is a snapshot you can
inspect later. You will create a small repository, work on a branch, and send
your commits to GitHub.

Use a terminal on Linux or macOS, or a WSL terminal on Windows. Complete the
Install Git step first. Run `git --version` to confirm that Git is available.

> [!NOTE]
> Run the commands in this lesson in a new practice directory, not in an
> existing project.

## Create a repository

```bash
mkdir git-practice
cd git-practice
git init -b main
```

Git creates a `.git` directory for the repository's history and settings.
Set your commit identity for this repository. Replace the example values with
your name and your GitHub email address.

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
```

Git stores this identity in each commit. GitHub can associate commits with
your account when the email matches a verified address on your account.

## Make a commit

Create a file, inspect the repository, and stage the file:

```bash
echo "My Git practice" > notes.txt
git status
git add notes.txt
git status
git commit -m "Add practice notes"
```

`git status` shows which changes are untracked, staged, or unstaged.
`git add` stages the current contents of a file. `git commit` records the
staged snapshot. A later edit is not part of that snapshot until you stage
and commit it.

## Inspect changes and history

```bash
echo "I am learning to use Git." >> notes.txt
git diff
git add notes.txt
git diff --staged
git commit -m "Expand practice notes"
git log --oneline
git status
```

`git diff` shows unstaged changes. `git diff --staged` shows what the next
commit will contain. The log shows your commits, newest first. After the
commit, status should report a clean working tree.

## Work on a branch

A branch lets you make a change without moving the `main` branch.

```bash
git switch -c add-goal
echo "Goal: use Git with confidence." >> notes.txt
git add notes.txt
git commit -m "Add a learning goal"
git switch main
cat notes.txt
```

On `main`, the file does not yet include the goal. Merge the branch and
inspect the result:

```bash
git merge add-goal
cat notes.txt
git log --oneline --graph --all
```

The goal is now on `main`. If Git reports a merge conflict, it has stopped
before completing the merge. Read `git status`, resolve the marked lines in
the file, stage the resolved file, and run `git commit`.

## Share the repository

Create a new, empty repository on GitHub. Do not initialize it with a README,
license, or `.gitignore`: your local repository already has commits. Copy its
HTTPS repository URL from GitHub.

In the next command, replace the example URL with the URL you copied:

```bash
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git remote -v
git push -u origin main
```

`origin` is a local name for the remote repository. The first push sets the
upstream branch, so later commits can be sent with `git push`. Authenticate
when Git prompts you, using your configured GitHub authentication method.
Refresh the GitHub repository page and check that `notes.txt` and your commits
appear.

> [!WARNING]
> Do not put passwords, tokens, or other secrets in this repository. Git
> history can retain committed content even after you remove it from a file.

You are done when your local `main` contains the merged goal and GitHub shows
the same file and commits. You can keep this repository for more practice.
