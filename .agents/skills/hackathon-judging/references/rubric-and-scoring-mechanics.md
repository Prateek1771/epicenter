# Rubric and scoring mechanics

## Contents

- Choosing the scale
- A capability ladder with negative rungs
- Weighting the brief's categories
- Worked rubric: single track
- Worked rubric: sponsor track alongside a general track
- The normalization arithmetic, worked
- A positive and a negative scoring pair
- Judge-type fit
- Using the worked examples

## Choosing the scale

Two scales have real precedent, both from conference talk review rather than from hackathon judging; each is built for a different room.

- **Multi-criteria numeric scale**, for judges who will never confer: five stars in half-star steps across named criteria (from KubeCon/CNCF reviewer guidelines). It measures comparability, which is what an aggregated cut needs. This is the shape that carries over cleanly to a hackathon, because judges scoring in parallel across a field they only partly saw is exactly the KubeCon situation.
- **Letter-grade advocate scale**, for a jury that will meet (from !!Con's published selection process):
  - A = will actively advocate
  - B = likes it but will not advocate
  - C = neutral
  - D = will advocate against
  - X = abstain, because the reviewer thinks they have recognized the submitter

  It measures advocacy, which is what a discussion round spends, and its X grade is the source's own conflict-of-interest mechanic - the same abstain-rather-than-score instinct the conflict ladder defaults to. It only makes sense paired with synchronous consensus, and consensus is the starved rung.

What does not carry over from either: both were applied to written proposals read at leisure. A judge holding a clipboard between two tables needs fewer steps than half-stars offer. Default to a 1-5 integer scale per criterion: five steps a judge can hold in their head, no arithmetic in the aisle.

Keep the number of criteria at or below four. KubeCon's rubric uses four:

- Content
- Originality
- Relevance
- The speaker(s): the suitability of whoever proposes to deliver it

Beyond that, the marginal criterion is scored from the same overall impression as the previous three, and it adds noise rather than resolution.

## A capability ladder with negative rungs

A 1-5 integer scale asks a judge for an opinion. A capability ladder asks a narrower question - which named rung does this project actually reach - and attaches a point delta to each rung, including a negative delta for the path that took the least effort. Use it on a criterion where the rubric should actively discourage the cheapest route, not merely fail to reward it.

Worked ladder for a criterion measuring technical depth:

| Rung                                    | Delta |
| --------------------------------------- | ----- |
| Simple chatbot with no added logic      | -5    |
| Simple prompting, no retrieval or tools | 0     |
| Retrieval-augmented                     | +2    |
| Agentic - tool use, function calling    | +5    |
| Fine-tuning                             | +10   |

A second ladder can score usability the same way:

| Rung                                       | Delta |
| ------------------------------------------ | ----- |
| Needs a developer present to run it at all | 0     |
| End-to-end usable by a novice with no help | +5    |
| Deployed and reachable online              | +8    |

Modifiers apply on top of whichever ladder rung a project reaches - each is a further delta, not a separate score: overly repetitive output (-2), response time too slow to demo comfortably (-2), the product requires the user to prompt it rather than presenting a complete interface (-2), the underlying technology is invisible to the end user (+3), a privacy violation in how the project handles data (-5).

**Normalize the raw ladder total to whatever fixed scale the published rubric uses**, with a cohort min-max pass: `(score - min) / (max - min) × top_of_scale`. Ladder totals are additive, open-ended and can go negative, so publishing the raw number to teams or a sponsor reads as arbitrary; the normalized figure is what appears on the sheet everyone sees.

Worked example, ladder scores for five teams before normalization: -3, 2, 7, 12, 15. Min is -3, max is 15, range 18. Normalizing to a 1-5 scale: team at -3 scores 1.0 exactly (the floor), team at 15 scores 5.0 exactly (the ceiling), team at 7 scores `(7 - (-3)) / 18 × 4 + 1 = 3.22`.

Only normalize within one cohort scored on the same ladder. A ladder built for one track's technical depth does not compare across a track that never used it.

## Weighting the brief's categories

The brief already named the categories (interview Q2). Weighting them is one decision, made once, before the event.

1. Write the categories down in the brief's own words. Do not rename them - teams optimized against the published wording.
2. Assign integer percentage weights summing to 100. Integers, because a judge or a sponsor reading the rubric should not have to parse a decimal.
3. Test the weights against the event's own purpose: if the highest weight is not on the thing the organizers would name as the point of the event, either the weights or the purpose statement is wrong.
4. Keep the exact weights internal by default. Publishing the category names (step 1) and the elimination list already satisfies disclosure - undisclosed _categories_, not undisclosed weights, are what score a competition nobody entered. Publish the weights too only where the event has a specific reason to prefer transparency over anti-gaming protection (a sponsor-track dispute that needs an auditable number, or a multi-edition event whose published rules already promise it).
5. Check the highest-weighted criterion is one a judge can actually observe in the slot. "Long-term commercial viability" cannot be seen in four minutes; "working demo" can.

## Worked rubric: single track

Invented illustration. Categories are the ones a general-purpose hackathon brief commonly names; the weights are the example's own.

| Criterion           | Weight | What the judge is looking for in the slot                            | Scale |
| ------------------- | ------ | -------------------------------------------------------------------- | ----- |
| Working demo        | 35%    | It runs, live, on the judge's request - not a recording, not a slide | 1-5   |
| Technical execution | 25%    | The hard part was actually built, not stubbed                        | 1-5   |
| Fit to the brief    | 25%    | It answers the challenge as published, not an adjacent problem       | 1-5   |
| Presentation        | 15%    | The team can say what it does in one sentence                        | 1-5   |

Weighted total = `Σ (score × weight)`, giving a 1-5 result on the same scale as its parts. The sheet computes it; the judge never does.

Why "working demo" carries the top weight in this example: it is the one criterion that is fully observable in the slot and fully verifiable on the spot, so it is also the one least likely to be contested afterwards. An event that genuinely rewards ambition over completion should invert this - and should say so in the brief, because teams will build to whichever it is.

## Worked rubric: sponsor track alongside a general track

Invented illustration. A team submits one project and may enter more than one track (from MLH's rules for hackathons, which state a team may submit its single project to multiple challenge tracks).

Run **two separate weighted totals over the same criteria**, not one blended score:

| Criterion                       | General-track weight | Sponsor-track weight |
| ------------------------------- | -------------------- | -------------------- |
| Working demo                    | 35%                  | 25%                  |
| Technical execution             | 25%                  | 20%                  |
| Fit to the brief                | 25%                  | 15%                  |
| Use of the sponsor's technology | 0%                   | 30%                  |
| Presentation                    | 15%                  | 10%                  |

The sponsor's criterion carries real weight in the sponsor's track and zero in the general one. This is what a sponsor bought and what the general track must be protected from: a general-track winner chosen partly on which vendor's API it called is not a general-track winner.

Consequence to state out loud to the sponsor before the event: a project can win the sponsor track and place nowhere overall, and that is the design working, not a scoring error.

## The normalization arithmetic, worked

The normalization argument underpins the combination-rule ordering in SKILL.md and is worth showing a jury.

Suppose judge H scores systematically two points lower than the rest of the panel on the 1-5 scale.

- **Under full coverage**: H scores every team in the field, and every team's total drops by the same 2 points × H's share of the panel. Subtracting a constant from every total leaves the ordering untouched. The rank is identical with or without normalization, so normalization is pure overhead here.
- **Under a sampled panel**: H is on the panel covering teams 1-20 and never sees teams 21-60, so teams 1-20 each lose points that teams 21-60 do not. The rank across the whole field is now partly a record of which panel a team drew. Normalization (converting each judge's scores to ranks or to z-scores within that judge's own slice before combining) removes exactly that artifact.

The practical rule: **normalize whenever a judge scored a proper subset of the field.** That is the same condition as being in Band 2 or 3 of the allocation math, which is why the two menus are coupled rather than chosen independently.

Two honest limits on normalization:

- It corrects a judge who is uniformly harsh, but it cannot correct a judge who is harsh on one kind of project and generous on another.
- With small slices (a judge who saw five teams), the correction is computed from very little data and can move a rank as much as the bias did.

Below roughly a dozen teams per judge, prefer rebalancing the panels so judges overlap on a shared subset instead. That overlap threshold is self-set rather than an established standard.

## A positive and a negative scoring pair

**Negative - what a judge actually wrote on an unweighted, criteria-free sheet:**

> Team 14: 8/10. Really impressive, loved the energy.

Nothing here survives a challenge. It cannot:

- Say which criterion carried the score.
- Be compared to another judge's 8.
- Feed a tie-break.
- Be explained to team 15 who got a 7.

"Energy" is not on any rubric.

**Positive - the same judge, same four minutes, on the weighted sheet above:**

> Team 14 - Working demo 5 (ran live, we asked it to handle a bad input and it did). Technical execution 4 (auth is real, the ranking is a stub they said so). Fit to the brief 3 (solves an adjacent problem, not the published one). Presentation 4. Weighted total 4.10.

- The scores are comparable.
- The parenthetical evidence is one clause rather than a paragraph.
- The fit gap is on the record before anyone contests it.
- The tie-break has something to reach for.

The whole entry fits inside the slot because nothing in it is prose.

## Judge-type fit

**Mix judge types within each panel rather than clustering them, so no team's whole panel shares one blind spot.** That is a constraint on the allocation map, not only on recruitment: judge composition changes what a format can surface, and therefore what a criterion is worth.

Each type weights a different thing and needs a different affordance from the format:

- **Technical judges** weight working code and novel implementation, and need to touch the demo.
- **Business judges** weight market size and monetization, and need the narrative delivered deliberately.
- **Domain experts** weight real-world accuracy.
- **Sponsor representatives** weight use of their own technology, and need an explicit rubric prompt, or it bleeds into their other scores.

## Using the worked examples

Every weight, scale length and threshold on this page serves as a starting point for organizers to debate, not as a standard to conform to. Adjust all of them against the event's own culture and constraints.
