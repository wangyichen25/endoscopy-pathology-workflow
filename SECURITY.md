# Privacy and security boundaries

This repository contains code, general clinical instructions, and fictional transport fixtures. It intentionally excludes clinical data, private validation results, institutional adapters, deployment addresses, authentication settings, and secret values. The demo checkerboard is generated locally and is not a patient image.

The software is not a de-identification or protected-information detection tool. Source reports, labels, filenames, identifiers, image pixels, metadata, model outputs, rationales, reviewer comments, and raw responses can contain sensitive information. Remove identifying content using independently validated processes and local governance before transmitting or sharing anything. A local anonymous identifier does not make the remaining record anonymous.

Network inference requires explicit `--allow-network` and an explicitly configured HTTPS endpoint/model/key. Review the endpoint's authorization, retention, logging, data location, and access controls. There is no automatic upload to a repository or telemetry service. Operating-system proxies and the selected provider can affect network handling; verify the complete deployment environment.

Keep runtime data outside the checkout in approved private storage. Restrictive file creation and ignore patterns reduce accidental inclusion but are not an access-control system or a privacy guarantee. Do not commit `.env`, keys, local configurations, reports, images, review CSVs, raw outputs, or internal adapters. Review every staged file and the full Git history before making a copy public. Never attach clinical records or secrets to public issues.

If a real secret is exposed, revoke it through the issuing system. If sensitive content is exposed, follow the applicable incident process and repository-host removal guidance; deleting the latest file does not remove earlier history or copies. Report code issues with a minimal synthetic reproduction only.
