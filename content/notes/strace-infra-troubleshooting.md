---
title: "strace for infra troubleshooting"
date: 2026-04-15T17:53:31+0800
tags: [infra, linux, debugging, python]
---

`strace` traces every syscall a process makes. Since almost everything a program does — reading files, spawning threads, talking to the network, allocating memory — goes through the kernel, strace gives you a ground-truth view of what's actually happening at runtime, independent of what the code or docs say.

Useful for:
- Diagnosing slow startup or imports (filesystem latency, lock contention)
- Figuring out which files a program opens (config resolution, library search paths)
- Debugging "works on my machine" failures (missing files, wrong permissions, unexpected paths)
- Understanding network behaviour without source code
- Confirming whether a program is actually sleeping, spinning, or blocked on I/O

## Basic usage

```bash
# Trace all syscalls, print to stderr
strace <command>

# Follow threads/child processes
strace -f <command>

# Aggregate summary: counts + total time per syscall (no per-call output)
strace -f -c <command>

# Filter to specific syscalls only
strace -e trace=openat,read <command>

# Attach to a running process
strace -p <pid>
```

For profiling imports specifically — run the binary directly, not through a wrapper like `uv run`, otherwise you profile the launcher waiting for the child, not the import itself.

## Case study: slow filesystem (Python import)

### Reading the output

`strace -c` prints a table sorted by time:

```
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- --------
 98.71  376.123456        1481    254012           futex
  0.91    3.470000          12    289450           openat
  0.38    1.450000           5    290000           read
```

Common mistake: `futex` dominating (>90%) looks like a locking/threading problem, not a filesystem problem. It often IS a filesystem problem — just indirectly.

### Import lock amplification

Python's import system uses a per-module lock (a `futex`). When many threads import the same module:

1. Thread A acquires the import lock, reads the file from disk — **holds lock while reading**
2. All other threads (B, C, D...) block on `futex` waiting for the lock
3. Thread A finishes → releases → next thread acquires → reads → rest block again
4. This cascades across every module in the import graph

`strace -f -c` sums time across all threads. So 254 threads each waiting 1.5s on a lock shows as ~381s of aggregated futex time — even though wall time is much shorter. A slow filesystem makes Thread A hold the lock longer, which amplifies the wait for every other thread.

**The filesystem is the root cause, but it appears as futex time.**

### Distinguishing causes

| strace output | Likely cause |
|---|---|
| `futex` >> everything, filesystem syscalls tiny | Import lock amplification from slow reads, OR genuine Python/CUDA init |
| `openat`/`stat` high count + high time | Direct filesystem bottleneck (no page cache, high per-call latency) |
| `read` high time | Slow file data reads — storage or page cache issue |
| `mmap`/`mprotect` high | Shared object loading — not filesystem latency |

To tell import lock amplification apart from genuine Python/CUDA overhead:

```bash
# Copy venv to local fast storage, rerun
cp -r /slow-fs/.venv /tmp/test-venv
strace -f -c /tmp/test-venv/bin/python3 -c "import slow.module"
```

If wall time drops dramatically → filesystem was the cause. If wall time stays the same → genuine Python/CUDA init overhead.

## Syscall crash course

Knowing what each syscall does lets you read strace output without guessing.

**Filesystem**

| Syscall | What it does | High count/time means |
|---|---|---|
| `openat` | Open a file | Many small files being opened (e.g. Python `.py` and `.pyc` files per import) |
| `read` | Read bytes from a file descriptor | File data reads are slow — storage or cache miss |
| `write` | Write bytes to a file descriptor | Write throughput bottleneck |
| `close` | Close a file descriptor | Usually cheap; high count confirms many opens |
| `stat` / `fstat` / `newfstatat` | Get file metadata (size, mtime, permissions) | Filesystem doing many metadata lookups — common in Python import path resolution |
| `getdents64` | Read directory entries | Directory listing; slow on large or remote directories |
| `lseek` | Move file offset | Repositioning within a file |

**Memory**

| Syscall | What it does | High count/time means |
|---|---|---|
| `mmap` | Map file or anonymous memory | Library (`.so`) loading, memory allocation |
| `munmap` | Unmap memory | Cleanup of mappings |
| `mprotect` | Change memory region permissions | Part of shared library loading — set segment permissions after mapping |
| `brk` | Extend/shrink heap | Heap allocation via `malloc` |

**Threading / synchronisation**

| Syscall | What it does | High count/time means |
|---|---|---|
| `futex` | Fast userspace mutex (kernel arbitrates contention) | Lock contention — many threads waiting. Often caused by a slow operation holding a lock, not the lock itself |
| `clone` | Create thread or process | High thread spawn rate |

**Process**

| Syscall | What it does | High count/time means |
|---|---|---|
| `execve` | Execute a program | Process launch — slow if filesystem is slow |
| `wait4` / `waitid` | Wait for child process to exit | Parent blocked on child |
| `exit_group` | Exit all threads in process | Normal shutdown |

**Networking / IPC**

| Syscall | What it does | High count/time means |
|---|---|---|
| `socket` | Create a socket | Network or Unix socket setup |
| `connect` | Connect to an address | Outbound connection — high time = connection latency or refusal |
| `recvfrom` / `recvmsg` | Receive data | Network read blocked or slow |
| `sendto` / `sendmsg` | Send data | Network write |
| `epoll_wait` / `poll` / `select` | Wait for I/O events | Event loop idle time — high time is normal for servers waiting on clients |
| `ioctl` | Device control | Driver-level operations; common in GPU/CUDA and network device paths |

**Timing**

| Syscall | What it does | High count/time means |
|---|---|---|
| `nanosleep` / `clock_nanosleep` | Sleep for a duration | Deliberate sleeps or backoff loops in the program |
| `clock_gettime` | Read a clock | Profiling or timeout checks inside the program; very cheap |

### Quick pattern guide

- **Slow startup, many `openat` + `stat`** → filesystem latency on metadata ops. Common with network filesystems and Python imports.
- **`futex` dominates, filesystem syscalls are fast** → lock contention amplified by slow I/O (see import lock amplification above), or genuine thread synchronisation.
- **`mmap` + `mprotect` high time** → shared library loading from slow storage.
- **`epoll_wait` dominates** → program is idle waiting for network — usually expected.
- **`nanosleep` unexpectedly high** → check for retry loops or deliberate throttling in the code.

## Caveats

- `strace -f` adds overhead — wall times will be longer than uninstrumented. Use for relative comparisons only.
- CUDA init (`libcuda.so` loading) contributes a fixed 3–8s baseline regardless of filesystem.
- Lock amplification scales with thread count. Single-threaded imports won't show this pattern.
