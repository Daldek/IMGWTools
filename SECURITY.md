# Security policy

## Supported versions

Security fixes go into the latest release of Obserwator (and the development branch
`develop`). Older releases are not patched.

## Reporting a vulnerability

Please do not report vulnerabilities in public issues or pull requests.

Use GitHub's private vulnerability reporting: open the **Security** tab of
<https://github.com/Daldek/Obserwator>, choose **Report a vulnerability** and describe
the problem, the affected version and, if possible, how to reproduce it. You get an
answer as soon as the maintainer can read the report; a fix is released as a patch
version and credited in the CHANGELOG unless you prefer otherwise.

## Scope

Obserwator downloads public data from IMGW-PIB and ČHMÚ and writes it to local files or a
versioned store. Reports about the following are in scope:

- the REST server (`obserwator server`, `/api/v1`, the web GUI), including the store write
  routes and their API key (`OBSERWATOR_STORE_WRITES_ENABLED`,
  `OBSERWATOR_STORE_WRITE_TOKEN`, header `X-API-Key`) and the server's API keys file;
- the MCP server (`obserwator mcp` over stdio and `/mcp` of the REST server), including
  the sandbox of writes (`--allow-writes`, `--allow-dir`): any write or path outside the
  allowed directories;
- writes to the store and to output files: path traversal, overwriting files outside the
  target, corruption of committed versions;
- unsafe parsing of downloaded archives (ZIP, CSV, JSON) and of store files;
- the supply chain of the package.

Problems of the IMGW-PIB or ČHMÚ services themselves are out of scope; report them to the
institute.
