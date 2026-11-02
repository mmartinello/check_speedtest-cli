# check_speedtest

Nagios/Icinga plugin to monitor WAN connection speed. It runs a speed test with
the Python `speedtest-cli` or the Ookla `speedtest` command, or reads the JSON
result of a previous test from a file, and compares download and upload speed
with the given levels.

## Requirements

- Python 3.7 or later, with no additional modules
- One of the following commands, unless `--from-file` is used:
  - `speedtest-cli`, the Python tool (`pip install speedtest-cli`)
  - `speedtest`, the official Ookla command

## Installation

Copy `check_speedtest.py` to your plugins directory and make it executable:

```sh
cp check_speedtest.py /usr/lib/nagios/plugins/
chmod 755 /usr/lib/nagios/plugins/check_speedtest.py
```

## Usage

```sh
# Warning below 50 Mbit/s and critical below 20 Mbit/s in download,
# warning below 10 Mbit/s and critical below 5 Mbit/s in upload
check_speedtest.py -w 50 -c 20 -W 10 -C 5

# Also give the connection maximum speeds, used in perfdata
check_speedtest.py -w 50 -c 20 -W 10 -C 5 -m 100 -M 20

# Check only the download speed against a specific server
check_speedtest.py --no-upload -s 1234 -w 50 -c 20

# Test a specific WAN connection, on a multi-WAN host
check_speedtest.py --source 192.0.2.10 -w 50 -c 20
```

Example output:

```text
OK - Download speed: 93.46 Mbit/sec, Upload speed: 21.99 Mbit/sec, Ping: 12.35 ms (server: Example ISP, Milan) (command: speedtest-cli, Python) | 'download_speed'=93.46;50.0:;20.0: 'upload_speed'=21.99;10.0:;5.0: 'ping'=12.35ms;;;0
```

## Options

### Levels

| Option | Description |
|---|---|
| `-w` | Download warning level in Mbit/s |
| `-c` | Download critical level in Mbit/s |
| `-W` | Upload warning level in Mbit/s |
| `-C` | Upload critical level in Mbit/s |
| `-m` | Maximum download level in Mbit/s for the connection |
| `-M` | Maximum upload level in Mbit/s for the connection |

Levels are optional and accept decimals. An alarm is raised when the speed falls
below the level, so a warning level must be bigger than the critical one, and a
maximum level must not be lower than the warning and critical ones.

### Speed test

| Option | Description |
|---|---|
| `--python` | Use the Python `speedtest-cli` command |
| `--ookla` | Use the Ookla `speedtest` command |
| `--command COMMAND` | Speedtest command or path |
| `-s`, `--server ID` | Server ID to test against |
| `--source IP` | Source IP address to bind to |
| `--secure` | Use HTTPS with speedtest.net servers (`speedtest-cli` only) |
| `--no-download` | Do not perform the download test (`speedtest-cli` only) |
| `--no-upload` | Do not perform the upload test (`speedtest-cli` only) |
| `-t`, `--timeout SECONDS` | Speedtest command timeout, 90 by default |

`--no-download` and `--no-upload` cannot be used together, or with the levels of
the disabled test.

Keep the timeout lower than the one of the caller (Icinga, NRPE), otherwise the
caller stops the check before the plugin can report the problem.

### Reading the result from a file

| Option | Description |
|---|---|
| `-f`, `--from-file PATH` | Read the JSON output from a file instead of running the test |
| `--max-age MINUTES` | Exit with UNKNOWN if the file is older than the given minutes |

### Other

| Option | Description |
|---|---|
| `--always-ok` | Always exit with OK, keeping the level markers in the message |
| `--debug` | Print debugging info to console |
| `--debug2` | Print debugging info and exceptions to console |
| `-V`, `--version` | Print the version |
| `-h`, `--help` | Print the help |

`--debug` and `--debug2` are meant to be used by hand: their output may break
the check when it is run by Icinga.

## Speedtest command selection

Without `--python`, `--ookla` and `--command`, the plugin looks for the commands
in the `PATH` and reports the selected one in the message:

| Commands found | Command used |
|---|---|
| Ookla `speedtest` | `speedtest`, Ookla |
| `speedtest-cli` | `speedtest-cli`, Python |
| Ookla `speedtest` and `speedtest-cli` | `speedtest`, Ookla |
| `speedtest` and `speedtest-cli`, both installed by pip | `speedtest-cli`, Python |
| `speedtest` installed by pip | `speedtest`, Python |
| None | UNKNOWN |

The `speedtest-cli` package installs a `speedtest` command too: the plugin runs
`speedtest --version` to tell it from the Ookla one.

With `--no-download`, `--no-upload` or `--secure` the plugin selects
`speedtest-cli` even if the Ookla command is available. If only the Ookla command
is available, it exits with UNKNOWN.

`--command` without `--ookla` uses the `speedtest-cli` syntax. To run the Ookla
command from a custom path, use both options:

```sh
check_speedtest.py --ookla --command /opt/ookla/speedtest -w 50 -c 20
```

### Ookla license

The plugin runs the Ookla command with `--accept-license` and `--accept-gdpr`,
which accept the Ookla license and GDPR terms for the user running the check.
This also happens when the command is selected automatically. Use `--python` if
you do not want it.

## Use with cron and NRPE

A speed test takes longer than the usual NRPE timeout and uses a lot of
bandwidth. You can run it from cron, and let the check only read the result.

Write the result to a temporary file and then rename it, so that the check never
reads a partial result:

```cron
# speedtest-cli
*/30 * * * * nagios speedtest-cli --json > /var/tmp/speedtest.tmp && mv /var/tmp/speedtest.tmp /var/tmp/speedtest.json

# Ookla speedtest
*/30 * * * * nagios speedtest --format=json --accept-license --accept-gdpr > /var/tmp/speedtest.tmp && mv /var/tmp/speedtest.tmp /var/tmp/speedtest.json
```

Then define the command in the NRPE configuration:

```ini
command[check_speedtest]=/usr/lib/nagios/plugins/check_speedtest.py -f /var/tmp/speedtest.json --max-age 60 -w 50 -c 20 -W 10 -C 5
```

The file format is detected from its content, so `--ookla` is not needed. The
options of the speedtest command are ignored, except for `--no-download` and
`--no-upload`, which must be used if the test was disabled in the cron job:
`speedtest-cli` reports a disabled test with speed 0.

## Exit codes

| Code | Status | Meaning |
|---|---|---|
| 0 | OK | Speeds are above the levels, or `--always-ok` is set |
| 1 | WARNING | A speed is below its warning level |
| 2 | CRITICAL | A speed is below its critical level |
| 3 | UNKNOWN | Wrong arguments, or no valid result available |

The status is the worst one between download and upload. The value out of range
is marked in the message with `[WARNING]` or `[CRITICAL]`.

UNKNOWN is returned when the arguments are not valid, the speedtest command is
missing, times out or fails, the output is not valid, a requested test has no
value, the file cannot be read or is older than `--max-age`.

## Performance data

| Label | Unit | Warning, critical | Min, max |
|---|---|---|---|
| `download_speed` | Mbit/s, not reported in the UOM | `-w`, `-c` | 0 and `-m`, if given |
| `upload_speed` | Mbit/s, not reported in the UOM | `-W`, `-C` | 0 and `-M`, if given |
| `ping` | `ms` | None | 0, no max |

Levels are in the `x:` range format, since a low value is the bad one. The speed
of a disabled test is not reported, and so is the ping if it is missing from the
result.
