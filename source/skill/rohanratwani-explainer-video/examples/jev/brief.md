# ep02 · Jev, the decision model (and how to use it in RAG) · fact sheet

Researched 2026-10-01. Narration and on-screen facts come only from this file.
Angle: plenty of "Jev explained" videos already exist (Caleb Writes Code's 7-minute one has 751k
views). Our edge is shorter, visual, and the RAG angle, which only a few small videos cover and
which chains straight off ep01.

## Facts used
| Claim | Source |
|---|---|
| Made by TypeSafe AI, launched (early access) 15 Sep 2026 | [TechTarget](https://www.techtarget.com/it-infrastructure/news/366650696/Jev-decision-model-touted-as-quicker-cheaper-LLM-alternative), [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| Founder Diogo Almeida, ex-OpenAI researcher | [TechTarget](https://www.techtarget.com/it-infrastructure/news/366650696/Jev-decision-model-touted-as-quicker-cheaper-LLM-alternative) |
| A decision model: answers typed questions about text or JSON, returns structured values, never prose. Marketed as the first "System One" model | [Sanity glossary](https://www.sanity.io/glossary/jev-typesafe-ai-model), [TAO](https://www.tao.media/jev-explained-the-ai-model-that-makes-decisions-instead-of-writing-answers/) |
| "Language models generate; decision models choose" | [Sanity glossary](https://www.sanity.io/glossary/jev-typesafe-ai-model) |
| Three question types: choice (pick from options you supply), score (rate on levels you define), noul (probability a yes/no statement is true) | [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| Choice and score return a probability for every option plus a confidence from 0 to 1 | [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| About 10 full decision loops per second; LLMs need several seconds | [TechTarget](https://www.techtarget.com/it-infrastructure/news/366650696/Jev-decision-model-touted-as-quicker-cheaper-LLM-alternative) |
| $0.042 per million input tokens, output free | [TechTarget](https://www.techtarget.com/it-infrastructure/news/366650696/Jev-decision-model-touted-as-quicker-cheaper-LLM-alternative), [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| A million support tickets would cost about $19 | [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| GPT-6.1 Sol standard input price: $2.00 per million tokens | [benchlm](https://benchlm.ai/blog/posts/openai-devday-2026) |
| 13% of Vercel's paid AI Gateway users adopted it within 24 hours | [TechTarget](https://www.techtarget.com/it-infrastructure/news/366650696/Jev-decision-model-touted-as-quicker-cheaper-LLM-alternative) |
| Limits: text only, no text generation or explanations, no exact arithmetic, no published weights or paper | [OpenRouter](https://openrouter.ai/blog/insights/what-is-jev/) |
| RAG uses: routing questions by type, reranking 60 retrieved chunks (~30,000 tokens, about a tenth of a cent), citation checking in 4 categories (full support, partial, not relevant, contradicts). Final answer stays with an LLM | [The AI Automators](https://www.theaiautomators.com/switching-rag-decisions-to-jev/) |
| Other documented RAG uses: filtering irrelevant chunks before generation, routing between SQL / vector / graph search | [MindStudio](https://www.mindstudio.ai/blog/jev-reranker-rag), [Hugging Face use-case list](https://huggingface.co/blog/karmen-beatapi/18-practical-jev-use-cases-for-ai-agents) |
| Prompt injection: Check Point hid false content inside documents; 59% of attack attempts succeeded (24 Sep 2026) | [Check Point](https://blog.checkpoint.com/ai-security/jev-is-not-a-language-model-but-it-breaks-like-one-prompt-injection-against-a-typed-decision-model/) |
| Amazon open-sourced Strands Decider 2B, a Jev-style model small enough to run locally (1 Oct 2026) | [TechCrunch](https://techcrunch.com/2026/10/01/amazon-releases-its-own-jev-clone-as-decision-models-flood-the-web/) |
| OpenAI announced a Decisions API (model: Luna), limited preview, at DevDay 29 Sep 2026 | [OpenAI dev community recap](https://community.openai.com/t/devday-2026-announcements-and-developer-resources/1402006) |

## Illustrative, not claims
- The support-ticket hook, the ticket text, the paragraph the LLM writes, and every probability
  shown on screen (0.94, 0.82, 71%) are made-up examples of the output shape.
- "System One" explained as fast, gut-feel decisions is our gloss on the name (Kahneman's term).
- Using routing to choose plain RAG vs GraphRAG per question is our suggested design, built from
  the documented routing use. The narration says "you could".
- Reranking accuracy: sources disagree (5% to 18% top-1 in one write-up, 21% to 54% in another),
  so no accuracy number goes on screen.
