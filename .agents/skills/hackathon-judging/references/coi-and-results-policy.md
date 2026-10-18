# Conflict of interest, judge briefing, and results policy

## Contents

- The conflict ladder in detail
- The sponsor-judge hard case
- Judge recruitment and eligibility
- The judge brief checklist
- Announcement plan
- The contest path
- Tie-break precedent

## The conflict ladder in detail

**No formal process.** Judges are trusted implicitly and nothing is said.

It triggers no review before the event and pushes the whole review to the point of least reversibility - after prizes changed hands, when the only remaining options are re-running a judged round nobody can reconvene or living with the result. Delete this rung entirely once any sponsor funds a track prize.

**Self-declared recusal - the default.** One line in the judge brief: abstain from scoring any team you are close to, rather than scoring it and disclosing afterwards.

The convention is borrowed from conference-review practice: tell reviewers to "skip the question" for colleagues they work closely with and for organizations they are associated with or competing against, and to review wearing the event's hat rather than an employer's.

- What transfers: the honour-system convention and its framing.
- What does not transfer: the recovery time. A CFP reassigns a reviewer over days, a hackathon reassigns inside the window.

Wording that works in a brief, at the right level of specificity:

> If a team includes someone you work with, someone you manage or are managed by, someone you have invested in or are hiring, or a company you compete with directly - do not score them. Tell the judging lead and we will route another judge to that table. You are judging for the event, not for your employer.

Name the recusal fallback in advance: what happens when a team loses so many judges that its scores are no longer comparable to the rest of its band.

- The workable answer: route replacement judges from another panel and record the swap.
- The unworkable one: average what is left and hope.

**Declared recusal plus assigned replacement.** The organizer keeps a list of judge-to-sponsor and judge-to-team ties collected at recruitment, and rebalances the allocation map when one fires.

Promotion condition: any sponsor funds a track and any judge is tied to that sponsor. Cost is a live tracking job on the judging lead, and the rebalance is visible to the sponsor whose representative was moved.

**Written policy with a disclosure registry and escalation path.** Ties are declared in writing before the event, the register is kept, and a named person arbitrates a judge who will not recuse.

Top of value, effort and compliance cost: it triggers a governance review every edition, and it is the hardest rung to unwind, because withdrawing a published policy next edition reads as a retreat rather than a simplification. Promotion condition: a multi-edition event whose published rules already promise a dispute process, or a prize pool large enough that a losing team will ask who decided and on what basis.

## The sponsor-judge hard case

A signed sponsorship agreement can require the sponsor's own representative to judge the track that sponsor funded. The conflict was accepted at contract time. The ladder above cannot rank it away, and pretending otherwise produces advice the organizer cannot follow.

Handling, in order:

1. **Confine the sponsor judge to that track.** Keep them off the overall or grand-prize decision. The contract bought a say in the prize the sponsor funded, not in the event's headline rank.

   If the contract genuinely reaches the overall prize, that is a negotiation failure to fix next edition, not a scoring problem to solve now.

2. **Pair them with at least one neutral judge on that track.** A track judged by one interested party is not judged.
3. **Run the drop-test.** Compute the track rank twice: with the sponsor judge's scores and without them.

   - If the winner is the same: say so in the announcement notes and move on.
   - If the winner changes: tell the sponsor before the ceremony, not after, and decide in advance who makes that call.

   The test costs one extra column in a spreadsheet and it is the only cheap evidence available that the outcome was not bought.

4. **Disclose the composition in the published rules before submissions close.** A conflict disclosed in advance is a rule teams entered under.

   The same conflict disclosed after the announcement is a scandal. Nothing about the facts changes between those two outcomes except the timing.

Where the clause has not been signed yet, say what to ask for and hand the drafting to `samber/dev-event-organizer-skills@event-sponsor-agreement`:

- A sponsor judge scoped to the sponsor's own track.
- A neutral co-judge on that track.
- The disclosure obligation stated in the agreement rather than assumed.

## Judge recruitment and eligibility

- **Judges are not mentors.**
  - Mentors help teams build during the hacking window.
  - Judges evaluate finished projects afterwards.

  Reusing the same people is a staffing convenience at a small event, and it carries a real cost: a mentor who helped a team build cannot score that team neutrally. If the roles overlap, apply the recusal rule to every team that person mentored.

- **Judges cannot compete.** Organizers, volunteers, judges and sponsors are barred from competing as hackers. Check the entrant list against the judge list before scoring, not after.
- Recruit against the panel composition the allocation map needs - a mix of judge types per panel - rather than filling a headcount and sorting the mix later.
- Collect each judge's employer and any team or sponsor ties at recruitment. That single question is what makes the recusal rule enforceable on the day.
- Confirm each judge's availability against the actual judging window in minutes, not against "the afternoon". A judge who arrives an hour late shrinks `W` for their whole panel.

## The judge brief checklist

Deliver before scoring opens, in writing and in person. Six items, all of which must exist for the skill's pass threshold:

1. The criteria, in the brief's own words, with the weights.
2. The scale, with what a 1 and a 5 each mean.
3. The conflict-of-interest rule and who to tell.
4. Their own slice of the allocation map: which teams, in which order, starting when.
5. The clock: how many minutes per team, and what to do if they fall behind - skip the notes, never skip a team.
6. What happens to their scores afterwards: how they combine, that per-judge scores are not published, and that the tie-break may reach for their sheet.

## Announcement plan

- Collect the winner list, sponsor tracks included, before the ceremony rather than live. Announce from prepared slides rather than live narration.
- Do not schedule live demos at the closing ceremony while judging is still concluding. The allocation arithmetic gives the mechanical reason: demo slots and judging draw on the same minutes.
- Announce the rank and the criteria. Withhold per-judge and per-team raw scores, and the numeric weights unless the event already published them before submissions closed. That is the default because publishing either turns a decision into a leaderboard teams audit at a precision the rubric was never built for, and raw scores additionally expose individual judges by name.

  The opposite posture (publishing full scores) is a legitimate choice for an event that wants radical transparency and has a rubric robust enough to survive it; make it deliberately, and publish the tie-break ladder alongside.

- Announce sponsor-track winners from the sponsor's own confirmation, collected in advance, so the ceremony is not the place a sponsor changes its mind.

## The contest path

An appeals or dispute process for a judging result is a separate subject from code-of-conduct sanction appeals, which some events do publish. Treat what follows as a process you adopt and publish, not as an established norm.

State all four elements in the published rules before submissions close:

1. **Who receives a challenge** - a named role, not "the organizers".
2. **The window** - short, and closing before prizes change hands. After payout, reversal is a money problem and belongs to `samber/dev-event-organizer-skills@hackathon-cash-prize`.
3. **What can change** - an arithmetic error, a missed submission, or an eligibility fact. A judge's opinion cannot.
4. **What the answer looks like** - the rubric, the weights, and which criterion decided. Not the per-judge scores.

Two rules for handling one when it arrives:

- Answer in writing.
- Answer with the process rather than the verdict.

"Your fit-to-brief score was the lowest of the three finalists and fit carries 25%" is an answer. "The judges felt yours was weaker" is not.

## Tie-break precedent

Real published rules corroborate the ladder above, though none matches it rung for rung.

- **Devpost's rules template** is the closest industry standard: compare tied submissions on the first-listed judging criterion, walk down the list if still tied, then fall back to a judges' vote once every criterion ties. This exact wording is reused verbatim across many Devpost-hosted hackathons, including Google Cloud- and Microsoft-sponsored ones.
- **Global PyTorch Summer Hackathon** fixes the criterion order by name ("Potential Impact" before "Implementation of the Idea") instead of using the submission's own listed order - the same cascade idea, with the order set explicitly rather than inherited.
- **AWS Breaking Barriers Challenge** escalates through score comparison, then a judges' vote, then a named event-leader as the final tiebreaker - the same three-step shape as this ladder's rungs 1, 2 and 3.
- **Meet & Hack 2 (RIT)** re-judges by the full panel first, then escalates to a named tie-breaking judge if the panel still ties.
- **MLH's own contest terms** give the judge sole and final discretion, with no criterion cascade at all - the loosest published version of rung 3.
- **WildHacks (MLH-affiliated)** publishes a three-tier fallback borrowed from competitive debate instead of a criterion cascade: normalized score, then median score with the high and low dropped, then average score with nothing dropped.
- **HackMIT** avoids numeric ties structurally. Its Gavel system ranks projects by pairwise comparison (the Crowd-BT algorithm) rather than independent scores, so there is no tie to break in the first place.
- **Salesforce** is the one documented case of abandoning score-based resolution entirely: after a 2013 judging controversy at its Salesforce1 Hackathon, it declared co-champions and split the grand prize between both finalists. That was crisis management after the fact, not a rule published in advance.

Platforms outside the Devpost template default to discretion rather than a formula: NASA Space Apps' Judging & Awards Guide has no tie-break language at all, and an executive committee decides winners instead.
