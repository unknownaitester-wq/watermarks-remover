# Optional backend maintenance

The `v1.0.0` tag remains frozen. The normal file command remains:

```bash
python3 service/scripts/clean_file.py INPUT_FILE -o OUTPUT_FILE
```

Optional research backends are independent of that command. Before using one,
check its local checkout or package installation:

```bash
python3 service/scripts/check_backends.py
python3 service/scripts/check_backends.py --strict
```

The command prints JSON. `ready` means the expected Git commit and backend
files were found with a local virtual environment, or the pinned MarkDiffusion
package version was found. `absent` is normal for an unused backend; even
`--strict` ignores it. Other statuses identify a local setup problem. The
check is read only and does not load models or claim that detection or removal
will succeed. The service's `/health` and `/capabilities` endpoints remain the
runtime checks for its core tools.

`config/backend-compatibility.json` records the tested upstream commits and
MarkDiffusion package version. The setup scripts, Dockerfiles, and requirement
files are the installation sources; `tests/test_backend_compatibility.py`
checks that their pins agree with the record. Setup scripts fail if an existing
checkout is at a different commit, leaving it untouched.

## Regression checks

The repository already has small repeatable fixtures under `tests/fixtures`.
The core suite covers Unicode cleanup, Office metadata, C2PA, text detectors,
and file formats; optional backend tests use local stand ins so they do not
download models. Run before proposing a pin change:

```bash
python3 -m pytest -q tests/test_backend_compatibility.py tests/test_capabilities_tooling.py
python3 -m pytest -q
```

For changes to a research backend, also run its focused tests and a controlled
before/after sample with the same scheme, configuration, keys, and seed. Record
the upstream commit, dependency versions, commands, detector result, and
output quality. No local fixture or surrogate score proves a vendor detector
will fail.

## Upstream update process

1. Check upstream releases manually. Do not auto-upgrade the active setup.
2. Try a candidate in a separate checkout or branch. Update the relevant
   setup pin, image pin, requirements, and compatibility record together.
3. Run the regression checks and the backend's controlled sample. Keep the
   previous pin if setup, detection, or output quality regresses.
4. Review the change on a work branch before promoting it. Cut a release only
   when explicitly requested.

CtrlRegen and MarkDiffusion image regeneration remain experimental. In the
prior CtrlRegen batch, only 3 of 5 images cleared the reverse-SynthID
surrogate, and fidelity suffered. Keep an original image and inspect any
regenerated result before use.
