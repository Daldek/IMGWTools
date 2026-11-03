"""
MCP adapter of Obserwator: the command catalog for AI agents (extra ``obserwator[mcp]``).

The fourth adapter of the catalog, next to the CLI, REST and the web GUI (ADR-004
D6–D9, spec 2026-10-19 §6). Every catalog command is an MCP tool named
``x-obserwator.operation_id`` with the command's JSON Schema; `validate_command`
normalizes the arguments, the result is the ``obserwator-result/1`` envelope and an
error is the CLI error document with a title. Without writes (the default) a
writing command returns its ``obserwator-plan/1`` plan.

`obserwator.mcp.server` builds the server (`create_server`), serves it over stdio
(`run_stdio`, ``obserwator mcp``) and as the Streamable HTTP application of ``obserwator
server`` (`http_app`, ``/mcp``). Importing this package does not import the SDK.
"""
