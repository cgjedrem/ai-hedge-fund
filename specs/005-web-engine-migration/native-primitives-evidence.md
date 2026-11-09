# Native primitive evidence — T022

## Result

**T022 PASS — Windows/NTFS host and Linux/ext4 runtime verified.** Both matrix
executions passed against the same immutable source snapshot. This closes only the
native primitive row; it does not pass T021 writer integration, runner lifecycle,
full-suite, or migration acceptance.

If either supported native runtime is missing, the corresponding row is **BLOCKED**.
If any primitive assertion fails, host mutation acceptance remains blocked and
mutation capability must stay denied. No failure or missing-runtime pass-through is
permitted.

## Source and artifact identity

- Git HEAD: `1acbf4623686c90a04aba95099dc4fe5fe14db34`.
- Source snapshot: 226 files from `hedge_fund/` and `pyproject.toml`, plus both new
  native test files; tar SHA-256
  `00a9d54e659d650e708979f27b6406d7f23887d7cb7091a6c1017d7dfd698e5b`,
  **2,846,720 bytes**.
- Sorted path/SHA-256 source-manifest identity:
  `81463eef1da9302a676218ea7b8f8340d015cf4ff3476d4e9bff474922ac2cc4`.
- Windows imported package from the extracted archive at
  `outputs/spec005-native-evidence-09bb55567c9a47ab923b26be271c1cb2/windows-src/src/hedge_fund/__init__.py`.
- Linux extracted the same archive onto the test-owned ext4 volume before testing.
- No wheel or application binary was built. Windows used the isolated project Python;
  Linux used the identified local pytest image. The source archive was removed after
  both runs; its hash and manifest identify the tested artifact.
- The checkout was dirty from parallel work. The snapshot includes the exact captured
  versions; this task did not edit admission, handover, root, or ownership source.

SHA-256 of direct test sources and runtime dependencies:

| File | SHA-256 |
|---|---|
| `hedge_fund/runtime/test_native_primitives.py` | `75921c563cfb0cb98dd3662f529e1e48239bda849c687de24ac668017aa7abac` |
| `hedge_fund/runtime/test_native_credentials.py` | `ae181c6070f1d3d572a4289b0d0a613814e89ed7c772acf7244c9708e22f7bec` |
| `hedge_fund/runtime/root.py` | `16518441140d73657fa7c06399a77b08d581fec3593613205759a85815956f30` |
| `hedge_fund/runtime/ownership.py` | `25636b43652f2129dc29c7c5b60b33fd275cf4da7211e9b5918e84fd93775196` |
| `hedge_fund/runtime/admission.py` | `2af13b9c65f7ecc5cfc9e2e6190edad9b143218becd24533151f71b67f19d03a` |
| `hedge_fund/runtime/handover.py` | `30d1d64863ba4cddb2680eecc0df2c963475c08267b8a491d5ee126be911a008` |
| `hedge_fund/runtime/credentials.py` | `e440b364546582179fe9bfc72710caa0290f0c93d0c2644570fbc4d6a1a7d17d` |
| `hedge_fund/runtime/capture.py` | `abf3116d867182187f045fc9469e5fce35c722b6d70d6a130be074e5b820fa62` |
| `hedge_fund/runtime/configuration.py` | `9cd572303e73990c28ab29e11ccfac9d86322a5a020d64d1ffe2288e9645a31b` |
| `hedge_fund/conftest.py` | `f1539e3ba25cb39c3cf1d862f563ac10151c863aa08622469ebb492455b2197b` |
| `hedge_fund/test_support/network_guard.py` | `96a0849a06c2c5df3d6f957e3d255ec17e8c6246fc2661b5d7c60af3d96beac1` |
| `pyproject.toml` | `290da1b1d4532be9346d2278c7109460245fc696367be6b93636e917d67076ee` |

## Windows / NTFS

- Environment: Windows 11 Enterprise `10.0.26200`, build `26200`; `C:` filesystem
  `NTFS`; Python `3.13.7`; pytest `7.4.4`; PowerShell `5.1`; x64 host.
- ACL tooling check: `powershell.exe` and `icacls.exe` present;
  `win32security` unavailable. Credential ACL assertions use PowerShell
  `Get-Acl`; no POSIX mode result is used as ACL evidence.
- Fixture: `outputs/spec005-native-windows-root-09bb55567c9a47ab923b26be271c1cb2`,
  test-owned and removed after execution. `hedge_fund/conftest.py` isolates test
  HOME/TEMP/root/credentials/network; `PYTHON_DOTENV_DISABLED=1`.
- Start/end: `2026-11-01T18:33:03.0839685+01:00` /
  `2026-11-01T18:33:25.6397182+01:00`.
- Exact test command from extracted source root:

  ```powershell
  $env:PYTHON_DOTENV_DISABLED='1'
  $env:AIHF_NATIVE_TEST_ROOT_BASE='outputs\spec005-native-windows-root-09bb55567c9a47ab923b26be271c1cb2'
  & outputs\spec005-poetry-envs\aihf-DI2Co9qP-py3.13\Scripts\python.exe -m pytest hedge_fund\runtime\test_native_primitives.py hedge_fund\runtime\test_native_credentials.py -q -p no:cacheprovider
  ```

- Result: **10 passed, 3 skipped in 17.62 s**, exit `0`. Skips are Linux-only
  filesystem/mode checks. The Windows NTFS identity, lock, atomic replace,
  incarnation, ACL, and inheritance checks ran.

## Linux / ext4

- Environment: Docker Desktop server `29.9.2`, `linux/amd64`; image
  `aihf-qa2-pytest:d054b3ae`, ID
  `sha256:f46586c33e835ed3ecf57a9b3199396d0301571007955c87cf69905ac4e67412`;
  Python `3.13.18`; pytest `7.4.4`.
- Kernel: `6.6.87.2-microsoft-standard-WSL2`. This is ext4 on a WSL2 Linux kernel
  inside the Docker Desktop VM, **not a bare-metal Linux host**.
- Filesystem: `df -T /work/native-tests /work/src` reported `/dev/sdd`, `ext4`,
  mounted at `/work`. Both the test root and copied source were on that volume,
  not a Windows bind mount.
- User: `uid=1000 gid=1000 groups=1000`; not root. `USER=spec005-native` and
  `LOGNAME=spec005-native` satisfy the image's Python `getpass` setup; mode checks
  still run as UID 1000. Network disabled.
- Owned volume: `aihf-spec005-native-09bb55567c9a47ab923b26be271c1cb2`,
  label `aihf.test-owned=spec005-turbo`. Removed by exact name; subsequent
  `docker volume inspect` returned no volume. The transfer/snapshot directory was
  also removed.
- Start/end: `2026-11-01T18:33:34.2210757+01:00` /
  `2026-11-01T18:33:44.6072909+01:00`.
- Exact test command:

  ```sh
  docker run --rm --network none --entrypoint sh --user 1000:1000 \
    -v aihf-spec005-native-09bb55567c9a47ab923b26be271c1cb2:/work \
    aihf-qa2-pytest:d054b3ae \
    -c 'set -eu; cd /work/src; export PYTHON_DOTENV_DISABLED=1 AIHF_NATIVE_TEST_ROOT_BASE=/work/native-tests USER=spec005-native LOGNAME=spec005-native; date -Ins; uname -r; df -T /work/native-tests /work/src; id; python --version; python -m pytest --version; python -m pytest hedge_fund/runtime/test_native_primitives.py hedge_fund/runtime/test_native_credentials.py -q -p no:cacheprovider'
  ```

- Result: **9 passed, 4 skipped in 5.75 s**, exit `0`. Skips are Windows-only
  NTFS/ACL checks. The Linux ext4 identity, lock, atomic replace, incarnation,
  permission, version, and capture checks ran.

## Scenarios and limits

- File identity: NTFS `st_dev/st_ino` and ext4 `st_dev/st_ino` remain stable over
  rename; atomic replacement yields a distinct file identity and replacement bytes.
- Cross-process lock: parent holds registry lane; owned child obtains root ownership
  then observes registry conflict. Child records `blocked`, not `acquired`.
- Atomic read/replace: owned child uses `RootContext.read_bytes` while parent performs
  120 alternating replacements (64 KiB / 96 KiB). Every observed value is complete
  old or new payload.
- Adjacent NTFS state: plain Python `open()` without delete sharing blocks replace
  with `PermissionError`; original bytes remain, no temp remains, and replace succeeds
  after reader close. Native `RootContext` readers permit delete sharing. This is an
  observed NTFS sharing boundary, not a partial-write result.
- Root handle: NTFS denies directory rename while handle is open; ext4 permits rename,
  after which the context rejects a replacement directory by identity.
- Process incarnation: owned child identity matches only while it lives; altered
  start-time identity fails; exited child no longer matches. Windows checks native
  process creation time/host identity. Linux checks `/proc` start ticks, boot ID, and
  PID namespace identity.
- The first Linux invocation ran UID 1000 without `USER`/`LOGNAME`; pytest fixture
  setup reported **9 errors, 3 skipped in 1.49 s** because the image has no passwd
  entry for UID 1000. No assertion ran. Adding test-only `USER`/`LOGNAME` fixed setup;
  final non-root result above passed. No source was changed for this environment issue.
- An early Windows experiment with a plain Python file reader produced `WinError 32`
  on replace. That adjacent case is now an explicit expected-denial/preserve-state test;
  cooperating application readers use `RootContext` and pass the atomic-reader test.
- No `os.kill` call, provider call, broker call, network call, or unrelated process/
  container operation was used.

Evidence type: native runtime observation plus automated tests. Execution owner:
Python Developer session. Console summaries and environment output are retained in
the task execution transcript; no standalone test log was created.
