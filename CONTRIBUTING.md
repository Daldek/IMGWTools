# Contributing to IMGWTools

Thanks for your interest in improving IMGWTools! Contributions of all kinds —
bug reports, fixes, features, and documentation — are welcome.

## Getting started

```bash
# Install the locked development environment (uv: https://docs.astral.sh/uv/)
uv sync --locked

# Run the gate before opening a pull request: ruff, mypy, tests with coverage
# and the commit check (contributors keep their own identity, so skip the
# author check)
GATE_CHECK_AUTHOR=0 scripts/gate.sh
```

Please keep pull requests focused, follow the existing code style, and use
[Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## Contributor License Agreement (CLA)

Before your first contribution can be merged, we ask you to sign our
**Contributor License Agreement**. In plain terms:

- **What it is.** A short agreement in which you confirm that you wrote (or have
  the right to submit) your contribution, and that you grant the necessary rights
  to use and redistribute it. The full text is in [`docs/CLA.md`](docs/CLA.md).

- **Why it is required.** It keeps the project's licensing on solid legal footing
  and preserves the option to relicense in the future if that ever becomes
  necessary. Without it, a single contribution with unclear rights could block
  such a change for everyone.

- **Your contribution stays MIT.** Signing the CLA does **not** change the
  licence. The project is and remains distributed under the [MIT Licence](LICENSE),
  and so is your contribution.

- **Signing is one comment — the process is manual.** There is no bot and no
  form. When your pull request is ready, add a comment on it with exactly this
  text:

  > I have read the CLA document and hereby sign it.

  When the maintainer merges your pull request, they record your signature —
  your GitHub handle, the date, and the pull-request number — in
  [`CONTRIBUTORS.md`](CONTRIBUTORS.md). You only have to sign once; it also covers
  your future contributions.

Please also tick the CLA box in the pull-request template.

## Reporting issues

Found a bug or have a feature idea? Please open an issue at
<https://github.com/Daldek/IMGWTools/issues> with as much detail as you can
(steps to reproduce, expected vs. actual behaviour, environment).
