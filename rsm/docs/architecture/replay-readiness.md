# Replay Readiness

Replay readiness is a **derived property**, not a lifecycle state (spec §11).

| Lifecycle state                        | Classification       | Replayability          |
|----------------------------------------|----------------------|------------------------|
| `RETIRED`                              | any                  | `NOT_REPLAYABLE`       |
| `RECEIVED`, `STAGED`                   | any                  | `NOT_YET_REPLAYABLE`   |
| `RELEASED`                             | `READY_EXECUTION`    | `REPLAY_BUILDABLE`     |
| `STORED`, `ACTIVATED`, `REPLAYED`, `RELEASED` (other classifications) | any | `REPLAYABLE` |

The replay envelope (`rsm.replay.envelope.build_replay_envelope`) is the single
canonical shape every transport returns for replay (spec §14).
