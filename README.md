# bzr-step-count

`bzr-step-count` counts physical raw-diff step changes between two Bazaar
revisions by parsing `bzr diff -r FROM..TO` unified diff output.

```powershell
py -m pip install -e .
bzr-step-count --repo C:\path\to\repo --from 1000 --to 1100
bzr-step-count --repo . --from 1000 --to 1100 --format json --output report.json
```

The MVP counts only hunk lines: `+` as added and `-` as deleted. File headers,
Bazaar metadata, context lines, and `No newline` markers are not counted.
