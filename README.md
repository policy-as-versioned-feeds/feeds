# feeds

**Licence:** [Apache-2.0](LICENSE)

*A demonstration party, not affiliated with, endorsed by or speaking for any real authority it names.*

This repository publishes one feed, the threat register, in `threat-register/feed.json`.

## What the feed is

One row is one way a loss happens at a named party. A row gives:

- `events_a_year` and `loss_an_event`, each as `[lowest, most likely, highest]`, or `null` when nobody has a number.
- A basis for each: its kind (`editorial`, `published` or `counted`), a date and a sentence.
- The penalty regime and tier it draws, or `null`.
- `needs`: the capabilities (`egress` or `inbound`) that, once closed, close the row. Each need names its source. A row with no needs is a loss the cage cannot touch.

Overlapping rows are never summed. The feed prices nothing. The reader applies its own size.

The feed holds three rows, all for `driftwood`. The numbers are editorial or published, and none is counted. Each basis says so.

## How a change lands

1. Open a pull request that changes `threat-register/feed.json`. Change `version` in the same pull request.
2. The `test` job runs `test_feed.py` on the pull request. It checks the shape of every row.
3. The app approves and merges it from the orchestrator's session once `test` is green.
4. A tag `threat-register/v<version>` is signed with the workflow's own identity and pushed. `CUT_ON_MERGE` is `true`, so each merge that changes `version` cuts the tag. Dispatching `cut-release` does it by hand.
5. If the feed changes and `version` does not, the cut ends red. A tag never moves.

Readers pin a signed tag and its commit. In act mode, Driftwood follows a new tag by itself.

To run the tests: `python3 -m unittest -v test_feed`.
