# CI without external actions

## Decision

The workflow in `.github/workflows/ci.yml` uses no action at all, GitHub's own included. Every step is a `run:` script: checkout is `git init` and a depth-1 fetch of exactly the commit under test, with the token passed in a masked header for that one command and never written to `.git/config`; Python is an interpreter already in the runner's tool cache, used only to create the virtual environment each job then runs in. Each of Python 3.11 to 3.14 runs the gate, builds the wheel and sdist twice and compares the bytes, runs the gate inside the unpacked sdist and rebuilds an identical wheel from it, and installs the sdist, the directory, and an editable copy with the pip that ships inside that Python, offline. Nothing is downloaded; uv, which development uses locally, is not on the runner image and is not fetched.

Permissions start empty and the job reads contents only. The workflow runs on pull requests and pushes to `main` and on manual dispatch; never on `pull_request_target`, which would run fork code with a write token, and never with secrets. Every value from the event reaches a script through `env:`, never by interpolation into the script. While the repository is private, jobs are skipped unless dispatched by hand, so they cost no minutes. `tests/test_workflows.py` enforces each rule above that a text check can see.

## Alternative weighed

Use `actions/checkout` and `actions/setup-python`, pinned to commit hashes.

## Why the alternative lost

Pinning makes an action immutable but not small: each is thousands of lines of someone else's code running with the job's token on every build, and its dependencies are fetched at run time. The two jobs they do here, fetching one commit and pointing at an interpreter the image already holds, take twenty lines of shell that can be read in full. The cost is that a runner image without one of the four Python versions fails the job instead of downloading it, and the matrix then drops that version.
