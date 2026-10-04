# Lifecycle State Machine

Seven states, eight legal directed edges (spec §7.2):

| From       | To         |
|------------|------------|
| RECEIVED   | STAGED     |
| STAGED     | STORED     |
| STORED     | ACTIVATED  |
| ACTIVATED  | REPLAYED   |
| ACTIVATED  | RELEASED   |
| REPLAYED   | RELEASED   |
| RELEASED   | ACTIVATED  |
| RELEASED   | RETIRED    |

`RETIRED` is terminal. Every other pair is rejected with
`ILLEGAL_LIFECYCLE_TRANSITION`.
