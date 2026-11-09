"""Garden diagnostic agent: an MCP server plus an agent host.

The server exposes Open-Meteo weather lookups and a SQLite planting log as
MCP tools with schema-checked inputs and outputs. The agent host connects to
the server over MCP and chains those tools to produce garden check reports.
"""

__version__ = "0.1.0"
