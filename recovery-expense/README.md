# Prospective shadow recovery-expense cohort

`feeds/recovery-expense` is a separate major-1 family for nominal direct security-incident recovery expense per registered institution-year in GBP. Its model discriminator is `direct-security-recovery-expense/v1`, and its scope is `shadow-collection-only`. It does not replace an institutional threat/fine forecast or price a control. Platform composition excludes this exact family from ordinary prices, switching costs and financial dates, including before a report policy exists. Current threat envelopes and converter bytes remain unchanged.

No institution-year parameters, cost-centre identities, charge-out rates, envelope, signed release, registration or annual outcome are supplied here. The publisher must provide each institution's annual incident-frequency PERT triple, incremental GBP severity per incident, dated normative basis and exact cost-centre inventory. These are explicit unvalidated planning choices. They must not be inferred by summing overlapping workload contingencies or relabelling current threat/fine forecasts. The fixed released FAIR engine later produces the annual empirical distribution; PERT min/mode/max are not quantiles.

The standalone converter supports `forecast-base payload.json context.json` and `widen-to payload.json context.json`. Recovery `warn` and `deny` are identical: equality establishes no observed mitigation or effectiveness. The converter requires no sibling module or SDK dependency.

## Complete private candidate construction

Install `recovery-expense/requirements.txt` in an isolated environment. Help works without dependencies; a command missing validation instruments exits 3. Invalid inputs exit 1.

```
python3 recovery-expense/pilot.py bundle \
  --parameters /inputs/institution-model-parameters.json \
  --collection-policy /inputs/collection-policy.json \
  --contexts /inputs/actual-context-files-and-refs.json \
  --engine /inputs/exact-sdk-engine-ref.json \
  --discovery party.yaml --version 1.0.0 \
  --published-at ACTUAL-UTC-TIMESTAMP \
  --resolver-evidence-prefix https://github.com/policy-as-versioned-platform/platform/ \
  --output /new/private/unsigned-candidate
python3 recovery-expense/pilot.py check-bundle /new/private/unsigned-candidate
```

The output directory must not exist. Context inputs map each institution to its exact signed `party.yaml` source reference and corresponding local file. Its actual Git blob, party, reporting currency and one explicit recovery-expense major-1 selection must agree. Existing threat/fine selections may coexist. Construction checks structure and bytes; the NIST SDK remains the source/signature/history admission authority.

The bundle includes a matching payload schema, envelope, standalone converter, complete publisher discovery, 2027 case inventory, profile and collection policy. Discovery and envelope agree without manual repair. Context refs are explicit, and same-tree inventory refs use actual generated blobs. Unrelated publication declarations are conserved.

Model and profile bind the same canonical collection-policy digest. The platform collector uses that exact unit, cost-centre inventory and explicit labour charge-out rule. The profile names platform as separate resolver with `/amount`, `/final` and `/complete` pointers. Shared operator control and incident dependence must be disclosed; different publisher names do not prove organisational independence. Vendored NIST contracts are exact source-bound copies, including the unchanged engine descriptor and empirical CRPS criterion.

`widening_declaration` preserves scenario identity and frequency while doubling every recovery severity parameter. It requires an explicit release-cage reference and creates no native proof. It is publisher-owned full-target widening, never a consumer multiplier or evidence grade.

## Enrollment and honest release boundaries

A source change or private bundle is unsigned and unregistered. Genuine parameters and accounting identities must first be reviewed. Actual matching signed model/profile/context/engine sources must then pass the unchanged SDK admission checks. Each immutable forecast must be registered strictly before the 2027 horizon starts; never backdate. The exact named feed is supported by publisher release tooling, but no first-family predecessor exists until a genuine release exists. A native comparison without a predecessor remains unobserved; this software does not manufacture a passing cage. A later report/widening policy requiring a cage must satisfy that separate genuine gate.

The accepted bar is `-1000` with at least three final complete institutional cases: an operational error budget, not statistical confidence. Independent worklogs/invoices and year-end completeness/finality are required. A 30-day collection-process assessment, an empty ledger or software tests supplies no annual outcome, score, institutional price, runtime grade or cage credit.

Pure regressions: `python3 -B -m unittest discover -s recovery-expense -p test_pilot.py -v`. Synthetic parameters and source references are labelled test-only; no engine or signature verifier runs. The dedicated source workflow leaves existing native verification intact.

Recognition is by the actual expense-incurred UTC subject-year, including eligible carry-in recovery work, and excluding carry-out cost. Frequency counts incidents with eligible recovery activity inside that expense year; severity includes only their within-year eligible direct expense. Incident onset, payment and recording dates do not silently replace that recognition rule. No lifetime severity is compared to a partial-year ledger.
