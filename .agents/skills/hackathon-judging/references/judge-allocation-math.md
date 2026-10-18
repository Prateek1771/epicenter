# Judge allocation math

Everything here is arithmetic over four quantities derived from per-team timing inputs, each labelled where it is used.

## Contents

- The four quantities
- Published timing inputs and what they do not cover
- The three formulas
- Band boundaries computed
- Worked allocation maps
- The triage round
- What this math does not decide

## The four quantities

| Symbol | Quantity                                                    | Where it comes from           |
| ------ | ----------------------------------------------------------- | ----------------------------- |
| `N`    | number of teams expected to submit                          | interview Q3                  |
| `t`    | minutes of judge time consumed per team, including the swap | the demo format, interview Q1 |
| `W`    | minutes between submission close and ceremony start         | interview Q3                  |
| `J`    | confirmed judges                                            | interview Q4                  |

`t` is judge time, not team time. A team demoing for three minutes still costs a judge the walk, the notes and the handoff.

## Published timing inputs and what they do not cover

**10 minutes per team**, broken down as 3 minutes demo, 1-2 minutes Q&A, and 5-6 minutes setup and swap (from MLH organizer guide). Setup and swap consume more than half the slot, which is the guide's own point in publishing the breakdown.

Scope limit, stated because the figure is doing a lot of work here: MLH gives this for live demo slots at a closing ceremony, not for a judging round.

- What carries over: the setup/swap tax, since a team plugging in and swapping out is the same physical handoff either way.
- What does not: the audience (a ceremony slot holds a room, a judging slot does not), so a stage-pitch judging block can legitimately run tighter than 10 minutes.

**MLH's judging-round formula publishes a fourth, more precise anchor, for the round itself rather than the ceremony.** Its guide gives `J = ⌈(P × n × t) / T⌉`, where `n` is "Number of Judges for each project (or number of rounds of judging per project)" and `t` is minutes per project per judge. The guide's own defaults: `n` = **3 rounds per project** ("the goal is to have each project seen at least 3 times"), `t` = **4 minutes per project** (2 minutes presentation and demo, 1 minute questions and score compilation, 1 minute judge travel). This is a named-source answer to the judges-per-project question this page's `k` otherwise derives from first principles - `J = ⌈(P × n × t) / T⌉` and this page's `k ≤ (J × W) / (N × t)` are the same relationship solved for opposite variables. The guide's own worked example (175 projects, 2-hour window) solves to 18 judges, and it publishes a full attendees-by-window lookup table built on the same formula.

From hackathon practitioner write-ups:

- **3-5 minutes per team** at an Expo Table.
- **2-5 minutes plus Q&A** at a Stage Pitch.

These figures cover demo and Q&A time only, with no setup or swap allowance folded in, which if anything makes the gap wider.

Every ceiling computed from them is therefore an optimistic upper bound: real expo judging spends walking time and note-writing time the figure ignores. Present those ceilings with that caveat attached, not as a capacity promise.

Every `k` below is computed from these timing inputs rather than observed at a real event.

## The three formulas

**Full coverage ceiling.** Every judge sees every team, so every judge personally traverses all `N` teams:

```
N × t ≤ W        →        N ≤ W / t
```

`J` does not appear. Adding judges cannot extend full coverage, because each added judge still has to make the same complete traversal. This is the single most useful result on the page and the one organizers most often get wrong.

**Coverage per team under a sampled panel.** Split `J` judges into panels covering disjoint slices of the field.

- Total available judge-minutes: `J × W`.
- Total demanded judge-minutes: `N × t × k`, for `k` judges per team.

```
k ≤ (J × W) / (N × t)
```

Read the units out loud when presenting it: judge-minutes available, divided by team-minutes demanded, gives judges per team. Take the floor (a team seen by 2.6 judges is seen by 2).

Full coverage is the special case `k = J`, which reduces to `N ≤ W / t` exactly as above.

**Triage threshold.** Set `k = 1`:

```
N > (J × W) / t     →     not even one judge reaches every team
```

Past this point no allocation of the confirmed judges works inside the window. The field must be cut before judges see it, or judging must leave the live window entirely.

## Band boundaries computed

Full coverage ceiling `W / t`, in teams:

| `W` (window) | `t` = 10 min (MLH figure) | `t` = 5 min (optimistic) | `t` = 3 min (optimistic) |
| ------------ | ------------------------- | ------------------------ | ------------------------ |
| 60 min       | 6 teams                   | 12 teams                 | 20 teams                 |
| 90 min       | 9 teams                   | 18 teams                 | 30 teams                 |
| 120 min      | 12 teams                  | 24 teams                 | 40 teams                 |
| 180 min      | 18 teams                  | 36 teams                 | 60 teams                 |

The `t` = 10 and `t` = 5 columns differ by a factor of two, and the quantity that doubles is **the number of teams full coverage reaches for a given window**. It is not a doubling of judges, of judge-hours, or of the window itself.

Triage threshold `(J × W) / t`, in teams, at `W` = 120 minutes:

| `J` (judges) | `t` = 10 min | `t` = 5 min |
| ------------ | ------------ | ----------- |
| 6            | 72 teams     | 144 teams   |
| 12           | 144 teams    | 288 teams   |
| 20           | 240 teams    | 480 teams   |

Above those counts, a live judging window cannot give every team even one judge.

## Worked allocation maps

**Example A - Band 1, full coverage** 10 teams, expo table at `t` = 5, `W` = 120, `J` = 4.
`W / t` = 24 ≥ 10, so full coverage fits with room. All four judges walk the same ten tables, `k` = 4. No allocation map is needed beyond a start order, which is why full coverage wins efficiency in this band: the map itself is the cost the other rungs pay.

**Example B - Band 2, sampled panel** 60 teams, expo table at `t` = 5, `W` = 120, `J` = 12.
`W / t` = 24 < 60, so full coverage is impossible. `k ≤ (12 × 120) / (60 × 5)` = `1440 / 300` = 4.8, so `k` = **4 judges per team**.

Split the 12 judges into three panels of four. Each panel takes 20 teams and spends 100 of its 120 minutes visiting them. The 20-minute remainder is the buffer that absorbs a team that is not at its table.

Present the map as a table with one row per judge: judge name, panel, team list in visiting order, start time. A judge without a written list improvises, and improvisation is how a team ends up unvisited.

**Example C - Band 3, triage** 200 teams, expo table at `t` = 5, `W` = 120, `J` = 8.
`(J × W) / t` = `(8 × 120) / 5` = 192 < 200. Even `k` = 1 does not fit.

Either cut the field before judges see it, or move judging out of the live window. Moving judging out of the live window is a format decision that belongs to `samber/dev-event-organizer-skills@event-format-selection`, not to this math.

**Example D - Stage pitch, the tight case** 30 teams, stage pitch at MLH's `t` = 10, `W` = 120, `J` = 5.
`W / t` = 12 < 30. Note what does _not_ help: at a stage pitch the whole panel sits together and teams present serially, so the panel advances as one unit and `k` = `J` = 5 whether you like it or not. The only levers are:

- Cutting `N` with a pre-screen.
- Cutting `t` by shortening the slot.
- Extending `W`.
- Running two parallel stages (a format change, not an allocation change).

## The triage round

Only reach for this in Band 3, or in Band 2 when interview Q8 confirms a volunteer crew exists.

- Round one is a **pass/fail gate**, never a score. Volunteers or organizers check the published submission requirements:
  - does it run
  - does it meet the brief's deliverable format
  - is it eligible

  A gate is defensible without judging expertise; a score is not.

- Publish the gate's criteria in the brief before submissions close, with the fact that a pre-screen exists. A cut round teams did not know about is the most contestable thing on this page.
- Round two gives finalists full coverage. Size the finalist count from `W₂ / t` on the _remaining_ window, not the original one (the pre-screen consumed part of `W`).
- Record which teams were cut and on which failed requirement. That record is what answers the challenge that follows.

## What this math does not decide

It gives feasibility, not quality. It says nothing about which judges should see which teams beyond disjointness, and a panel built without regard to judge type will give a track full of infrastructure projects to three business judges. Compose each panel against judge type (technical judges want to touch the demo, business judges want the narrative) before fixing the map.

It also assumes teams are present and ready. Every band above holds a buffer for the ones that are not; a plan that spends 100% of `W` has no room for the first no-show.
