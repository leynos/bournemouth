# 1. Key goals for the **MVP**

| Target              | Requirement                                     | Practical yard-stick                                                                       |
| ------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Latency**         | Sub-second end-to-end for 95% of chat turns     | Retrieval ≤ 50 ms, LLM generation ≤ 600 ms, glue ≤ 350 ms                                  |
| **Security**        | Comparable to a mainstream consumer e-mail host | TLS everywhere, OIDC login, data encrypted at rest, audit trail, per-tenant data isolation |
| **Cost/complexity** | “One DevOps engineer can run it”                | ≤ 5 long-running services, zero-licence software                                           |

______________________________________________________________________

## 2 Minimum-viable component set (one **Kubernetes** namespace)

| #   | Runtime                                        | Role                                           | Why it’s *minimum*                                                                                     |
| --- | ---------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1   | **Traefik** (or NGINX Ingress)                 | TLS termination, OIDC ↔ IdP, rate-limit        | single binary, well-worn Helm chart                                                                    |
| 2   | **chat-api** (**Python 3.13 + Falcon**)        | Handles REST/WS chat, does RAG & novelty test  | Falcon adds `<1 ms`/router overhead in benchmarks ([falconframework.org][1])                           |
| 3   | **neo4j** (single-node, Community)             | Knowledge-graph + native vector index          | graph *and* ANN search in one store ([Graph Database & Analytics][2], [Graph Database & Analytics][3]) |
| 4   | **postgres** (13 + `pgvector`)                 | users \+ auth tables + audit log; fallback ANN | keeps auth/PII out of the graph; pgvector is OSS ([GitHub][4])                                         |
| 5   | **worker** (same image as chat-api)            | Background queue + cron for batch KG writes    | avoids a full Airflow/Argo install; scale to 0 when idle                                               |

A **monorepo**, one Dockerfile, two deployable images (API / worker) keep
build-time friction low. Add as many **chat-api** replicas as needed; each uses
Python **sub-interpreters** (PEP 684) to achieve true CPU-parallel request
handling without spawning extra OS processes
([Python Enhancement Proposals (PEPs)][5]).

______________________________________________________________________

### 3 Hot path for a single request (≤ 1 s)

```text
User ➜ Traefik(OIDC) ➜ chat-api
      ① parse + embed query (≈5 ms, on-CPU)
      ② Cypher: graph lookup + vector ANN  (≈20-40 ms)
      ③ compose prompt and call LLM        (≈300-600 ms)
      ④ stream tokens to client            (≈100 ms overlap)
```

*Because retrieval never calls an LLM* and lives in-process with a local Neo4j
driver, it stays comfortably under 50 ms even with tens of thousands of triples.

______________________________________________________________________

### 4 Surprise-based memory in the MVP

*Inside chat-api* after every user turn:

1. **Cheap novelty test**

   - Named-entity scan (spaCy small, 2–3 ms).
   - Hash of `(subject, relation, object)` looked up in Neo4j; *missing* ⇒
     novel.
   - If *high* novelty (new entity *or* contradicts current fact) enqueue a job
     on the **worker** (Redis queue or Postgres NOTIFY).

2. **Worker job (async, eventual consistency)**

   - Runs same extractor but slower **relation-extract** model.
   - Up-serts nodes/edges with a `valid_from` timestamp, tombstones superseded
     facts.
   - Logs change row in Postgres for audit.

This keeps the chat path GIL-free and sub-second, while memory refresh settles
in minutes.

______________________________________________________________________

### 5 Security hardening checklist

Comparable to e-mail SaaS defaults

| Surface      | Measure                                                                                                                     |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Transport    | Traefik terminates TLS 1.3; internal pod-to-pod mTLS via service mesh (optional)                                            |
| AuthN        | OIDC bearer-token middleware in chat-api; short-lived JWTs                                                                  |
| AuthZ        | Every Cypher/SQL query parameter-filters on `tenant_id`; Neo4j role set to *reader* for API pod, *editor* for worker pod    |
| Data at rest | LUKS-encrypted PVs, Postgres `pgcrypto` for PII fields, AES-encrypted Neo4j store.key                                       |
| Secrets      | K8s Secrets ↔ sealed-secrets; no secrets baked in images                                                                    |
| Audit        | INSERT trigger on Postgres `kg_audit` table; chat-api logs `(user, prompt, retrieved_ids)`; immutable retention ≥ 90 days   |
| Back-ups     | `kubectl exec neo4j -- neo4j-admin dump` nightly; Postgres `pg_dump`                                                        |
| DoS / abuse  | Traefik rate-limit plugin; Redis sliding-window per IP & per JWT                                                            |

______________________________________________________________________

### 6 Why this meets the brief

- **Minimal surfaces:** five pods keep cognitive and ops load low; no
  heavyweight orchestration.
- **Latency headroom:** retrieval path is pure DB I/O; Neo4j’s vector index is
  in-process C++ (sub-millisecond for < 100 k vectors)
  ([Graph Database & Analytics][3]).
- **Concurrency without gunicorn churn:** sub-interpreters exploit multiple
  cores safely ([Python Enhancement Proposals (PEPs)][5]).
- **Audit & isolation:** row-level tenant filters, full change log, encrypted
  vols → on par with consumer mail providers.
- **Evolvable:** drop-in Dask cluster later if extraction volume explodes (adds
  1 ms task overhead only) ([distributed.dask.org][6]); swap Neo4j for sharded
  instances when graph > 100 M triples; plug Airflow if cronjobs grow unwieldy.

______________________________________________________________________

### 7 Scaling path (when the MVP creaks)

1. **LLM latency**: move from external API to local quantised Q-former (4-bit)
   on A10G → 100 ms generation.
2. **Batch brain surgery**: add Airflow or Argo once nightly jobs > 3; still
   keep API stateless.
3. **Graph size**: spin up a Neo4j causal cluster; or shard by tenant hash if
   still on Community.
4. **Compute bursts**: tack on a Dask‐Kubernetes operator for ad-hoc embedding
   re-builds.

Until then, the above **five-service footprint** is the leanest way to deliver
surprise-aware, RAG-backed chat with enterprise-grade security and true
sub-second answers.

[1]: https://falconframework.org/?utm_source=chatgpt.com "Falcon | The minimal, fast, and secure web framework for Python"
[2]: https://neo4j.com/press-releases/neo4j-vector-search/?utm_source=chatgpt.com "Neo4j Adds Vector Search Capability Within Its Graph Database"
[3]: https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/?utm_source=chatgpt.com "Vector indexes - Cypher Manual - Neo4j"
[4]: https://github.com/pgvector/pgvector?utm_source=chatgpt.com "pgvector/pgvector: Open-source vector similarity search for Postgres"
[5]: https://peps.python.org/pep-0684/?utm_source=chatgpt.com "PEP 684 – A Per-Interpreter GIL | peps.python.org"
[6]: https://distributed.dask.org/?utm_source=chatgpt.com "Dask.distributed — Dask.distributed 2025.5.0 documentation"
