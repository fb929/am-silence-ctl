# am-silence-ctl

Command-line tool to create or delete silences in [Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/).

## Features

- Create silences with flexible matchers.
- Delete active silences matching given matchers.
- Optional comment and duration.
- Matchers can include:
  - `alertname` (from CLI)
  - `role` (default from config, overridable via `-r VALUE`)
  - `group` (default from config, overridable via `-g VALUE`)
  - `fqdn` (fallback from system hostname when no other matcher is provided)
- `--dry-run` mode (prints actions without calling the API).
- YAML config for defaults: `alertmanager_url`, `role`, `group`.

## Installation

Copy `am-silence-ctl.py` somewhere in your `$PATH` and make it executable:

```bash
chmod +x am-silence-ctl.py
sudo mv am-silence-ctl.py /usr/local/bin/am-silence-ctl
```

Requires Python 3.7+:

```bash
pip install requests pyyaml
```

## Configuration

Config is optional. Default Alertmanager URL is `http://127.0.0.1:9093`.

By default, the tool looks for config in:

- `/etc/am-silence-ctl/config.yaml`
- `~/.am-silence-ctl.yaml`

Example config:

```yaml
alertmanager_url: "http://127.0.0.1:9093"
role: "prod"
group: "billing-db"
```

### Supported config keys

- `alertmanager_url` — base URL to Alertmanager (without `/api/v2`).
- `role` — default value used when `-r/--role` is passed without an explicit value.
- `group` — default value used when `-g/--group` is passed without an explicit value.

## Usage

### Quick start (create silence)

Create a 2-hour silence matching current host FQDN (fallback):

```bash
am-silence-ctl
```

Create with `alertname`:

```bash
am-silence-ctl --alertname HighCPU
```

Create with role from config:

```bash
am-silence-ctl -r
```

Create with a custom role:

```bash
am-silence-ctl -r backend
```

Create with group from config:

```bash
am-silence-ctl -g
```

Create with a custom group:

```bash
am-silence-ctl -g frontend
```

Multiple matchers + comment:

```bash
am-silence-ctl --alertname HighCPU -r -g analytics -c "Planned maintenance"
```

Custom duration:

```bash
am-silence-ctl --hours 4
```

Dry-run (no API calls):

```bash
am-silence-ctl -r -g --dry-run
```

### Delete silences

Delete active silences that match current host FQDN:

```bash
am-silence-ctl --delete
```

Delete by `alertname`:

```bash
am-silence-ctl --alertname HighCPU --delete
```

Delete by role/group:

```bash
am-silence-ctl -r -g --delete
```

Dry-run deletion:

```bash
am-silence-ctl --alertname HighCPU --delete --dry-run
```

## CLI reference

```
am-silence-ctl [-h] [-c COMMENT] [--hours HOURS] [--alertname ALERTNAME]
               [-r [ROLE]] [-g [GROUP]] [-d] [--dry-run]
               [--config CONFIG]
```

- `-c, --comment` — optional comment (create mode).
- `--hours` — silence duration in hours (create mode, default: `2`).
- `--alertname` — value for the `alertname` label (optional).
- `-r, --role [ROLE]` — include `role` matcher.  
  - With value → use provided value.  
  - Without value → use `role` from config.  
- `-g, --group [GROUP]` — include `group` matcher.  
  - With value → use provided value.  
  - Without value → use `group` from config.  
- `-d, --delete` — deletion mode (find and delete *active* silences matching all provided matchers).
- `--dry-run` — print what would be created/deleted without calling the API.
- `--config` — path to YAML config (defaults: `/etc/am-silence-ctl/config.yaml`, `~/.am-silence-ctl.yaml`).

## Matching rules

- If **no** `--alertname`, `-r/--role`, or `-g/--group` is provided, the tool falls back to `fqdn=<system fqdn>`.
- In deletion mode, the tool deletes every **active** silence whose matcher set is a **superset** of the provided matchers (exact name/value/isRegex=false).

## Logging

Logs include timestamps and levels, for example:

```
2025-09-25 14:00:01 [INFO] Added matcher fqdn=server1.example.com
2025-09-25 14:00:01 [INFO] Prepared request: url='http://127.0.0.1:9093/api/v2/silences'; data={...}
2025-09-25 14:00:02 [INFO] Silence created successfully: 1234abcd-5678-efgh
```

## Exit codes

- `0` — success.  
- Non-zero — error (invalid config/args, network/API error, etc.).

## License

This project is licensed under the terms of the [MIT License](./LICENSE).
