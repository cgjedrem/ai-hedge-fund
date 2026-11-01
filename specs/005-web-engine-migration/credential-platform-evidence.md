# Credential platform evidence — T059

## Result

**T059 PASS — native Windows ACL and Linux/ext4 mode, atomic-version, and private
capture checks passed.** Windows ACL evidence is separate from Linux permission-bit
evidence; no POSIX mode was substituted for Windows ACL proof.

The tested `credentials.py` implementation provides root-private storage and
versioned writes. These results close only T059's native acceptance row; they do not
mark every T050 workflow or overall US2/migration acceptance complete.

## Source and test artifact

Both platforms ran the same immutable source archive and Git base:

- HEAD: `1acbf4623686c90a04aba95099dc4fe5fe14db34`.
- Archive SHA-256:
  `00a9d54e659d650e708979f27b6406d7f23887d7cb7091a6c1017d7dfd698e5b`
  (**2,846,720 bytes**, 226 source files).
- Sorted path/file-hash manifest SHA-256:
  `81463eef1da9302a676218ea7b8f8340d015cf4ff3476d4e9bff474922ac2cc4`.
- Test source hashes: `test_native_credentials.py`
  `ae181c6070f1d3d572a4289b0d0a613814e89ed7c772acf7244c9708e22f7bec`;
  `test_native_primitives.py`
  `75921c563cfb0cb98dd3662f529e1e48239bda849c687de24ac668017aa7abac`.
- Direct runtime/harness dependency hashes are listed in
  [native-primitives-evidence.md](native-primitives-evidence.md).
- No application wheel/binary was built. Windows used the extracted source tree
  with the isolated project interpreter. Linux used the same archive on a named
  ext4 Docker volume with the image ID recorded below.

## Windows / NTFS ACL

- Environment and run identity: Windows 11 Enterprise `10.0.26200`, build `26200`;
  C: `NTFS`; Python `3.13.7`; pytest `7.4.4`.
- Tool discovery before declaring any limitation: `powershell.exe` and `icacls.exe`
  present; Python `win32security` absent. The native test inspects ACL owner and
  inheritance using PowerShell `Get-Acl`; absence of `win32security` is not a block.
- Fixture: test-owned NTFS root under
  `outputs/spec005-native-windows-root-09bb55567c9a47ab923b26be271c1cb2`, removed
  after test.
- Start/end: `2026-11-01T18:33:03.0839685+01:00` /
  `2026-11-01T18:33:25.6397182+01:00`.
- Command, run from extracted source:

  ```powershell
  $env:PYTHON_DOTENV_DISABLED='1'
  $env:AIHF_NATIVE_TEST_ROOT_BASE='outputs\spec005-native-windows-root-09bb55567c9a47ab923b26be271c1cb2'
  & outputs\spec005-poetry-envs\aihf-DI2Co9qP-py3.13\Scripts\python.exe -m pytest hedge_fund\runtime\test_native_primitives.py hedge_fund\runtime\test_native_credentials.py -q -p no:cacheprovider
  ```

- Result: **10 passed, 3 skipped in 17.62 s**, exit `0`.
- Native ACL assertions: private root owner equals current process SID; DACL is
  protected and contains only current user, SYSTEM, and local Administrators with
  Allow/FullControl. Credential directory, provider directory, immutable credential
  version file, and atomic index file are owned by current user; each has the exact
  expected inherited principals, inherited Allow/FullControl rules, and no explicit
  child ACL. This is observed Windows security-descriptor evidence.

## Linux / ext4 modes and captures

- Runtime: Docker Desktop `29.9.2`, `linux/amd64`; image
  `aihf-qa2-pytest:d054b3ae`, ID
  `sha256:f46586c33e835ed3ecf57a9b3199396d0301571007955c87cf69905ac4e67412`;
  Python `3.13.18`; pytest `7.4.4`.
- Kernel `6.6.87.2-microsoft-standard-WSL2`; ext4 named volume in Docker Desktop VM
  on WSL2, not a bare-metal Linux host. `df -T` returned `/dev/sdd ext4` for both
  test source and native test root.
- Permission context: `uid=1000 gid=1000 groups=1000`, not root. Network disabled.
  `USER=spec005-native` / `LOGNAME=spec005-native` satisfy `getpass`; this does not
  elevate UID or bypass mode checks.
- Volume `aihf-spec005-native-09bb55567c9a47ab923b26be271c1cb2`, label
  `aihf.test-owned=spec005-turbo`; exact volume was removed and inspection confirmed
  it absent.
- Start/end: `2026-11-01T18:33:34.2210757+01:00` /
  `2026-11-01T18:33:44.6072909+01:00`.
- Command:

  ```sh
  docker run --rm --network none --entrypoint sh --user 1000:1000 \
    -v aihf-spec005-native-09bb55567c9a47ab923b26be271c1cb2:/work \
    aihf-qa2-pytest:d054b3ae \
    -c 'set -eu; cd /work/src; export PYTHON_DOTENV_DISABLED=1 AIHF_NATIVE_TEST_ROOT_BASE=/work/native-tests USER=spec005-native LOGNAME=spec005-native; date -Ins; uname -r; df -T /work/native-tests /work/src; id; python --version; python -m pytest --version; python -m pytest hedge_fund/runtime/test_native_primitives.py hedge_fund/runtime/test_native_credentials.py -q -p no:cacheprovider'
  ```

- Result: **9 passed, 4 skipped in 5.75 s**, exit `0`. Windows NTFS/ACL cases were
  skipped; Linux mode/version/capture cases ran.
- Mode assertions: private root, credential directory, provider directory, and
  persisted capture directory are current UID with mode `0700`; credential version,
  atomic index, and persisted capture files are current UID with mode `0600`.
- Atomic version scenario: an owned concurrent reader parsed each complete index
  while 40 compare-and-swap writes advanced version `1` through `41`; final status
  was `(41, configured=True)`.
- Capture scenario: capture persisted under root-private storage and round-tripped;
  its version handle contains root/provider/version only. Neither serialized
  private capture bytes nor public view contains credential material.

## Setup limitation and disposition

The first Linux invocation omitted `USER` and `LOGNAME`; the container image has no
passwd entry for UID 1000, so pytest fixture setup reported **9 errors, 3 skipped in
1.49 s** before test assertions. Retrying with those two test-only environment values
and the same non-root UID passed. No source behavior changed. The `win32security`
package was checked and absent, but native PowerShell ACL inspection was available and
passed, so Windows ACL proof is not blocked.

Evidence type: native platform observation plus automated tests. Execution owner:
Python Developer session. No provider/LLM/broker/network call. Console summaries and
ACL/mount metadata are retained in the task execution transcript; no standalone log
was created.
