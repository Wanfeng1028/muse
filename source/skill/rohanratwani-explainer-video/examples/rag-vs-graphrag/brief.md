# ep01 · RAG vs GraphRAG · fact sheet

Every number and claim on screen traces to a line here. If it is not here, it is not in the video.

## Claims used

| On screen | Source |
|---|---|
| RAG = retrieval augmented generation; the name comes from a 2020 paper by Facebook AI researchers ("Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", Lewis et al.) | Lewis et al., 2020, arXiv 2005.11401 |
| GraphRAG paper published April 2024 | arXiv 2404.16130, first submitted 2024-04-24 (Edge, Trinh, Cheng, Bradley, Chao, Mody, Truitt, Metropolitansky, Ness, Larson) |
| Open sourced that July | Microsoft Research blog, "GraphRAG: New tool for complex data discovery now on GitHub", 2024-07-02 |
| A Christmas Carol is the sample book in Microsoft's GraphRAG Get Started guide, with the query "What are the top themes in this story?" | microsoft.github.io/graphrag/get_started |
| Pipeline: LLM extracts entities + relationships into a graph, Leiden community detection (hierarchical), pre-generated community summaries, global search = map-reduce over summaries | arXiv 2404.16130 |
| Test datasets: podcast transcripts ~1M tokens (1,669 × 600-token chunks), news articles ~1.7M tokens (3,197 chunks) | arXiv 2404.16130 (HTML v2, datasets section) |
| 72–83% comprehensiveness win rate vs vector RAG, big picture (global) questions, judged by an LLM evaluator | arXiv 2404.16130: 72–83% podcasts, 72–80% news (p<.001). Video says "72 to 83 percent" across both |
| LazyGraphRAG: indexing cost identical to vector RAG and 0.1% of full GraphRAG | Microsoft Research blog, "LazyGraphRAG: Setting a new standard for quality and cost", Nov 2024 |

## Book details used (public domain, 1843)
- Opening lines on the embedding card are verbatim: "Marley was dead: to begin with..." through "Scrooge signed it."
- "Bah!" said Scrooge, "Humbug!" and "Out upon merry Christmas!" are verbatim (Stave One).
- Bob Cratchit is Scrooge's clerk; he "ran home to Camden Town" (Stave One). The chunk 37 card is a paraphrase built on that line, not a quote.
- Tiny Tim is Bob's son. Belle leaves Scrooge over his love of money. Fezziwig was his old employer. Fan is his sister and Fred's mother. Fred is his nephew.

## Illustrative, not data (said or shown as examples)
- The hook's chat, "1,204 files" and the three quotes are a made-up example ("You give an AI...").
- Embedding numbers, map positions, chunk numbers and the theme list are illustrative.
- The cost receipts list the steps, not prices. No dollar figures anywhere.

## Sources
- https://arxiv.org/abs/2404.16130
- https://www.microsoft.com/en-us/research/blog/graphrag-new-tool-for-complex-data-discovery-now-on-github/
- https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
- https://microsoft.github.io/graphrag/get_started/
- https://arxiv.org/abs/2005.11401
