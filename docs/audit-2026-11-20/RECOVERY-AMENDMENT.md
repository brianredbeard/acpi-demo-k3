# Recovery amendment: integration commit 9b95f32

This amendment incorporates `1a9d958` (operating rules) and `9b95f32db905b47650b331c154c378dd2bc04aee` (v26 recovery). The latter is committed on November 20 at 18:04 -0800; its recovery cycle and post-mortem are labelled November 21. The original audit's `d3daf37` measurements remain historical evidence. **Release remains HOLD, while the deployed board is reported recovered.** No board commands, builds, flashes, resets or implementation changes were made for this amendment.

## Three distinct states

| State | Current evidence | Interpretation |
|---|---|---|
| Original audited source | d3daf37, twelve EDK2 patches and seven ESOS patches | Retained inventories and binary/AML tests describe this snapshot, not the recovered ESOS |
| Current integration source | 9b95f32; ESOS patch0007 changed, manifest unchanged | Manifest validation now FAILS; a fresh supported ESOS preparation cannot validate these inputs |
| Reported recovered board | v12 ESOS + v21g OpenSBI + v19 EDK2 with UFS0/_LPI | Team reports clocks and bounded recovery checks working; P1 ESOS ownership/sequencer/policy work is not deployed |

The maintained EDK2 source remains clean at `a2a647a5`. No EDK2 patch, ACPI source or platform pin changed between the integration audit baseline and this commit. Consequently the existing AML defects, PCI/runtime findings and locked-versus-maintained namespace distinction remain open. No unrelated defect is closed by a rollback.

## Recovery evidence and its limits

The committed post-mortem reports 17 clock entries, `ufs_aclk` at 491.52 MHz, zero UFS clock-fallback warnings, P0 results -1/-2/-3/-2, type-0 result0, live `_LPI`, UFS673 MB/s, no lockups and a clean reboot. These are **team-reported hardware results**, not tests executed by this audit. Raw v26 boot/clock/test output was not present in the inspected recovery bundle or committed post-mortem. The full regression procedures in regression.csv have not thereby all passed.

The local `/tmp/pico-acpi-v26` bundle exists. All **20 manifest entries** (five payloads and fifteen provenance files) were hashed and match. Retained copies of the manifest and v26 recovery description are under `evidence/recovery-amendment/`; full firmware binaries were not duplicated. Payload SHA256:

- ESOS FIT: `37533b27df72792152d01cff949e170d26946ab98e4b4128edd0532ff82b8fc4`
- OpenSBI region: `537d30d776e385e4bed87e2f4cbeaa5cd3a2dd781dfa3e3b2632a364928a2293`
- EDK2: `5a148ed6cba479ede2944764c2478f4fb5a919fe3c989c57b7727e527e06e4bb`

The shortened `2f14c5c8` OpenSBI identity in the recovery description refers to the inner qualified firmware binary; it must not be compared directly with the region/FIT hash above. Bundle hash agreement does not prove flash contents. Older provenance files copied into the bundle retain their older qualification scope.

The reported 17 entries are not a replacement inventory for the original source's 13 RPMI IDs. Capture full names, IDs and consumer lookups before reconciling counts. In particular zero UFS fallback warnings supports the recovered UFS path; it does not resolve GPIO/Ethernet/thermal consumer-name mismatches or cross-agent ownership.

The recovery description also makes an essential distinction: v12 ESOS lacks the rcpu DT advertised type for the experimental `0x11000000` route, so an unsupported result can occur **before** any P1 gate. A denial or unsupported response plus successful UFS I/O is not proof the ownership gate or clock service ran.

## Corrected incident interpretation

The latest post-mortem supersedes the earlier explanation that v24 would restore clocks by applying missing patches or changing the hand-build path. It reports that the clock service was already broken in v20–v23 and that earlier green checks exercised deny/UFS without checking clocks. Recovery by replacing ESOS makes the P1 ESOS composition the leading suspect; the specific registration hunk/root cause is still unidentified. This audit does not independently prove that every earlier cycle had identical failure or that registration is the final root cause.

Continue using `build_esos.py` as AGENTS.md requires. The newer incident evidence does **not** show that the wrapper alone prevents the clock regression. AGENTS.md's older v24/v25b diagnostic matrix and “working v20” language are superseded for incident interpretation by the later recovery report. Likewise its service-idempotency assertion does not close CLK-05 without a complete service-path test.

## Fresh source/test findings

**REL-03 — P1, confirmed, high confidence:** current patch0007 hashes to `6c4bcf3ce26866ba21ce8a2c746876ebe5172f4bb3149cb7c0783cdc88abe897`; sources.lock.json still expects `7ebfbd2466b7350348d155b7b7a02ffdab75df73e5fba4cabe6814ea08394961`. `python3 meta.py validate` exits1. The repository suite runs17 tests with2 errors from this mismatch. These supersede the original PASS for current HEAD, without changing historical logs. Reconcile the intended patch with the lock after review; merely updating the hash does not qualify its contents.

**REL-04 — P1, confirmed validation gap, high confidence:** `tests/test_k3_domain_ownership.py:build_fixture` reuses `.p1-test-lock-source` when its C file exists, without checking current patch bytes. The cached manifest expects the old patch hash and has the same manifest hash as current HEAD because the manifest was not updated. An ownership-test pass against this cache does not validate current patch0007. Cache invalidation must depend on verified actual inputs; a manifest hash alone is insufficient when validation is bypassed. No shared fixture was deleted or modified by this amendment.

**CLK-07 — P1, reported hardware regression, recovery reported:** P1 ESOS composition loses clock service while narrower deny/UFS tests can pass. Current deployment avoids it by rollback; re-landing remains blocked until the causative change is isolated and every intermediate image preserves clock enumeration, rates and consumer acquisition. This is not evidence that the existing clock-policy/ownership implementation is now qualified.

The current patch also visibly differs from the “audit-fixed sequencer” description: it restores a100ms `k3_domain_request_sleep` call at patch line502 and lacks the later `k3_domain_hw_ops`/qualification interfaces. AGENTS.md records a20ms RX bound. Treat these as explicit re-review items in the candidate patch, not proof the recovered board runs them. The previously committed fuller implementation remains in Git history. Historical clock inventories are still valid for the original audited declaration set, but do not certify the current entire ESOS series.

## Qualification changes

Before re-landing any P1 change: verify current manifest and a fresh ownership fixture; use build_esos.py; commit and inspect the exact bundle; change one payload/feature per cycle. The first post-boot gate is actual clock-provider readiness, complete clock names/rates and UFS clock acquisition with no fallback. Then run the intended feature plus the established boot/idle/UFS/reset checks. Retain raw output and image hashes for every cycle. A failed clock gate stops promotion even if UFS throughput remains good.

The original54 regression procedures remain scoped as written. Their observations now link relevant recovery reports. REG-55 adds the missing clock-service promotion gate; REG-56 adds source/fixture identity validation. Neither is marked passed merely from the earlier limited recovery summary. `recovery-results.csv` records each reported result separately from independently checked artifact evidence.
