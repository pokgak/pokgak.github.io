---
title: "Tech Janitor: Linux Cookbook"
date: 2024-01-27T27:14:00+08:00
tags: [linux, tools, devops, vm]
draft: true
---

In this blog post I'll be listing out the tools that I frequently use in my day to day work but in a cookbook format where it's not just a random list of CLI tools but it is grouped by the goals that I'm trying to achive.

## Table of Contents

* Probing an instance from the outside
* Checking which service is running
* Checking the logs
* Monitor the system

## Probing an instance from the outside

### Check DNS record exists

```bash
## dig <domain> <record-type>

# when the record exists
$ dig pokgak.xyz +short
185.199.108.153
185.199.110.153
185.199.109.153
185.199.111.153

# when the record doesn't exist
$ dig pokgak.abc +short
# <empty>
```

### Check if a port is open

If you're having trouble connecting to an instance, you can check if the port is open by using `telnet`. This can be used for all protocols that use TCP ie HTTP(80/443), SSH(22), Postgres(5432), Redis(6379) etc.

```bash
## telnet <host> <port>

# when the port is open
$ telnet nuc 22
Trying 100.102.147.64...
Connected to nuc.hamster-nase.ts.net.
Escape character is '^]'.
SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.6
^]
telnet> Connection closed.

# when the port is closed
$ telnet nuc 80
Trying 100.102.147.64...
telnet: connect to address 100.102.147.64: Connection refused
telnet: Unable to connect to remote host
```

## Checking which service is running

### Check which process is listening on any port

Sometimes you want to know which process is listening on a port. This can be done using `ss`. Make sure to use `sudo` or run it as root because it won't show the process name if you don't.

```bash
$ sudo ss -ntlp
State    Recv-Q   Send-Q                     Local Address:Port        Peer Address:Port   Process
LISTEN   0        4096                      100.102.147.64:63177            0.0.0.0:*       users:(("tailscaled",pid=771,fd=26))
LISTEN   0        128                              0.0.0.0:22               0.0.0.0:*       users:(("sshd",pid=719,fd=3))
LISTEN   0        32                            10.45.81.1:53               0.0.0.0:*       users:(("dnsmasq",pid=1047,fd=7))
LISTEN   0        4096                       127.0.0.53%lo:53               0.0.0.0:*       users:(("systemd-resolve",pid=607,fd=14))
LISTEN   0        4096         [fd7a:115c:a1e0::a166:9340]:63177               [::]:*       users:(("tailscaled",pid=771,fd=28))
LISTEN   0        128                                 [::]:22                  [::]:*       users:(("sshd",pid=719,fd=4))
```

### Check systemd service status

If you're running a service using systemd, you can check the status of the service using `systemctl`.

```bash
## systemctl status <service-name>
```

### Check if a process is running

This might be useful if you know what process/program name you're looking for.

```base
## ps aux | grep <process-name>

$ ps aux | grep tailscale
root         771  0.3  0.2 1259760 43092 ?       Ssl  Jan25  11:45 /usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=41641
pokgak     30489  0.0  0.0   7008  2304 pts/0    S+   12:43   0:00 grep --color=auto tailscal
```

## Checking the logs

### Check systemd service logs

`journalctl` is a tool that can be used to check the logs of a systemd service. This is really useful when you're trying to debug a systemd service that is not running or keep on failing.

```bash
## journalctl -fu <service-name>
$ journalctl -fu tailscaled
```

### Check nginx logs

Some applications will write their logs to a certain folder. Usually on linux, the logs will be written to `/var/log/<app-name>`. For example, nginx will write its logs to `/var/log/nginx`.

`tail` will get the last 10 lines of a file. You can use `-f` to follow the file and print out the new lines that are added to the file.

```bash
tail -f /var/log/nginx/access.log
```

## Monitor the system

### Check CPU & Memory usage

`htop` is a tool that can be used to monitor the CPU and memory usage of a system. It's like `top` but with a better UI.

### Check disk usage

`df` is a tool that can be used to check the disk usage of a system. `-h` is used to make the output human readable. In linux, your hard drive usually will be represented as `/dev/sda` or `/dev/sdb` or other letters of alphabet if you have more disks in the system. The prefix number on the disk is the partition number. For example, `/dev/sda1` is the first partition of the first disk.

```bash
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           1.6G  1.5M  1.6G   1% /run
efivarfs        128K   87K   37K  71% /sys/firmware/efi/efivars
/dev/sda2       457G   15G  419G   4% /
tmpfs           7.8G     0  7.8G   0% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
/dev/sda1       1.1G  6.1M  1.1G   1% /boot/efi
tmpfs           1.6G  4.0K  1.6G   1% /run/user/1000
```
