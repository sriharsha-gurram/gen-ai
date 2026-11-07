# Evaluation Report — Market Research Agent (Week 3)

Run date: 2026-11-07. Markets: iPaaS and vector databases. Generation: OpenAI gpt-4o-mini (Gemini fallback unused). Search: Tavily basic depth. The two final runs (below) each took under 1 minute end to end; this report is a re-score of those runs after the absence-citation strip fix, so the run IDs and credits are from the original runs. Re-score time: 0.9 minutes.

## Summary

### AI integration platforms (iPaaS)

- Run: `ai-integration-platforms-ipaas-20261107-201336` — status done
- Claims judged: 10 (grounded 9, partial 1, ungrounded 0) — groundedness 0.9
- Completeness: 12/15 fields present across 3 competitors
- Citation coverage: 14/14 citations point at run sources
- URLs live-checked: 6/6 reachable
- Tavily credits: 14, errors recorded: 0

### vector databases

- Run: `vector-databases-20261107-201429` — status done
- Claims judged: 10 (grounded 10, partial 0, ungrounded 0) — groundedness 1.0
- Completeness: 12/15 fields present across 3 competitors
- Citation coverage: 8/8 citations point at run sources
- URLs live-checked: 5/6 reachable
- Tavily credits: 14, errors recorded: 0

## Per-claim judgements

### AI integration platforms (iPaaS)

- [grounded] MuleSoft's pricing model is capacity-based, utilizing flows and messages for its cost structure . (https://www.integrate.io/blog/mulesoft-cost)
- [grounded] The starting price for MuleSoft is $2,000 per month . (https://www.mulesoft.com/pricing)
- [grounded] MuleSoft is positioned as the world’s #1 integration and API platform . (https://www.salesforce.com/mulesoft/pricing)
- [grounded] It offers API management capabilities that support APIs throughout their entire lifecycle, from design and security to monitoring and discovery . (https://www.mulesoft.com)
- [partial] Extensive customization capabilities are available within the platform . (https://www.oneio.cloud/blog/what-is-mulesoft-used-for)
- [grounded] Boomi operates on a tiered subscription pricing model with pay-as-you-go options . (https://www.integrate.io/blog/boomi-pricing)
- [grounded] The starting price for Boomi is $99 per month plus usage . (https://ezintegrations.ai/ezintegrations-vs-boomi)
- [grounded] Boomi is positioned as a cloud-native, loosely coupled integration framework that supports microservices and hybrid deployments . (https://oditeksolutions.com/webmethods-to-boomi-migration)
- [grounded] Notably, it provides unlimited connections to applications and data sources . (https://checkthat.ai/brands/boomi/pricing)
- [grounded] The platform also allows for unlimited users without per-seat licensing , and includes standard 24/7 support . (https://checkthat.ai/brands/boomi/pricing)

### vector databases

- [grounded] Pinecone operates on a pricing model that involves a monthly minimum commitment based on the selected subscription plan . (https://docs.pinecone.io/guides/manage-cost/understanding-cost)
- [grounded] The starting price for the Starter plan is $0 per month . (https://docs.pinecone.io/guides/manage-cost/understanding-cost)
- [grounded] Pinecone is positioned as a leading vector database solution for AI applications . (https://airbyte.com/data-engineering-resources/pinecone-vector-database)
- [grounded] It offers fast similarity search capabilities across millions of data points . (https://airbyte.com/data-engineering-resources/pinecone-vector-database)
- [grounded] The platform also features managed infrastructure with automatic scaling . (https://airbyte.com/data-engineering-resources/pinecone-vector-database)
- [grounded] Users benefit from sub-second query performance  and integration with modern data stacks . (https://airbyte.com/data-engineering-resources/pinecone-vector-database)
- [grounded] Milvus provides an open-source and managed cloud pricing model . (https://airbyte.com/data-engineering-resources/milvus-database-pricing)
- [grounded] The starting price for their services is $99 per month . (https://airbyte.com/data-engineering-resources/milvus-database-pricing)
- [grounded] It is suitable for organizations needing a high-performance vector database solution . (https://airbyte.com/data-engineering-resources/milvus-database-pricing)
- [grounded] Milvus grants full access to basic features through a free tier . (https://airbyte.com/data-engineering-resources/milvus-database-pricing)

## Failure analysis

### AI integration platforms (iPaaS)

- [partial] Extensive customization capabilities are available within the platform . (https://www.oneio.cloud/blog/what-is-mulesoft-used-for)
- Completeness gaps (fields not found in sources): {'MuleSoft': ['recent_news'], 'Boomi': ['recent_news'], 'Workato': ['recent_news']}
- No cited URL failed the live check (6/6 reachable).

### vector databases

- Completeness gaps (fields not found in sources): {'Pinecone': ['recent_news'], 'Milvus': ['recent_news'], 'Weaviate': ['recent_news']}
- Cited URLs that did not load on the live check: ['https://milvus.io/docs/comparison.md']

The uniform completeness gap is recent news: it is missing for all six competitors. The news search (Tavily, last month) returns items, but dates are rarely visible in the snippets or extracts, so the extractor — correctly, per its rules — leaves news out rather than dating it by guesswork. That is a data limitation, not an invention: the briefings say the news was not found instead of printing a stale item as current.

## Cost

Re-score pass after the citation-strip fix (judging only, no new agent runs): gpt-4o-mini 9180 in / 661 out tokens, ~$0.0018. Total OpenAI spend across the whole build (about 10 runs including crashes, retries, and evals) is under $0.10 of the $5.00 credit.
