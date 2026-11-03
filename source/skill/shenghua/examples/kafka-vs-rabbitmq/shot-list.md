# Shot list — Kafka vs RabbitMQ (40.1s of voice, 42.3s composition)

Template `blueprint` · brand `brand.example.json` · captions `phrase` · music drop at 39.56.
Times are word starts from `transcript.txt`. Sound lists the cues `render.js cues` extracts, including
each entry's whoosh (0.1–0.12s before the cut); `fade` and `cut` entries make none.

```
#   in-out        line (spoken)                         block                               sound
01  0.00-2.32     Okay, quick question. If I told you   kinetic slam + ghost "?" drift      hit@0.84
02  2.32-5.88     RabbitMQ deletes your messages…       term pill + lane and tokens + stamp whoosh@2.22 pop@2.32 pop x3@2.50 pop@3.86 whoosh@4.48 pop@4.98 stamp+hit@5.16
03  5.88-7.86     and Kafka basically never does,       lane + offset counter + stamp       whoosh@5.76 pop@5.95 tick@6.14 stamp+hit@6.76
04  7.86-9.50     would you know which one to use       duo cards + slam "?"                pop@7.98 pop@8.10 hit@8.42
05  9.50-11.12    and why that one detail               highlight box                       whoosh@9.40 hit@10.20
06  11.12-13.60   changes everything about how you…     hub-and-spoke diagram               whoosh@11.02 pop@11.12 pop x4@11.58
07  13.60-17.00   Most tutorials show you both tools…   terminal                            whoosh@13.48 type@13.80 type@14.90 type@16.00
08  17.00-18.36   I'm not going to do that.             double strike-through               hit@17.16
09  18.36-21.82   By the end of this, you'll unders…    stacked rise + highlight + path     hit@21.22
10  21.82-25.46   that explains basically every oth…    tree diagram                        whoosh@21.72 pop@21.95 pop x5@23.22 hit@24.04
11  25.46-27.32   with real Spring Boot code,           terminal (code)                     whoosh@25.34 type x4@25.60
12  27.32-28.82   real numbers,                         kinetic type + bar motif            hit@27.86
13  28.82-30.26   and zero hand-waving.                 slam + strike-through               hit@28.82 hit@29.50
14  30.26-33.26   Let's get into it. Kafka versus R…    riser + stacked slams               whoosh@30.16 riser@30.36 hit@31.36 pop@31.50 hit@32.02
15  33.26-36.56   Everyone treats this like a cage…     duo cards + stamp + strike-through  whoosh@33.14 whoosh@33.50 stamp@34.50 hit@35.90
16  36.56-37.80   It's one question.                    highlight box                       hit@36.76
17  37.80-42.30   Do you need a queue or do you nee…    stacked slams + outro (brand handle) whoosh@37.68 hit@38.28 hit@39.56 pop@40.30
```

Captions hidden (`NOCAP`): 0–1.68 (the headline is the line), 18.36–21.82 (stacked headline),
27.32–33.26 (the words are the headline), 34.50–35.72 (the CAGE MATCH stamp), 36.56–end (the
question is on screen).

Media: none. Every visual is a template block; nothing is fetched, so there is nothing to credit.

On screen but not in these 40 seconds:

- **From later in the script:** the five differences in shot 10 (retention, routing, ordering, replay,
  throughput), the consumer offset in 03, "keeps the log" in 04, the BILLING and ANALYTICS consumers in
  06, and `topics = "orders"`, `groupId = "billing"` in 11.
- **Invented illustration:** the PRODUCER, BROKER and AUDIT nodes in 06, "deletes on read" in 04, the
  tutorial terminal in 07, the method body in 11, and the bar heights in 12 (no values or labels).
