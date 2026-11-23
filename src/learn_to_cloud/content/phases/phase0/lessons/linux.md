Linux is used in many cloud servers. Learning a few Linux concepts and
commands will help you understand and work with those servers.

## What is Linux?

An operating system manages a computer's hardware and lets programs run.
Linux is the kernel, the part of an operating system that manages resources
such as memory and devices. People often use “Linux” to mean a complete
operating system built around that kernel.

Linus Torvalds started the Linux kernel in 1991. Its source code is open,
so people can study, change, and share it under its license. A large
community and many organizations maintain the software around it.
Linux matters in the cloud because it runs on many servers and supports
automation, networking, and a wide range of applications.

## Distributions

A Linux distribution combines the kernel with software and tools. Ubuntu
and Debian are common distributions. Fedora and Red Hat Enterprise Linux
are other examples. They share Linux fundamentals, but their tools,
release schedules, and support options can differ.

You do not need to master every distribution. Start with one and learn how
to find its documentation.

## Try a terminal

A terminal lets you enter commands as text. A shell reads those commands.
The examples below use a Linux shell. If you use Linux, open its terminal.
On Windows, use a Linux distribution installed through Windows Subsystem
for Linux (WSL). On macOS, use a Linux environment such as a virtual
machine; the macOS terminal has similar commands but is not Linux.

If you do not have a Linux environment yet, read the examples now and
return to them after you set one up. Phase 1 includes local terminal setup.
Run the commands in your own home directory, not on a shared server.

```bash
pwd
ls
mkdir cloud-practice
cd cloud-practice
echo "Hello, cloud" > notes.txt
cat notes.txt
ls
cd ..
```

`pwd` prints the current directory. `ls` lists its contents. `mkdir`
creates a directory, and `cd` changes directories. The `echo` command
writes a line to `notes.txt`; `cat` prints that line. The final `ls`
should show `notes.txt`. `cd ..` returns to the parent directory.
The `>` symbol replaces a file's contents, so use it only with a practice
file you are willing to overwrite.

Try explaining what each command does before you run it again. If a
command reports an error, read the message and check the directory shown
by `pwd`.

## Go deeper

These resources are optional:

- [Linux Documentary](https://www.youtube.com/watch?v=zPt_e9Cdk08)
- [Bash scripting and command line for beginners](https://www.freecodecamp.org/news/bash-scripting-tutorial-linux-shell-script-and-command-line-for-beginners/)
