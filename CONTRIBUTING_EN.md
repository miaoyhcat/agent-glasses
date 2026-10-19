# Contributing

[中文](CONTRIBUTING.md) · **English**

Changes are welcome around reproducibility, drivers, phone connectivity, task adapters,
mechanics, circuits and documentation. Read the [personal noncommercial license](LICENSE) and
the [commercial licensing terms](COMMERCIAL-LICENSE.md) first. Third-party material keeps its
original license; submit only what you have the right to provide.

- Say which concrete behaviour or design input the change affects, and attach the relevant
  files and a reproduction command.
- Run the related tests for code changes; the host regression entry is
  `python scripts/verify.py`. A text-only change does not justify claiming that hardware
  performance has been verified.
- For CAD or circuit changes, keep source files, generated outputs, BOMs and the corresponding
  check records in sync.
- Label parameters, tests, calculations and vendor specifications by their original evidence,
  and never put battery life measured under different loads into one ranking.
- Do not commit API keys, pairing tokens, debug private keys, personal recordings, cached media
  or private project source files.

For a defect report, include the version, OS, device configuration, steps to reproduce and
logs with sensitive information removed; for a feature request, describe the user scenario and
how it should be accepted. Commercial manufacturing, integration and licensing:
3277681859@qq.com.
