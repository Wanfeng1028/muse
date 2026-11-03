# Research and the brief

The brief is the only source of truth for the video. Write it before a single beat.

## Steps
1. Search the topic. Read the primary source (the launch post, the paper, the docs) before any
   write-up of it. Note the date of every source.
2. Search YouTube for the topic. Note the top 5 videos, their views, length, and angle. Your
   angle is whatever they all skip: a use case, a comparison, a catch, a number nobody showed.
3. Fill `brief.md` from `templates/episode/brief.md`:
   - **Facts used:** one claim per row, worded the way the narration will say it, with a link.
   - **Illustrative:** example data, invented tickets, made-up probabilities that show an output
     shape, analogies. Say so here, so nobody mistakes them for claims.
   - **Sources disagree:** both numbers, and keep the number off screen.
4. Every number on screen must trace to a row. Round only in the direction that does not
   overstate ("about 48x", not "50x", when the math gives 47.6).

## Timing and topic choice
- **News** (a launch in the last few days) belongs in a Short. Big channels cover news long-form
  within 48 hours and own search for it.
- **Evergreen** topics and angles nobody covered belong in long-form.
- Titles in the "X Explained in N Minutes" shape do well for explainers. N must be the real
  runtime, rounded up.
