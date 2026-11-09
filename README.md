# Garden Diagnostic Agent

[![Tests](https://github.com/anthony-marr/garden-diagnostic-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/anthony-marr/garden-diagnostic-agent/actions/workflows/tests.yml)

An MCP (Model Context Protocol) server and agent host for diagnosing garden
plant stress. The server exposes two data sources as MCP tools - Open-Meteo
weather and a SQLite planting log - and the agent host connects over MCP and
chains those tools into a full garden check.

## How it fits together

```
+-------------------+        MCP (stdio)        +----------------------+
|   agent host      |  ---------------------->  |   MCP server         |
|  (garden check)   |   list_plantings          |                      |
|                   |   diagnose_planting x N   |  tools:              |
|                   | <----------------------   |   log_planting       |
|                   |      GardenCheckReport    |   list_plantings     |
+-------------------+                           |   log_observation    |
                                                |   list_observations  |
        diagnose_planting chains internally:    |   get_weather        |
        log lookup -> weather fetch -> rules    |   diagnose_planting  |
                                                +----------+-----------+
                                                           |
                                        +------------------+------------------+
                                        |                                     |
                              +---------v---------+               +-----------v------+
                              |  SQLite log       |               |  Open-Meteo API  |
                              |  plantings +      |               |  daily weather,  |
                              |  observations     |               |  no key needed   |
                              +-------------------+               +------------------+
```

Every tool validates its inputs and outputs with pydantic models
(`src/garden_mcp/schemas.py`), so bad dates, out-of-range coordinates, and
empty names fail at the boundary instead of corrupting the log. Diagnostics
are transparent rules over the weather window (`src/garden_mcp/diagnostics.py`):
frost, heat, water deficit versus evapotranspiration, excess water, and wind.

## Quickstart

```bash
pip install -r requirements-dev.txt
python -m pytest -q        # 40 tests, no network needed (Open-Meteo is mocked)
python -m garden_mcp.demo  # end-to-end: seeds sample data, live weather, agent check
```

Run the server for any MCP host (Claude Desktop, etc.):

```bash
python -m garden_mcp.server    # speaks MCP over stdio
```

Run the agent host, which spawns the server and chains its tools:

```bash
python -m garden_mcp.agent tools            # list exposed tools
python -m garden_mcp.agent check --db garden.db
```

Load your own garden data (format in `src/garden_mcp/seed.py` docstring):

```bash
python -m garden_mcp.seed data/sample_garden.json --db garden.db
```

`data/sample_garden.json` is synthetic. `data/garden_2026.json` is a real
container-garden log (raised beds, buckets, and pots in Washington, DC):
13 plantings and 11 dated field observations logged from the garden's photo
record. Planting dates are left out where they aren't known; the observations
carry the real dates.

## Sample output

A real garden check against that log (live Open-Meteo weather for the
garden's coordinates, trimmed to one planting):

```json
{
  "checked_plantings": 13,
  "diagnoses": [
    {
      "planting_id": 6,
      "plant_name": "tomato",
      "flags": [
        {
          "kind": "dry",
          "severity": "high",
          "detail": "Only 1.6 mm of rain against 13.2 mm evapotranspiration over the past 7 days (12% of demand)."
        }
      ],
      "summary": "tomato: 1 stress signal(s) - dry (high).",
      "recommendations": [
        "Increase watering frequency; soil moisture is not keeping up with evapotranspiration."
      ]
    }
  ],
  "summary": "Checked 13 planting(s): 13 with stress signals, 0 clear."
}
```

Every diagnosis traces back to the weather numbers in its `detail`, so the
report can be checked against the forecast it used.

## Tools

| Tool | What it does |
| --- | --- |
| `log_planting` | Record a planting (name, variety, coordinates, date, notes) |
| `list_plantings` | List everything in the log |
| `log_observation` | Attach a dated field note to a planting |
| `list_observations` | Read notes back, all or per planting |
| `get_weather` | Daily past + forecast weather from Open-Meteo for a location |
| `diagnose_planting` | Look up a planting's coordinates, pull its weather, flag stress |

## Agent host

`GardenAgent` takes any connected MCP `ClientSession`, which keeps the host
honest: it can only do what the server's tools allow. A garden check chains
`list_plantings` into one `diagnose_planting` call per planting and aggregates
the results into a single report. In production it spawns the server over
stdio; in tests it runs in-memory against the same server object.

## Layout

```
src/garden_mcp/
  schemas.py      pydantic models: the checked I/O boundary for every tool
  db.py           SQLite planting log (plantings + observations)
  weather.py      Open-Meteo client (free, no API key)
  diagnostics.py  stress rules over the weather window
  server.py       FastMCP server exposing the tools
  agent.py        agent host that chains the tools
  seed.py         JSON import for garden data
  demo.py         end-to-end demo
tests/            pytest suite (Open-Meteo mocked with httpx.MockTransport)
.github/workflows/tests.yml
```

## Notes

- Open-Meteo is free for non-commercial use and needs no API key.
- Tests never touch the network; the live path is covered by the demo.
