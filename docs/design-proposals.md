# Design Proposal

Thanks, that's exactly the context I needed. I’ll put together a proposed
architecture for a cloud-deployed, novelty-based knowledge graph memory system
with retrieval-augmented generation (RAG), tuned for multiple authenticated
users and eventual consistency. It will emphasise auditability, accuracy, and
latency, using Python 3.13, Falcon, and open source tools like JAX, Airflow, and
Argo where relevant.

I’ll let you know as soon as the design is ready for review.

## Cloud-Deployable Knowledge Graph Memory & RAG System Architecture

## Introduction

Building a chatbot with **long-term memory and retrieval-augmented generation
(RAG)** capabilities requires an architecture that can **continuously learn new
information** and recall it efficiently during conversations. This proposal
outlines a cloud-deployable system for a novelty/surprise-based knowledge graph
memory, integrated with a chatbot’s RAG pipeline. The design targets deployment
on Kubernetes (e.g. AKS on Azure or EKS on AWS) and supports **multiple users**
with secure, authenticated access. The solution emphasizes **detecting novel or
surprising information** in user interactions and updating the knowledge graph
memory accordingly, while keeping inference-time latency low. We leverage modern
Python features (e.g. Python 3.13 with subinterpreters), parallel compute
libraries (JAX/Dask), and workflow orchestrators (Airflow/Argo) to achieve these
goals, using open-source components for data storage and processing.

**Key goals and challenges include:** multi-user isolation and authentication,
real-time novelty detection to trigger memory updates, efficient knowledge graph
storage with versioning and querying, asynchronous background processing of
heavy tasks, minimal latency for chatbot responses, and full auditability of
memory updates and model inferences. The following sections present a detailed
architecture proposal, covering system components, technology choices,
scheduling strategies for updates, and a discussion of trade-offs and open
challenges.

## System Overview and Requirements

**System Requirements:** The system must allow each authenticated user to have a
personal knowledge graph “memory” that the chatbot can use for enriched
responses. It should detect when new information (novel facts or relations)
appears in conversations and decide whether to incorporate it into the knowledge
graph. Updates to the graph should be versioned (preserving history) and
traceable. The chatbot’s inference pipeline should retrieve relevant knowledge
with minimal latency (preferably no expensive model calls during retrieval) and
incorporate it into generation. All components should be containerized and
orchestratable on Kubernetes for scalability. Python 3.13 is the implementation
language, using the Falcon web framework for the API, and taking advantage of
PEP 734-style subinterpreters for concurrency. Batch or long-running jobs (like
periodic graph maintenance or large-scale extraction) will be managed via Apache
Airflow or Argo Workflows. The design prioritizes open-source tools (for
example, Neo4j or PostgreSQL for storage, JAX or Dask for computation) to avoid
licensing costs.

**High-Level Architecture:** The system can be thought of as a set of
interacting services and modules, illustrated below:

- **User Interface / Chatbot Frontend:** (Outside scope) Communicates with our
  backend via API.
- **Falcon Web API Service:** Receives chat requests, manages user sessions and
  auth, and routes queries to the RAG pipeline.
- **RAG Pipeline:** For each query, performs **retrieval** from the knowledge
  graph memory (and possibly other indexes) and then calls the **generation
  component** (LLM) with the query plus retrieved context to produce an answer.
- **Knowledge Graph Memory Store:** A graph database that persists entities,
  relations, and possibly supporting text. Supports **graph queries** and
  **index lookups** (semantic and keyword) to retrieve relevant knowledge.
- **Novelty/Surprise Detection Module:** Analyzes incoming user utterances (and
  possibly the chatbot’s outputs or external data) to detect unseen entities or
  facts. If a novelty **threshold** is exceeded, it triggers the knowledge
  update workflow.
- **Knowledge Extraction Pipeline:** When triggered (either in real-time or
  batch), this pipeline uses NLP techniques to extract entities and
  relationships from new information, possibly aided by ML models. It then
  updates the knowledge graph (adding nodes/edges or updating timestamps on
  existing ones).
- **Workflow Orchestrator:** Coordinates background tasks and periodic jobs. For
  example, an Airflow DAG or Argo workflow might schedule nightly summarization,
  cleanup of stale info, or batched processing of accumulated novel facts.
- **Parallel Compute Layer:** Heavy computations (embedding generation,
  similarity calculations, bulk extractions) are offloaded to parallel
  frameworks. **JAX** may be used for GPU-accelerated vector operations or ML
  inference, while **Dask** can distribute tasks across a cluster for scale-out.
- **Persistence Layer:** Comprises various storage solutions – a graph database
  (e.g. Neo4j) for the knowledge graph, a relational store (PostgreSQL) for user
  data and logs, and possibly embedded analytics databases (SQLite/DuckDB) for
  intermediate or local processing. All are open-source.
- **Monitoring & Audit Logs:** Every memory update and important inference event
  is logged with metadata (timestamp, user, source of info, old vs new values)
  to enable auditability. A versioning scheme in the graph allows tracing how
  knowledge evolved over time.

### Table 1: Major Components and Technology Choices\*

| Component                       | Technology (Choice)                                | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Web API Layer**               | **Falcon (Python 3.13)**                           | HTTP API for chatbot integration; handles requests, auth, and session management. Falcon is lightweight and async-friendly, ideal for low-latency APIs.                                                                                                                                                                                                                                                                                                                                                                                |
| **Concurrency Model**           | **PEP 734 Subinterpreters**                        | Utilize Python subinterpreters to isolate user sessions or tasks. Each interpreter has its own GIL, enabling parallel execution on multiple cores for concurrent user requests without threading conflicts.                                                                                                                                                                                                                                                                                                                            |
| **Knowledge Graph Store**       | **Neo4j (Graph DB)** or similar                    | Stores the **knowledge graph memory** – nodes (entities) and edges (relations), with properties for timestamps, versions, etc. Neo4j supports graph queries (Cypher) and can index text and vectors for fast retrieval. Open-source alternatives: Apache AGE (Postgres extension), ArangoDB, or even an RDF triplestore.                                                                                                                                                                                                               |
| **Vector Index** (optional)     | **Built-in Neo4j index or Faiss/PGVector**         | For semantic similarity search. Neo4j 5+ supports vector indexing for nodes. Alternatively, use an external vector store (FAISS library or PostgreSQL with pgvector) to retrieve relevant documents or facts by embeddings.                                                                                                                                                                                                                                                                                                            |
| **LLM Generation**              | **Retrieval-Augmented Generation** pipeline        | Not a single tool, but the process: use an LLM (could be an open-source model or API) to generate answers using retrieved context. Integration via Python (e.g., HuggingFace Transformers or OpenAI API). In this architecture, the LLM call is made only after retrieving knowledge, to keep the number of LLM calls minimal for latency reasons.                                                                                                                                                                                     |
| **Novelty Detection Module**    | **Custom (NLP + ML)**                              | Code that decides if new information is novel enough to store. May use NLP (named entity recognition, keyword comparison) and embedding similarity to existing knowledge. Possibly implemented with spaCy or transformer models for NER, and embedding distance calculations (which could leverage JAX for speed).                                                                                                                                                                                                                     |
| **Entity & Relation Extractor** | **NLP Pipeline** (spaCy, Transformer-based NER/RE) | Analyzes text to extract structured data. For each novel piece of text (user utterance or document), it identifies entities (people, places, etc.) and relations between them. Could use pre-trained models or prompt an LLM to output triples. Runs either in real-time for critical info or in batch for accumulated data.                                                                                                                                                                                                           |
| **Orchestration**               | **Apache Airflow** *or* **Argo Workflows**         | Schedules and runs workflows for background tasks. **Airflow**: define DAGs in Python for tasks like daily knowledge consolidation, periodic re-computation (with time-based scheduling and dependency management). **Argo**: Kubernetes-native workflows (each step in a container), good for parallel jobs on K8s. Both handle retries, monitoring, etc.                                                                                                                                                                             |
| **Parallel Compute Framework**  | **JAX** and/or **Dask**                            | **JAX**: for numeric-heavy operations on CPU/GPU/TPU. JAX can compile and run vectorized computations with accelerators and parallelize across devices via `pmap` (useful for computing large batches of embeddings or similarity scores quickly). **Dask**: for general Python parallelism across a cluster. Dask’s distributed scheduler can manage complex task graphs with low overhead (~1ms per task) and scale computations to many workers, useful for data preprocessing, handling many simultaneous extraction tasks, etc.   |
| **Persistence (Relational)**    | **PostgreSQL** (primary RDBMS)                     | Stores metadata: user accounts, authentication info, and audit logs of interactions or memory changes. Also could store unstructured conversation history if needed (though large texts might be in object storage instead). Chosen for reliability and open-source availability.                                                                                                                                                                                                                                                      |
| **Persistence (Embedded)**      | **SQLite / DuckDB**                                | Used for lightweight storage in certain components: e.g., caching recent conversation data per user in an embedded DB for quick local access, or performing analytical queries on logs using DuckDB’s fast columnar engine. These are file-based and require no separate service, making them useful for on-the-fly analysis or local session state that can later be merged into the main DB.                                                                                                                                         |
| **Monitoring & Logging**        | **Audit Logs + Versioning**                        | Not a single product, but practice: Each update to the KG is logged (could be in Postgres or a log file). The knowledge graph itself implements **temporal versioning** – for example, edges have `t_valid` (start/end timestamps) to indicate when a fact was true. This way, updates don’t delete info but mark it as expired, preserving history. Tools like Prometheus/Grafana can be added for monitoring performance metrics (latency, throughput) in the K8s deployment.                                                        |

## Web API Service and Concurrency Model

**Falcon Web Service:** At the front end, we deploy a Python 3.13 service using
the Falcon framework. Falcon is a minimalist WSGI framework known for high
performance and low overhead, making it suitable for latency-sensitive
applications. The service exposes REST endpoints (or possibly WebSocket for
streaming responses) for chat interactions. Each request carries an
authentication token (e.g. JWT or OAuth2 bearer) that identifies the user; this
can integrate with an **MCP (Model Card Protocol or Model Context Protocol)**
style auth system or standard OAuth/OIDC tokens. The service validates the token
(potentially via an MCP server or OIDC provider) and then processes the request
on behalf of that user.

**Multi-User Isolation:** To support multiple users concurrently without
interference, the service will leverage **PEP 734 subinterpreters**.
Subinterpreters allow creating separate Python interpreter instances within one
process, each with its own Global Interpreter Lock and module state. We can
assign each user (or each session/conversation) to a dedicated subinterpreter.
This provides *isolation* (one user’s variables and memory won’t clash with
another’s) and allows true parallelism on multi-core CPUs since each interpreter
has its own GIL (thanks to PEP 684). For example, if two users make requests at
the same time, the Falcon app can spawn tasks in separate subinterpreters to
handle each, utilizing multiple cores in parallel. Communication between the
main server and subinterpreters would use the new `interpreters` module API (via
message queues or shared objects as per PEP 734 spec). This design avoids the
overhead of launching new processes per user request, while still maintaining
safety and concurrency. It is especially beneficial in Python 3.13+, as
subinterpreters and per-interpreter GIL provide a new concurrency model that
scales better than traditional threading.

**Request Lifecycle:** Upon receiving a chat query, the Falcon endpoint (running
in the main interpreter or a lightweight routing thread) will delegate the
request to a worker function possibly executed in a subinterpreter (from a
pool). That worker will carry out the RAG pipeline (detailed below) for that
user and return the response. Because each user’s state (e.g. cached memory or
last conversation turns) can be kept in the subinterpreter’s memory, context
switching is efficient. The server can reuse a subinterpreter for multiple
requests in the same session to exploit locality (similar to how threadpools
work, but now interpreter-pools). If subinterpreters were not available or
mature, an alternative is to run multiple Falcon worker processes (or Gunicorn
workers), or use asyncio with careful management; however, subinterpreters
present a cleaner model for multi-core utilization in our scenario.

**Authentication & Authorization:** The system will enforce that each API call
is authenticated. We mention MCP as an option – e.g., an MCP server could issue
tokens that tie a user to certain permissions on tools or memory. In practice,
any OIDC provider (Auth0, Azure AD, etc.) could be used to manage user
identities. The Falcon service would integrate with this (perhaps via
middleware) to extract user ID and roles from the token. All subsequent
operations (queries to the knowledge graph, etc.) will include the user context
to ensure isolation (for instance, queries might be filtered by user ID, or use
a user-specific subgraph). This ensures **multi-tenancy** – each user’s data
remains private to them (unless intentionally shared).

## Knowledge Graph Memory Store

At the core of the system is the **knowledge graph memory**, a dynamic store of
the information the chatbot knows about each user (and possibly general
knowledge relevant to them). We propose using a graph database like **Neo4j** as
the primary store for this memory. The knowledge graph will contain **nodes**
(entities such as people, places, concepts, or user-specific items) and
**edges** (relationships between entities, or between an entity and a piece of
information). For example, if a user says “I have a dog named Fido,” the system
might create a node for the user (or use an existing user node), a node for
“Fido” (with label Dog/Pet), and a relationship `OWNS_PET` or `HAS_DOG` linking
the user to Fido, with a property `name="Fido"`. This structured representation
allows semantic querying later (e.g. “What’s my dog’s name?” could be answered
by traversing from the user node to the pet).

**Entity & Relation Extraction:** To construct and update this graph, we need to
extract structured knowledge from unstructured inputs (chat messages,
documents). This is handled by an **NLP extraction pipeline**. When a new piece
of text is identified as novel (see next section), the pipeline will run one or
more methods: named entity recognition (to find proper nouns or key entities),
relation extraction (to determine how those entities relate), and possibly
coreference resolution (to connect pronouns or implicit mentions to the right
entities). We can use libraries like spaCy or Stanza for NER, or fine-tuned
transformer models for relation extraction. In some cases, we might prompt a
large language model with the text and ask it to output triples (subject,
relation, object) which can then be parsed. The output of this pipeline is a set
of candidate triples or nodes/edges to add to the graph.

**Graph Schema and Ontology:** The knowledge graph will have a schema (which can
be flexible but provides consistency). For example, we might have entity types
like `Person`, `Pet`, `Location`, `Item`, etc., and relation types like `OWNS`,
`FRIEND_OF`, `MENTIONED_IN`, etc. The system can start with a basic ontology,
and *dynamically extend it* as new types of relations appear (much like Graphiti
automatically labels edges and de-duplicates nodes). A minimal ontology ensures
that similar facts use the same relation names, aiding in querying. If custom or
domain-specific entity types are needed, the system allows adding them (either
automatically or via configuration).

**Versioning and Temporal Data:** A crucial aspect is that the knowledge graph
memory is **temporal and versioned**. We do not simply mutate or overwrite facts
blindly; instead, each piece of knowledge is timestamped. We adopt a
**bi-temporal model** similar to what Graphiti uses: every relationship (edge)
can have `t_valid_start` and `t_valid_end` properties representing the validity
interval of that fact in the real world, and the system also records
`t_ingested` (when it was learned). For instance, if the user’s job title is
stored and later the user says they changed jobs, the relation
(`USER -[HAS_JOB]-> CompanyX`) would get an end timestamp (marking it expired as
of the change date) and a new edge (`USER -[HAS_JOB]-> CompanyY`) is added with
a start timestamp from now. This approach **preserves history** – one can query
the graph “as of” a past date to see what the system knew then, and it avoids
simply deleting data. Neo4j doesn’t natively version data, but we implement it
at the model level (similar to event sourcing). Community plugins like
`neo4j-versioner-core` can assist in automating some of this, but we assume a
custom implementation for full control. Each entity can also have versions or
state nodes (if needed, we separate an “entity identity” node from “entity
state” node that carries time-bounded attributes, linking them with temporal
edges). This complexity ensures that *auditability* is built-in: we never truly
lose information, and can trace how a piece of knowledge changed over time.

**Querying the Knowledge Graph:** The chatbot will query the graph to retrieve
relevant information during a conversation. There are multiple query modes:

- **Direct graph traversal:** If we know the user is asking about a specific
  entity (e.g. “my dog” implies the user’s pet), we can directly traverse the
  graph (using a Cypher query or a parameterized traversal) to fetch the facts
  needed (like find the node representing the user, then find their outgoing
  `HAS_DOG` relationship). This is extremely fast (constant time for indexed
  lookups or local traversals) and does not require any model call at runtime.
- **Semantic search (embedding-based):** If the question is more abstract or
  doesn’t directly mention a known entity, we can perform a semantic similarity
  search. The system maintains an **embedding index** of content in the
  knowledge graph – for example, each node or each fact triple can be associated
  with a vector (obtained by encoding the text of that fact or a description of
  the node via a sentence transformer or similar). When a query comes in, we
  encode the query to a vector and find the nearest neighbors in that vector
  index. This helps retrieve relevant facts even if the wording differs. Neo4j
  supports storing vector embeddings in node properties and indexing them for
  similarity search. Alternatively, an external vector search library (FAISS,
  Weaviate, etc.) could be used, but leveraging Neo4j keeps everything in one
  system.
- **Keyword or full-text search:** For certain queries, a classic keyword search
  might suffice or be more appropriate (especially if the knowledge includes
  text notes or documents). Neo4j has a full-text indexing (using Lucene) that
  can be used to match text efficiently. For instance, if the user asks “What
  did I say about Paris last week?”, a full-text search on the knowledge graph’s
  stored conversation snippets for “Paris” could find the relevant node or
  relationship where Paris was mentioned.
- **Hybrid querying:** The best results often come from combining approaches. As
  noted in Zep AI’s Graphiti, they use a hybrid of semantic, keyword, and graph
  search to quickly pinpoint relevant knowledge. Our system can do the same:
  e.g., first attempt to identify any entity mentions in the query (via NER or
  direct string match to node names). If found, retrieve those subgraphs. In
  parallel, do an embedding similarity search to catch non-obvious connections.
  Also do a keyword search for any rare terms. The results (multiple candidate
  pieces of info) can be merged and ranked (perhaps using a learned relevance
  ranker or simply heuristics).

All these queries are made extremely fast by using indexes and avoiding LLM
calls in the retrieval stage (the LLM is only used for final answer synthesis).
Graph databases like Neo4j are optimized for such traversals and index lookups,
yielding sub-second responses even for large graphs. In fact, Graphiti reports
*95th-percentile query latencies around 300ms* by using these techniques. This
ensures the retrieval-augmented generation step does not bottleneck the
chatbot’s responsiveness.

**Memory Partitioning (Per-User Graphs):** Since the system must support many
users, we need to partition or isolate each user’s knowledge data. There are a
few strategies:

- Use a **single multi-tenant graph**: Have a property on each node and edge
  indicating which user(s) it belongs to. Every query and update then filters by
  the user’s ID. This is simple but all data resides in one database/graph
  instance. We must ensure queries are always scoped, to prevent any leakage.
  Performance could degrade if the graph becomes huge with many users’ data
  mingled (though proper indexing and perhaps sharding by label or property can
  mitigate).
- Use **separate graph databases or keyspaces** per user: Neo4j Enterprise
  supports multi-database, or we could run multiple Neo4j instances (one per
  user, or per group of users). This gives strong isolation at the cost of more
  resources and management overhead. Given open-source constraints, running one
  instance per user is not feasible for large user counts, but per-user *graphs*
  in a single instance might be an option (if the DB supports switching graph
  contexts).
- Use **user-specific subgraphs** within one DB: We can maintain separate
  subgraphs (with perhaps a top-level “User” node for each user, and all their
  personal knowledge connected under that). This is a hierarchical separation
  that makes it easy to extract one user’s data (traverse from their root node)
  and also ensures no cross-user edges unless explicitly desired. This approach,
  combined with filtering by user ID on queries, is likely sufficient. The
  subinterpreter in the web layer can also cache the user’s subgraph in memory
  (e.g., as a Python NetworkX graph for quick lookups of very frequent queries,
  syncing with Neo4j periodically).

Given the above, the recommended approach is a **single Neo4j instance** that
holds all users’ knowledge graphs, with a top-level partition by user. This
minimizes operational complexity (only one DB service to maintain), and Neo4j
can handle millions of nodes/edges which is likely enough for many users’ data
combined. Sensitive information isolation is enforced in the query layer and by
not creating edges across users unless explicitly allowed (e.g., if the system
has some shared global knowledge, it could reside in a common area of the graph
that all users have read access to, but personal data stays separate).

## Novelty/Surprise Detection and Memory Update Strategy

A core innovation in this system is the **novelty or surprise detection
module**, which decides when incoming information warrants an update to the
knowledge graph memory. In Natural Language Processing, *“Novelty Detection
refers to finding text that has some new information to offer with respect to
whatever is earlier seen or known.”* In our context, we continuously compare new
inputs (or new external knowledge) against the contents of the knowledge graph
to identify truly new facts (as opposed to repetitions of known info). This
prevents unnecessary updates and focuses resources on integrating novel
knowledge.

**Mechanism of Novelty Detection:** When a user sends a message or when the
chatbot is about to generate a response (which might include new info gathered
via tools), the system performs the following:

- **Entity Novelty:** Identify named entities in the text. If an entity (e.g., a
  person’s name, a company, a pet, etc.) is not currently present in the user’s
  knowledge graph, that’s a strong signal of novelty. For instance, the first
  time a user mentions “Fido” or “Acme Corp”, those would be novel entities.
- **Relation Novelty:** Even if entities are known, the particular relationship
  or fact might be new. For example, the user had mentioned Alice and Bob
  before, but now says “Alice is Bob’s boss,” which is a new relation between
  previously known entities. We can detect this by checking if a similar edge
  exists in the graph (perhaps via a Cypher query like “MATCH (Alice)-[r]->(Bob)
  RETURN type(r)”). If no such relationship exists, this is novel.
- **Linguistic Novelty:** If the input is a statement or explanation, we might
  measure how similar the sentence is to any stored sentences/notes in the graph
  (using embedding cosine similarity). A low similarity (below a threshold)
  indicates the sentence has information not covered before. Additionally, we
  can use surprise metrics like *information gain*. For example, represent the
  knowledge graph or user’s known info as a vector of features or topics, and
  see if the new input significantly changes that representation (this is akin
  to “representation edit distance” novelty detection, though implementing that
  might be complex in real-time).
- **Anomaly or OOD detection:** Techniques from out-of-distribution (OOD)
  detection can be applied: have a model of what kind of content is expected
  given the user’s history and general knowledge, and flag content that is
  statistically unlikely (which could either be highly novel knowledge or a sign
  of something off-topic). However, in chatbots, conversations can shift topics
  freely, so a simpler approach focusing on knowledge novelty
  (entities/relations) is more practical.

The **novelty threshold** is a configurable parameter (or set of parameters)
that determines how “new” something must be to trigger immediate integration.
For example, we might require that either a brand new entity is mentioned, or
that an embedding similarity score to existing knowledge is below e.g. 0.8
(meaning the new info is sufficiently different). If the content doesn’t meet
the threshold (say it’s a rephrasing of known info or a trivial variation), the
system might choose not to create a new entry (to avoid clutter and duplicates).
It could still log the occurrence for frequency tracking or future analysis.

**Immediate vs Batch Updates:** Not all novel information needs to be ingested
into the KG immediately; some can be deferred to batch processing to optimize
performance. We define two pathways:

- **Immediate Update Path:** If the novelty is **high** (e.g., a completely new
  entity or a critical fact the user is likely to query soon), the system will
  trigger an update right away. In practice, as the chatbot is responding (or
  just after sending a response), it can spawn a background job (using an
  asynchronous task or an event) to run the extraction pipeline for that single
  piece of info and update the graph. This could be done via a lightweight task
  queue or simply a background thread (or subinterpreter) that doesn’t block the
  main response. The result is that within a few seconds, the new fact is in the
  memory. So if the user immediately asks a follow-up that requires that
  knowledge, it will be there. This path trades a bit of extra work (NLP
  extraction) per message for up-to-date memory.
- **Deferred Batch Path:** If the novelty is **low or moderate**, or if the
  system is currently under heavy load, the new info can be appended to a
  “to-be-processed” queue. Then, at a scheduled interval (say every hour or
  night), a batch job will go through accumulated new pieces and integrate them.
  This approach is efficient because the extractor can run on a batch of data at
  once (benefiting from vectorized processing or parallel processing via Dask)
  and possibly do global optimizations (like merging similar entries, removing
  duplicates across users, etc.). The downside is the knowledge graph won’t
  reflect those new facts until the batch job runs. We mitigate this by using
  the immediate path for things likely to be needed soon.

The decision of which path to take can be based on a *novelty score*. For
instance:

- Assign a score 0 to 100 for how novel/surprising an input is (perhaps based on
  number of new entities, new relations, and dissimilarity measure).
- Have a threshold (e.g., 70): if score ≥ 70, do immediate update; if 30 ≤ score
  < 70, schedule for batch; if < 30, likely redundant or unimportant, maybe just
  ignore or log it but don’t store.

This thresholding strategy ensures we **retain new information and filter out
redundant information**, as the NLP novelty detection definition suggests. The
threshold values and scoring method might be tuned over time (perhaps via
experiments or even a learning-based approach using feedback).

**Surprise-Based Triggers:** The term *surprise* in cognitive systems often
refers to an unexpected observation that conflicts with current beliefs. Our
system can treat a **conflict** as a kind of surprise. For example, if the user
says something that contradicts the knowledge graph (e.g., previously we stored
that the user’s car is a Tesla, now they say “I drive a Ford”), this is a
surprise event. In such cases, the system should definitely update the memory
(mark the old info as outdated and add the new info). It might even choose to
acknowledge or clarify in conversation (though that’s a higher-level dialogue
policy issue). Surprise detection can be done by checking for contradictions: if
the extraction pipeline finds a fact that matches an entity already in graph but
with a different value (like different car make), that’s a conflict. The update
logic in the KG will then **invalidate** the old relationship by setting its
`t_valid_end` to now and add the new one as current. This process ensures
consistency in the long run, while also preserving the old info with an
invalidation timestamp for audit/history.

**Orchestration of Updates:** We use the workflow orchestrator (Airflow/Argo) to
manage the batch update jobs and possibly the immediate ones as well. For
immediate updates, a full heavyweight orchestrator might be bypassed (too much
overhead for a single task); instead, the Falcon app could directly enqueue a
task (e.g., put a message in a Redis queue or trigger a Celery/Dramatiq worker).
However, one modern approach is to use Argo Workflows even for event-driven
tasks: one can programmatically submit an Argo workflow CRD to the cluster when
needed. Since Argo is K8s-native, this will spin up the necessary pods to handle
the extraction and update, then terminate. This is a bit heavier than
in-process, but gives the benefit of isolation and scalability (and the Argo
workflow could encapsulate a multi-step process: extract -> validate -> upsert
to DB). In contrast, Apache Airflow is more suited for periodic scheduling. We
can define DAGs for things like “Nightly knowledge graph maintenance” which runs
at 2am every day, iterating through the day’s new data. Airflow’s scheduler will
ensure these run reliably. Airflow can also trigger DAGs on events (using
sensors or an API call), so we might use Airflow for both scheduled and
event-driven if we want to consolidate.

**Scheduling and Frequency:** A possible schedule for batch updates might be:

- Minor novel info: batch every hour (to limit staleness to at most an hour for
  not-so-critical info).
- Major re-computation tasks (like summarizing long conversation histories into
  concise knowledge, or re-indexing the entire vector store): nightly or weekly.
- Conflict resolution audits: e.g., a daily job to detect any inconsistencies or
  duplicates in the KG and resolve them (though Graphiti’s incremental approach
  handles conflict at insert time, it’s good to have a safety net job).
- Backup and version snapshots: weekly or monthly, dump the KG (could use
  Neo4j’s dump or write certain subgraphs to file) for backup and potential
  rollback.

This strategy embodies a **novelty-driven memory update policy** – an idea that

- **High Novelty (surprise)**

  - *Action:* Immediate update via extraction and graph upsert.
  - *Frequency/Latency:* Real-time or on demand.
  - *Pros:* Memory stays current; user queries reflect new info quickly.
  - *Cons:* Overhead per message; bursty updates may need rate limiting.

- **Moderate Novelty**

  - *Action:* Queued for batch processing (e.g., within an hour).
  - *Pros:* Batching amortizes cost; optimized NLP can be used.
  - *Cons:* Graph not immediately updated; ensure medium-term info isn't lost.

- **Low Novelty (redundant or trivial)**

  - *Action:* No immediate update; maybe log frequency or update counters.
  - *Pros:* Avoids cluttering the graph with irrelevant data.
  - *Cons:* Detection mistakes could drop important info. the system’s memory
    should evolve primarily when truly new knowledge is encountered, much like
    human memory encodes new events and not every redundant detail. It’s worth
    noting that novelty detection itself can be an *open-world problem*; the
    system might encounter entities not just new to the user but completely
    unknown globally. In such cases, external knowledge bases or web search
    could be invoked to verify or enrich the information (though that’s beyond
    our current scope, it could be a future extension: e.g., if a user mentions
    a new movie, the system might search a movie database to get more details
    for the KG).

## Retrieval-Augmented Generation (RAG) Pipeline

Once the knowledge graph is populated and kept up-to-date via the above
mechanisms, the chatbot can leverage it during conversation via a
Retrieval-Augmented Generation pipeline. The pipeline steps for each user query
are:

1. **Query Analysis:** When a user asks something, the system first analyzes the
   query for intent and entities. For example, if the user asks, “What’s my
   dog’s name and where did I buy my car?”, the system identifies the topics:
   “dog’s name” and “where car was bought”. It maps “my dog” to an entity (the
   user’s dog, likely a Pet node) and “my car” to the user’s Car entity.

2. **Knowledge Retrieval:** Using those cues, the system queries the knowledge
   graph. Following the example:

   - It finds the user’s Pet node (via the user->HAS_DOG edge) and retrieves the
     name property (Fido).
   - It finds the user’s Car node (HAS_CAR edge) and then finds a relation like
     PURCHASED_AT or DEALERSHIP linking the car to a location or seller,
     retrieving that info.
   - If the query was less direct, e.g., “tell me about Alice,” the system would
     search for an “Alice” connected to the user or in general knowledge, gather
     facts about Alice (like her relations to user, her attributes).
   - It may retrieve not just atomic facts but also short text notes stored in
     the graph (the graph nodes could have a “description” property or attached
     documents from previous conversations).
   - The retrieval component aims to gather a concise set of relevant facts
     (perhaps a few sentences or data points) that can help answer the question.

3. **Context Construction:** The retrieved knowledge is then formatted into a
   context that the LLM can understand. This could be as simple as a text
   snippet: e.g., “You (the user) have a dog named Fido. You bought your car (a
   Tesla Model 3) at **SuperCars Dealership** in 2021.” We might also add some
   instructions or a system prompt that this is trusted knowledge from memory.

4. **Generation (LLM invocation):** We then feed the composed context plus the
   user’s question into the language model for answer generation. This could be
   done via a prompt like:

   ```text
   System: Here are some known facts: "User has a dog named Fido. User bought their car at SuperCars Dealership." 
   User: What's my dog's name and where did I buy my car?
   Assistant: 
   ```

   The LLM (running either locally or via an API) will produce an answer using
   those facts, e.g., “Your dog’s name is Fido, and you bought your car at
   SuperCars Dealership.” If the LLM is instructed properly, it should rely on
   the provided info and not hallucinate. Since we use **RAG**, the heavy
   lifting of factual recall is done by the retrieval from the KG, ensuring the
   answers are grounded in the stored knowledge.

5. **Post-Processing and Citing Memory:** (Optional) The system could also
   explain or cite which memory was used. This could be included in the answer
   or logged for traceability. For example, in an interface, it might highlight
   that “Fido” came from memory entry X. However, typically for user-facing
   answers, the assistant will just answer directly unless a special debug mode
   is on.

**Latency Considerations:** The RAG pipeline is optimized for low latency:

- The query analysis (step 1) is a quick NER/tagging operation.
- Knowledge retrieval (step 2) is designed to be sub-second by using database
  indexes (graph traversals and vector searches are all done on the Neo4j server
  or a local index). By avoiding an LLM call during retrieval, we save the
  overhead of one or more model invocations (in contrast, some multi-step RAG
  pipelines call an LLM to refine queries or summarize chunks – we avoid that
  here to keep it fast).
- The LLM generation step is typically the slowest (depending on model size and
  output length). To minimize perceived latency, one could stream the LLM’s
  response to the user as it is generated (if using a model that supports
  streaming tokens). Also, if using an open-source model, running it on a GPU
  with an optimized library (like FasterTransformer or quantized models) helps.
  The context length needed is not huge since we only insert relevant facts, so
  we remain within a manageable token count.
- Overall, our retrieval adds only a few hundred milliseconds overhead (or less)
  thanks to the efficient memory layer, so the dominant factor remains the LLM’s
  generation speed. The user should experience a fast, accurate response
  enriched with their personal or contextual knowledge.

**Handling Missing Knowledge:** If the user asks something that the knowledge
graph doesn’t have (e.g., truly new question), the RAG system could fall back to
some default behavior:

- The assistant might say it doesn’t have that information or might ask a
  follow-up question to get the info (which it would then treat as novel and
  store).
- Alternatively, if connected to external info sources (web search, etc.), it
  could attempt to fetch an answer from outside and then potentially store it if
  relevant. (This however introduces complexities of trust and permission,
  especially in personal assistant scenarios.)

For our architecture, we focus on the personal/enterprise knowledge aspect. The
design ensures that if knowledge exists, it will be found quickly. If not, the
novelty detection comes into play (the question itself might be an implicit
indication that a knowledge gap exists, which could be logged so that if the
answer is found later, it can inform the user).

## Background Workflows and Orchestration

Beyond the real-time interactions, the system requires various **background
workflows** to maintain and enhance the knowledge graph and overall performance.
We propose using either **Apache Airflow** or **Argo Workflows** for
orchestrating these tasks:

**Apache Airflow:** Airflow allows defining workflows as DAGs in Python, with
scheduling (cron-like or complex time rules) and dependency management. It’s
well-suited for periodic jobs and can run on Kubernetes with an executor that
launches tasks in pods. For example, we can create an Airflow DAG for “Daily
Knowledge Graph Maintenance” that has tasks like:

- Export a snapshot of the graph (for backup).
- Run consistency checks (verify no duplicate nodes for the same real-world
  entity, ensure indexes are okay, etc.).
- Compute any analytic metrics (e.g., which facts were most referenced, or
  identify stale facts that haven’t been referenced in a long time for potential
  pruning or summarization).
- Possibly re-embed all node descriptions if we updated the embedding model or
  to combat vector drift.

Airflow’s scheduler will run this DAG daily at off-peak hours. Another DAG might
be “Batch integrate queued knowledge” that runs every hour, picks up the queued
novel info, processes them, and updates the graph for each user in the batch.
Airflow gives us a UI and logs for monitoring these jobs, and we can set alerts
if any task fails.

**Argo Workflows:** Argo is a container-native workflow engine that fits well in
Kubernetes environments. Workflows are defined in YAML (or via Python SDKs) and
run as custom resources on the cluster. Each step is a container execution,
which could be our application’s container with a specific entrypoint. Argo
excels at parallel tasks: for instance, if we want to process each user’s
updates in parallel, Argo can dynamically fan-out a step to N parallel pods (one
per user or per chunk of data). It’s also easy to trigger Argo workflows on
demand (through Argo’s API or events) and to incorporate them into CI/CD or
event-driven architectures.

For example, an Argo workflow for integrating new knowledge might have steps:

1. Generate tasks: a step that queries the staging table for new info and
   generates one sub-task per item or per user.
2. Parallel step: multiple tasks run concurrently, each extracting and updating
   a portion of the graph (with proper transactions to avoid conflicts).
3. Final step: aggregate results, log summary (e.g., “10 new entities added, 5
   relations updated”).

Argo could also be used for model serving workflows, such as deploying a new
version of an embedding model and re-indexing vectors (each step as a container
performing part of the process).

**Choosing Airflow vs Argo:** Both tools overlap in functionality. If our team
is more comfortable writing Python and wants a rich scheduler with backfill,
etc., Airflow is great. If we prefer Kubernetes-native, lightweight, and mostly
container-based tasks, Argo is appealing. Since the requirement explicitly
allows either, one could even use *Airflow to schedule Argo workflows* (there
are ways to trigger Argo from Airflow tasks), but that might be overkill. For
this architecture, it suffices that we have a robust orchestration solution for
background jobs – the exact choice can be based on the deployment environment.
AKS/EKS support both; Airflow can be deployed via helm chart, and Argo via its
controller installation.

**Integration with the rest of the system:** The orchestrator will need access
to the data stores and possibly to some of the same code as the web service (for
extraction logic). To avoid code duplication, we can package the extraction &
update code as a module or script that both the web app and the workflow tasks
can call. For example, have a CLI script `update_knowledge.py` that takes a user
ID and a piece of text and performs the steps to update the graph. The Airflow
task or Argo container can run this script in batch over multiple inputs. The
workflow tasks will use the same databases (Neo4j, Postgres, etc.), so proper
locking or transaction management is important. Neo4j supports ACID
transactions; if multiple updates happen in parallel (which can under Argo), the
database will handle them with transaction isolation. We should design our graph
update queries to be **idempotent** or upsert-like (e.g., create node if not
exists, update if exists) to handle potential retries or concurrency.

**Example Workflow – “Novel Info Batch Ingestion”:**

- **Schedule:** Every hour at :00 (or triggered if queue length exceeds a
  threshold).

- **Steps:**

  1. **Extract Batch:** A task retrieves all new info records from the temporary
     store (could be a Postgres table `new_facts_queue` where each entry has
     user_id, text, timestamp).

  2. **Fan-out per User:** The next step dynamically splits by user (group the
     records by user to localize transactions). Each parallel task handles one
     user’s batch:

     - It loads that user’s current knowledge subgraph (if needed, or just uses
       DB queries on the fly).
     - For each new info piece, runs entity/relation extraction (this can be
       parallelized internally too, e.g., using `dask.delayed` to process
       multiple sentences concurrently on a worker).
     - Prepares Cypher queries to merge the new nodes/edges.
     - Executes the queries on Neo4j (ensuring to set timestamps and handle
       conflicts as needed).
     - Marks the entries as processed in the queue.

  3. **Post-process:** After all users are done, one final task might rebuild or
     update the full-text and vector indexes (if Neo4j doesn’t auto-index on the
     fly for new entries, we might trigger an index rebuild or at least ensure
     new embeddings are computed and added – possibly the extraction task itself
     computes embeddings for new text and stores them).

  4. **Completion:** Log summary and send metrics (like number of new nodes, any
     errors).

This workflow would ensure that even if immediate updates were skipped, within
an hour the KG is updated.

Another workflow might be **“Knowledge Graph Summarization & Cleanup”:** Over
time, a user’s memory might grow very large (hundreds of facts). Some facts
might become less relevant (e.g., ephemeral conversation details) or could be
summarized. This periodic job could:

- Identify nodes or clusters of info that have not been referenced in recent
  queries.
- Either archive or compress them (e.g., if there are 50 chat messages about a
  brainstorming, perhaps summarize into 5 key points and store that instead,
  linking the raw data elsewhere).
- Remove or flag any inconsistencies (if two contradictory facts exist without
  proper temporal markers, resolve them).
- Ensure the graph doesn’t violate any constraints (like uniqueness of certain
  node properties for an entity type).
- Possibly engage an LLM to categorize or tag knowledge for easier retrieval
  (adding metadata).

While not explicitly required, including this highlights the need for
**long-term maintenance** of the memory, analogous to how humans forget or
compress memories over time.

## Parallel and Distributed Computing with JAX and Dask

To meet the performance and scalability requirements, we integrate **parallel
computing frameworks** into the architecture. Both **JAX** and **Dask** can be
utilized in complementary ways:

**Use of JAX:** JAX is a high-performance numerical computing library that
brings XLA compilation and autograd to Python. In our system, JAX is
particularly useful for operations like:

- **Embedding Computation:** Suppose we use a transformer model to compute
  embeddings for sentences or entities. If that model is implemented in JAX (or
  if we use something like Sentence-Transformers with a JAX backend), we can
  take advantage of JAX’s just-in-time (JIT) compilation to batch-process many
  texts at once, and run on GPU/TPU. JAX will seamlessly utilize available
  hardware accelerators, which is crucial for quickly embedding potentially
  thousands of pieces of text during large updates.
- **Similarity Calculations:** If we want to compute pairwise similarity or
  other matrix operations as part of novelty detection or retrieval (for
  example, to compute a novelty score, we might compute distances between a new
  embedding and a set of existing ones), JAX can do this with ease, exploiting
  vectorization. Instead of looping in Python, we hand a vectorized function to
  JAX and let it compute many similarities in parallel. Moreover, if multiple
  devices are available (say multiple GPUs), JAX’s `pmap` can distribute the
  computation across them, effectively doing data-parallel computation which
  accelerates large workloads.
- **Model Inference:** If down the line we incorporate any learned models for
  tasks like NER, sentiment, or even a small generation model, JAX can be used
  (with libraries like Flax or Haiku for neural network definitions). Given
  JAX’s focus, it’s ideal for batch processing in training or inference where we
  can compile a function for repetitive use.

One thing to note is that JAX works best for pure array operations and might
require rewriting some Python logic into JAX-friendly form. We’ll use it in
performance-critical paths (like the math heavy parts: embeddings, vector math).
For the more procedural logic (like traversing graph structures or orchestrating
tasks), normal Python is fine.

**Use of Dask:** Dask complements JAX by handling **distributed task
scheduling** and general parallelism in Python. Dask allows us to scale out to a
cluster of machines if needed, and to parallelize irregular workloads (not just
array computations). Key uses:

- **Parallel NLP on multiple texts:** When doing batch extraction for many users
  or many documents, we can use `dask.delayed` or Dask dataframes to distribute
  the work. For instance, splitting 1000 new sentences across 4 worker pods to
  process concurrently (each doing NER/RE and DB updates). Dask’s scheduler is
  low-latency, with tasks incurring only ~1ms overhead, so it can handle
  fine-grained tasks efficiently. It also supports **dynamic task graphs**,
  meaning we can have workflows with dependencies that Dask resolves (similar to
  Airflow/Argo but at a programming level).
- **Scaling Web Workers:** If we needed to scale beyond subinterpreters in one
  process, we could run multiple replicas of the Falcon API, and potentially
  coordinate them via a Dask cluster (though typically a simpler load balancer
  is enough for web requests). More interestingly, if an API request itself
  might require parallel work (e.g., answering a question by querying multiple
  data sources in parallel), using Dask even within the request can speed it up.
  But one must be careful not to introduce too much overhead for a single short
  request.
- **Data aggregation and analytics:** Dask can be used for analyzing accumulated
  conversation data or usage logs, e.g., to compute statistics or to
  train/update any models. DuckDB or pandas can be too slow for huge data on one
  machine, so Dask DataFrame can distribute the data processing.
- **Integration with Airflow/Argo:** We could also leverage Dask as an execution
  backend for Airflow tasks (Airflow can offload tasks to a Kubernetes pod where
  Dask client runs, connecting to a Dask cluster). Or in Argo, one step could be
  “spin up a Dask cluster” to handle a particularly large job, then shut it
  down. However, maintaining a persistent Dask cluster (e.g., via Dask
  Kubernetes Operator) might be simpler, so that whenever needed, tasks can be
  dispatched to it.

**Example – Parallel Extraction with Dask:** Imagine the batch ingestion
workflow retrieved 10,000 new fact sentences to process. We can use Dask to
parallelize the NER and relation extraction. We’d create a Dask client (possibly
running in the orchestrator environment or as part of a worker container). We
then do something like:

```python
import dask
from dask.distributed import Client
client = Client(...)  # connect to Dask scheduler
results = []
for sentence in new_sentences:
    future = client.submit(process_sentence_to_triple, sentence)
    results.append(future)
triples = client.gather(results)
```

This will farm out the `process_sentence_to_triple` function to many workers.
Each worker could even use JAX inside to speed up part of its work (though NER
is not easily done in JAX; more likely we’d use transformer models via Hugging
Face which might not be JAX-based yet. However, we could still benefit from GPU
by using PyTorch on each worker if available). Once gathered, we then do batch
DB writes (maybe also parallelized – Neo4j can handle concurrent writes, but we
might choose to do a single transaction for all of a user’s data to ensure
consistency).

**Resource Management:** Running JAX and Dask means we should allocate
appropriate resources in the Kubernetes cluster:

- Likely we’ll have a **GPU node pool** for tasks that use JAX (for example, an
  Airflow/K8sPodOperator or an Argo step that runs embedding calculation could
  request a GPU resource).
- We might have a dedicated set of **Dask worker pods** possibly on CPU nodes
  for general tasks, and some on GPU nodes if needed for ML tasks. Dask’s
  scheduler can be containerized as well.
- Alternatively, some tasks can use **Ray** (another parallel framework) but
  since the requirement specifically mentions JAX and Dask, we stick to those.

**Concurrency vs Parallelism:** It’s worth distinguishing:

- The Falcon API with subinterpreters gives us concurrency for serving multiple
  users at the same time (I/O-bound and some CPU-bound tasks in parallel).
- JAX and Dask give us *parallelism* especially for CPU/GPU heavy jobs (which
  often are the background tasks or large-scale operations). This ensures that
  even if one user triggers a big update, it can be distributed and not hog the
  main thread, and also that our system can scale to handle many such updates or
  queries if needed.

In summary, **JAX accelerates internal computations** (especially ML-related
ones) by using hardware efficiently and providing advanced features like JIT
compilation and automatic differentiation (useful if we ever implement
learning/adaptation in the system). **Dask scales out the workload** across
multiple workers/machines, allowing the system to handle large volumes of data
and multitask operations concurrently in the backend. Together, they help
maintain **low latency for the user** (by offloading work) and **high throughput
for processing** large amounts of knowledge data.

## Data Persistence and Storage Choices

The system uses a combination of storage technologies, all open-source, each
chosen for specific types of data and workloads:

- **Graph Database (Neo4j):** As discussed, Neo4j is the primary persistent
  store for the knowledge graph memory. It excels at managing interconnected
  data and executing graph queries (like traversals or pattern matching
  queries). Community Edition of Neo4j is open-source and can be used if we
  don’t need clustering; if high availability is needed, we might consider Neo4j
  Enterprise (which is free for development but paid for production) or an
  alternative like **JanusGraph** (open-source graph database on top of
  Cassandra or BerkeleyDB) or **ArangoDB** (multi-model DB with graph support).
  However, Neo4j’s rich ecosystem (APOC procedures, full-text search, upcoming
  vector indexing) makes it a strong choice. The data stored includes all
  entities, relationships, properties (attributes), timestamps, etc. We also
  store some textual information in the graph (for example, a note or
  description node that contains raw text from the user’s input if needed to
  have the context for a fact).

- **Relational Database (PostgreSQL):** Even though the core knowledge is in a
  graph, an RDBMS is useful for other structured data. We use PostgreSQL to
  store **user profiles** (username, auth info, preferences), and **system
  metadata** such as logs of conversations or prompts (if needed for audit), or
  a table of “novelty queue” entries awaiting batch processing. Postgres could
  also store embeddings (via the `pgvector` extension) if we decided not to use
  Neo4j for vector search. However, maintaining the same data in two places is
  undesirable, so likely we’d either use Neo4j or Postgres for that but not
  both. The relational store also provides an easy way to integrate with other
  systems or run analytical SQL queries outside of the graph context (sometimes
  writing SQL is more straightforward for certain reports than Cypher on a
  graph).

- **Document/Blob Storage:** Not explicitly mentioned in requirements, but if
  users upload files or if we have large text documents to integrate, we might
  need a blob storage (like files in S3 or Azure Blob, or an on-prem MinIO).
  References to those documents could be stored in the knowledge graph (as nodes
  with a file path property) but the content itself kept in blob storage to
  avoid bloat. This is only relevant if our chatbot ingests documents or images
  etc. For now, we assume mostly text input.

- **Embedding Store:** If using an external vector database is not desired (to
  keep everything free and simple), we have a few options:

  - Use **Neo4j** itself: store each embedding as an array property on a node
    and create an index. Neo4j has introduced native vector similarity search in
    recent versions.
  - Use **Faiss** (Facebook AI Similarity Search): an in-memory vector index
    library (C++ with Python bindings) which can be used within our application.
    We could maintain an up-to-date Faiss index of all embeddings. If the
    dataset is not huge (e.g., a few hundred thousand vectors, which might be
    fine in memory), Faiss can give millisecond similarity queries. We’d need to
    persist the Faiss index to disk periodically (Faiss can save to a file) so
    that it can be reloaded on service restart. Alternatively, rebuild the index
    from the graph DB on startup (compute embeddings for each node – which might
    be heavy if many).
  - Use **Postgres+pgvector:** This gives a persistent, albeit slightly slower,
    vector similarity search. The advantage is everything remains in Postgres
    (which we already have). The disadvantage is that graph data is in Neo4j, so
    cross-database coordination is needed (unless we double store some data).
    One approach could be: each time we add a node to Neo4j, also store a row in
    Postgres with `node_id`, `text`, `embedding`. This is duplication but might
    be acceptable for simpler querying via SQL if needed.

  Given the focus on open-source and avoiding complexity, using Neo4j’s own
  indexing for both text and vectors is appealing – it centralizes search
  functionality in one system.

- **SQLite and DuckDB:** These embedded databases are not central to the
  architecture but serve niche purposes:

  - **SQLite:** Could be used in a couple of ways. We might have a local SQLite
    DB on each server instance to cache some data (for example, caching recent
    queries and their answers for quick retrieval if repeated, or caching
    partial results of computations). SQLite’s file can reside on a node’s disk;
    if the pod dies the cache can be lost, but that’s usually okay. SQLite is
    also a handy way to ship a small database of reference data with the app if
    needed (though not in our case, but perhaps for a small ontology or a
    config).
  - **DuckDB:** DuckDB is an embedded analytics database (columnar, similar to
    having a local data warehouse). It can be used for analytic queries on data
    that’s too slow in Postgres or Neo4j. For instance, if we log every user
    question and some metrics, and want to do a quick analysis of all logs to
    find patterns, dumping the log to a CSV and querying in DuckDB might be
    faster and easier. DuckDB can directly query Parquet files or in-memory
    data. It’s not a service; it runs in-process, so it could be invoked in a
    Jupyter notebook or a maintenance script for one-off analysis. In
    production, we might not use DuckDB heavily, but it’s an option for data
    science tasks on the side.

All these storage components would be deployed on Kubernetes with persistent
volumes as needed:

- Neo4j would use a **StatefulSet** with a persistent volume to store the graph
  database files. We must also plan backups (either use Neo4j’s backup tool or
  snapshot the volume).
- Postgres could be a single instance (StatefulSet) or we could use a managed
  service (RDS, Cloud SQL) if allowed, but since requirement is open-source, we
  assume a containerized Postgres with a persistent volume.
- For reliability in production, one might consider clustering or replication
  (Patroni for Postgres, causal clustering for Neo4j), but that adds complexity.
  Initially, a single-instance of each (with failover strategy at infra level
  perhaps) is fine.
- The application itself is stateless aside from caches, so scaling it is easy
  (multiple pods behind a service). The orchestrator will also be deployed
  (Airflow in its pods, or Argo controller, etc.). The Dask cluster, if
  persistent, would have a scheduler and multiple worker pods, which can scale
  on demand (auto-scaler can add workers if queue grows).

## Auditability and Traceability

To meet the requirement of auditability, the system incorporates several layers
of logging and trace tracking:

- **Memory Update Logs:** Every time the knowledge graph is modified (be it
  adding a new node, updating a relation, or marking something invalid), the
  system will record an entry describing the change. This can be done at the
  application level: e.g., after a successful update transaction to Neo4j,
  create a log entry in Postgres or a log file with details
  (`timestamp, user_id, change_type, entity_or_relation_id, summary_of_change, source_text`).
  Storing this in a relational table is useful for later queries like “what
  facts were added for user X in the last week” or “who/what caused this piece
  of info to be updated”. It’s essentially a **journal of memory changes**. This
  could be made even more sophisticated by integrating with a provenance
  tracking system (each piece of data carries metadata of origin).
- **Versioned Knowledge Graph:** As discussed, the KG itself holds historical
  states via temporal properties. This inherently provides traceability for the
  data’s evolution. If one needs to audit the state at time T, a Cypher query
  can reconstruct which nodes/edges were valid then. If an error is discovered
  (say a wrong fact added), one can trace back in the logs to see when it was
  added and perhaps by which input.
- **Inference Trace:** For each user query and the assistant’s answer, we may
  store a record of what knowledge was retrieved and used. For example, if the
  user asks “Where did I buy my car?”, we log that we retrieved node
  `Car123 (Tesla) -> purchased_at -> SuperCars Dealership`. If the answer is
  generated, we store perhaps the final answer text. This creates a chain where
  we can later say, “Answer to question Q was based on facts A, B, C.” This is
  crucial if the user ever says “Hey, that answer was wrong” – we can inspect
  what knowledge led to it. If the knowledge was wrong, that’s on memory; if the
  knowledge was right but the LLM answered incorrectly, that’s on the
  generation. Such transparency is valuable for debugging and improving the
  system.
- **Secure Access and Permissions:** Audit also ties into who can access or
  change data. Each update is attributed to either the user (if it came from
  user input) or the system (if it came from an external source or an automated
  process). We could include the user’s ID or name in the log as the actor. If
  multiple roles exist (say an admin can manually correct knowledge), those
  actions would be logged with admin identity.
- **Monitoring and Metrics:** In addition to data traceability, we monitor
  system performance. Each component (Falcon API, knowledge DB, etc.) can emit
  metrics to Prometheus (requests per second, query latencies, number of
  updates, CPU/memory usage of pods). This ensures we can audit the system’s
  health and capacity over time. Traceability of inferences might also involve
  capturing how often we hit certain branches (like how often novelty detection
  triggered immediate vs deferred updates – a metric to see if threshold tuning
  is needed).

**User Transparency:** Depending on the use-case, we might even offer users a
view of their stored knowledge (like a “My Memory” page where they can see what
the bot has stored about them). This is an ultimate form of auditability for the
end-user. It wasn’t explicitly asked, but ensuring the data is traceable
internally sets the stage to possibly expose it externally in a safe way.

**Tools for Auditing:** We can utilize existing frameworks or at least formats:

- Logging to files/STDOUT which go to a central log (ELK stack or cloud logging)
  ensures we have raw records of everything.
- The knowledge graph itself as a provenance store: We could model a “Source”
  node for each piece of knowledge linking to the conversation message or
  document from which it was extracted. E.g.,
  `Message123 -> [ASSERTED] -> (FactEdge)` indicating this message asserted that
  fact. This way, one can navigate from a fact to its source.
- If using Airflow, we get a lot of logging and monitoring for free in terms of
  batch jobs (Airflow UI shows DAG runs, etc., which is an audit of batch
  processes).
- If using Argo, each workflow execution is logged (and can be archived),
  showing what happened for each step (useful to audit any failures in update
  processes).

**Compliance and Security:** In certain domains, traceability might be needed
for compliance (e.g., GDPR – a user can request deletion of their data, we’d
need to trace and remove their personal data entirely). Having a structured
store of facts with timestamps helps locate and remove or anonymize data if
needed. Also, keeping an audit trail of data changes helps prove compliance
(like showing that when a user requested deletion, we performed it, etc., though
full implementation of that is beyond our immediate design).

In summary, the architecture doesn’t treat the knowledge base as a black box –
every update and usage is *observable*. We maintain logs and versioning such
that we can answer “who/what/when caused this knowledge to be added or changed”
and “what knowledge did the system use to answer this question.” This addresses
the traceability of updates and inferences requirement directly.

## Deployment and Kubernetes Considerations

Deploying this system on Kubernetes involves multiple components working
together. A possible deployment setup on AKS/EKS is as follows:

- **API Server Deployment:** A Deployment for the Falcon web service, with, say,
  3 replicas (scalable based on load). It could be exposed via a Kubernetes
  Service of type LoadBalancer (for external access). TLS termination and
  authentication can be handled at an API gateway or ingress (for instance,
  using an OAuth2 proxy or integrating with an identity provider, so that only
  authenticated calls reach Falcon).
- **Knowledge Graph DB:** A StatefulSet for Neo4j. Usually a single-instance
  (with a persistent volume). If high availability is needed, one can consider a
  causal cluster with multiple core members, but that complicates the
  open-source usage (community edition doesn’t support clustering). For moderate
  use, a single instance with backups is fine. The DB might be deployed in the
  same cluster or could be an external service.
- **PostgreSQL DB:** Another StatefulSet (or a helm chart like
  bitnami/postgresql) for the relational DB. It will have its volume for data.
- **Airflow** (if used): Typically consists of a Scheduler Deployment, a
  Webserver Deployment, and possibly CeleryExecutors or KubernetesExecutors for
  running tasks. There are charts that set this up. Airflow would need access to
  the same databases (likely via service endpoints for Neo4j and Postgres, using
  their internal cluster DNS names).
- **Argo** (if used, alternative to Airflow): Deploy the Argo Workflow
  controller (as a Deployment) and ensure RBAC is set so it can spawn pods. We’d
  submit Workflow CRDs either via the API server or via Argo CLI/CI pipeline.
  The workflows in Argo will mount config (like a kube Secret with DB
  credentials, etc.) to access the databases.
- **Dask Cluster:** Could be deployed as a set of deployments or via Dask’s
  operator. For example, a scheduler pod and an auto-scaled set of worker pods.
  The Falcon app or workflows would connect to the Dask scheduler to dispatch
  tasks. (This is optional, one could also just start a local Dask cluster on
  the fly in a pod when needed, but having a persistent one avoids startup
  cost.)
- **Monitoring**: Deploy Prometheus and Grafana (or use a managed one) to
  collect metrics from pods. We’d instrument the Python code with something like
  Prometheus client or OpenTelemetry to record key metrics (latency of KG
  queries, number of triples in KG, etc.).
- **Logging**: Ensure logs from all components go to a central sink (could be
  Azure Monitor on AKS or CloudWatch on EKS, or an ELK stack). This aids
  debugging and auditing.

**Security:** We must secure communications between components (use TLS for DB
connections if possible, or at least cluster-internal traffic is not exposed).
Also secrets (DB passwords, API keys if any) should be stored in Kubernetes
Secrets and mounted safely. Role-based access control (RBAC) in K8s will ensure,
for example, that only the orchestrator can trigger certain jobs, etc.

**Resource Scaling:** Each component can be scaled:

- The web API horizontally (more replicas).
- The Dask workers can scale vertically (bigger VMs for heavy compute) or
  horizontally.
- The DB might need vertical scaling (more memory for Neo4j if graph grows).
- Using a cloud K8s means we can attach auto-scalers to scale out on CPU/GPU
  usage for the workers.

**Trade-offs in Deployment:** One consideration is complexity vs simplicity. We
have many moving parts (web app, DBs, orchestrator, etc.). For a smaller scale,
one might simplify: e.g., not use Airflow/Argo at first, but just use Python
threads or cron jobs in a single container to run maintenance tasks. However,
that doesn’t scale or modularize as well. Our design goes for a robust,
production-ready setup at the cost of introducing these systems which require
DevOps effort. The benefit is each is well-suited to its role (Airflow for
scheduling, etc.) and they are all Kubernetes-friendly.

## Trade-offs and Open Challenges

Designing a system of this complexity involves numerous decisions. Below we
discuss some trade-offs made and highlight open challenges that may require
future work:

**1. Knowledge Graph vs Simpler Memory Store:** We chose a structured knowledge
graph for memory, rather than, say, a simple vector store or a key-value memory.
The graph approach offers rich querying capabilities and a more **interpretable,
constraint-enforceable** memory. It’s great for relational queries (who is
connected to whom) and making inferences. The trade-off is complexity: building
and maintaining a graph (with extraction pipelines and versioning) is more
involved than using an embedding store with raw text. A simpler design could
have been: store each conversation or fact as a chunk of text, index them in a
vector DB, and retrieve relevant chunks for context. That would be easier to
implement (and indeed many RAG systems do exactly that with tools like Milvus or
Pinecone). However, that loses the structured relationships and the ability to
do certain logical queries (like “who is X’s boss?” is easier if you have a
graph edge “boss_of”). Our design thus prioritizes **knowledge fidelity and
query power** at the cost of added components and pipelines. If the domain
required only Q&A on documents, a vector approach would suffice. But for
personal assistant memory (with potentially complex relations and the need to
update specific facts), a knowledge graph is justified.

**2. Real-time Updates vs Batch Updates:** We introduced an immediate update
mechanism for novelty. The advantage is responsiveness – the system’s knowledge
is always current with the conversation. The downside is potential overhead and
race conditions: what if the user rapid-fires 5 new facts in succession? The
system might spawn multiple update tasks that could even conflict (though Neo4j
can queue transactions, we might end up with an order issue if not careful).
Alternatively, doing everything in batch (like some systems only update memory
after conversation sessions) would be simpler but means the bot might seem
forgetful within a session (“I already told you that” issues). We opted to blend
the approaches for flexibility. Tuning the threshold for this is tricky; it
might need iterative refinement. This is an open challenge: **how to robustly
quantify novelty** to decide update timing. It’s possible we might use an ML
classifier in the future that predicts “store now” vs “store later” based on
training data of what facts users tend to ask about soon, etc.

**3. Subinterpreters and Python Concurrency:** Using Python’s new
subinterpreters feature (PEP 734) is cutting-edge. The benefit is unlocking
multi-core parallelism in-process, which is great for our multi-user
requirement. However, this feature in Python 3.13 might still be **new and not
battle-tested** at scale. There could be hidden issues or lack of ecosystem
support (many libraries might not expect to run in subinterpreters, especially C
extensions might have global state not designed for it). If subinterpreters
prove problematic, the fallback is to use multiple processes (which Python
frameworks already support via WSGI servers or by running one process per user
etc.) or to rely on `asyncio` with careful coroutine management. Each approach
has trade-offs: multi-process uses more memory and can complicate sharing data
(we’d need inter-process communication to access the knowledge graph or caches,
whereas subinterpreters share the same process memory albeit not directly the
objects). AsyncIO is single-threaded but can handle many I/O tasks; however, our
tasks (LLM inference, etc.) are CPU/GPU heavy, so async alone isn’t enough. We
went with subinterpreters as a forward-looking solution for concurrency in
Python, but it remains an area to watch. It’s an open challenge to ensure
library compatibility and stability with this new model (for example, we must
ensure the Neo4j Python driver or others don’t misbehave in subinterpreters –
they likely use sockets and threads which should be fine, but one must test).

**4. JAX vs Other ML Frameworks:** We included JAX to utilize accelerators and
parallelism for ML parts. JAX is powerful for researchers, but many production
systems default to PyTorch or TensorFlow, which have more out-of-the-box models
and perhaps easier integration with certain pipelines. The choice of JAX means
potentially reimplementing some models or ensuring that we can get JAX
equivalents. The trade-off here is between raw performance and ecosystem
maturity. JAX can outperform in some cases and allows neat tricks (like
compiling a whole workload end-to-end), but PyTorch has more pre-trained models
(for NER, etc.). We could actually mix: use PyTorch for NER model inference
(loading via HuggingFace) and use JAX for things like computing lots of
embeddings in parallel if we have a JAX-compatible model. This mix could
introduce complexity (two different ML frameworks in one system). We decided on
JAX to highlight cutting-edge parallelism, but this is flexible. If we find that
using PyTorch with DataParallel or NVIDIA TensorRT gives us better mileage, we
might pivot. **Open challenge:** making sure the ML components (NER, relation
extraction, embedding models) are efficient enough – if not, additional
engineering like quantization or compiled pipelines may be needed. Dask could
help distribute PyTorch inference too if JAX isn’t used.

**5. Orchestrator Choice and Complexity:** Managing Airflow or Argo is
non-trivial (Airflow requires maintaining a metadata DB and can be heavy; Argo
requires comfort with K8s CRDs and some YAML programming). For a lean team, this
might be overhead. The alternative could have been to rely on simpler scheduling
(like a cronjob Kubernetes resource for periodic tasks, and a simple queue +
consumer for events). That’s a lighter-weight approach but loses out on the
robust features (retries, DAG dependencies, etc.). We opted for Airflow/Argo
because the system is anticipated to be complex enough to benefit from a
full-featured orchestrator. In a scenario where resources are limited, one might
start with cronjobs and then upgrade to Airflow/Argo as needed. Also, using two
orchestrators is unnecessary – one should be picked. **Trade-off:** Airflow has
a nice UI and is Pythonic; Argo is cloud-native and might integrate better with
our K8s environment. If the team has more DevOps/K8s expertise, Argo could be
preferable, whereas data engineering expertise leans Airflow. We have to
consider team skill and existing tooling in making that choice.

**6. Multi-User Data Isolation:** Our plan is logically isolating data in one
database. An alternative approach for strong isolation is to spin up a separate
instance of the whole system per user (especially if user data is sensitive).
That’s what some personal AI systems might do if each user’s data must never
co-mingle. But that’s obviously resource-intensive and doesn’t scale beyond a
small number of users. The multi-tenant graph is a compromise, which raises some
challenges:

- Ensuring that query filtering by user is done everywhere. A bug or oversight
  could cause a leak (e.g., if someone forgets to add `WHERE user_id = X` in a
  query). This requires discipline and perhaps automated tests or graph rules to
  enforce no cross-user edges.
- Performance could degrade as the number of users grows, even if each has
  modest data, because the graph DB might have to handle a lot of partitions. We
  might need to shard by user ID range if it grows huge (which Neo4j doesn’t do
  automatically, but maybe by running multiple DB instances each handling a
  subset of users).
- If a user exports or deletes their data, it’s easier if it’s all tagged; we
  can delete that subgraph by deleting that user node and connected components.
- Another approach could be hybrid: small number of Neo4j instances, each
  handling a group of users (like tenancy groups). That’s an operational
  trade-off: more instances to manage but each is smaller. We stick to one for
  now with caution on the above issues.

**7. Data Consistency vs Responsiveness:** Our asynchronous update approach
means there will be moments when the conversation references something not yet
in the KG (if update is deferred). If the user immediately asks, the assistant
might not find it and appear forgetful. We mitigate by immediate updates for
high novelty, but some edge cases remain. One possible mitigation (as an idea)
is to always put new facts in a short-term memory store (like a cache) even if
not in KG yet. For example, as soon as the user says a fact, the system could
keep it in a session-memory dict that the retrieval step also checks. That way,
even if the KG update hasn’t happened, the retrieval might find it in this
ephemeral store. Later the batch update will persist it. This is an extra layer
that could be implemented to avoid any gap. We haven’t explicitly included this
in the architecture, but it’s a consideration to ensure consistency.

**8. Evaluation and Accuracy:** Ensuring the knowledge extracted is correct and
that the system doesn’t accumulate errors is an open challenge. The pipeline
might extract wrong relations (especially if using automated methods). Over
time, the knowledge graph could have inaccuracies that lead the bot astray. We
might need a verification step for critical info (maybe ask the user to confirm,
or cross-check with external knowledge). That’s beyond architecture – more of an
operational/policy challenge. Similarly, measuring the success of novelty
detection (precision/recall of detecting novel info) will be important. This
likely requires iterative refinement and possibly a feedback loop (if the bot
answers “I don’t know” and the user provides the answer, that indicates a miss
in novelty detection earlier).

**9. Integration of External Knowledge:** The design assumes user-specific
knowledge and possibly some general knowledge provided initially. We haven’t
included modules for ingesting large external corpora (which some RAG systems
have). If needed, one could integrate an external knowledge ingestion pipeline
(e.g., indexing company documents or scraping web info). That would then feed
into the same KG memory. The novelty detection would then also apply to new
external info relative to what’s known. This is an extension area – ensures the
architecture can accommodate an incoming data stream outside of the
conversation.

**10. Scalability of Graph Operations:** As the knowledge graph grows, some
operations might slow down (especially if not indexed well). For instance, a
very large number of historical edges could make queries filtering by latest
valid edges slower. We might need to archive or compress history (maybe move old
edges to a separate label or database). Also if we had complex queries like
multi-hop reasoning, performance could drop. Solutions include leveraging graph
algorithms libraries or pre-computing certain paths. While our current retrieval
needs are straightforward (mostly 1 or 2-hop queries), future needs (like “who
else in my network knows Alice’s boss?”) could require deeper graph searches,
which should be handled carefully to avoid timeouts. Neo4j can handle multi-hop
with proper algorithms (like built-in shortest path, etc.), but we should be
mindful of query tuning.

**11. Evolving Models and Tools:** The architecture uses many specific tools
(Falcon, Neo4j, etc.), but technology moves fast: - Falcon is stable but
relatively low-level; frameworks like FastAPI are more popular now for ease (but
slightly more overhead). We chose Falcon for speed. If development speed trumps
a few milliseconds of latency, FastAPI or Flask could be considered. - Neo4j vs
other knowledge stores: RDF triple stores (like GraphDB or Blazegraph) could
enforce ontology constraints (RDF Schema/OWL reasoning). We skipped those for
simplicity; an open question is whether reasoning/inference on the graph is
needed (e.g., infer transitive relations). That could be future work –
integrating a reasoner if needed. - Model upgrades: The LLM or NLP models used
might be improved or changed. We should design the system to allow swapping out
(e.g., today’s NER model might be replaced with a better one later). This
implies modular design where the NLP pipeline is loosely coupled (maybe through
an interface or an external microservice that can be replaced). - Python
versions: Python 3.13 is specified likely for the new concurrency features. If
for some reason we had to use 3.11 or 3.12 (if 3.13 is not stable by deployment
time), we lose PEP 734 built-in support. However, there is a PyPI `interpreters`
backport for 3.12 possibly, and PEP 684 (no GIL per interpreter) is actually
implemented in 3.12. So one could run experimental features if needed. It’s a
risk if timeline doesn’t align, so we keep an eye on Python releases.

In conclusion, while the proposed architecture meets the requirements with a
comprehensive solution, it is **not without challenges**. We have emphasized a
design that is *future-proof and scalable* (dynamic memory, parallel compute,
robust orchestration), but this comes at the cost of complexity in
implementation and maintenance. Key open challenges like fine-tuning novelty
detection, ensuring data quality, and managing system complexity will need to be
addressed through careful testing and iteration. The benefit, however, is a
powerful system that equips a chatbot with a **surprise-aware, ever-learning
memory** that can provide personalized, context-rich interactions in a reliable
and auditable manner, moving beyond static knowledge retrieval towards a more
human-like evolving understanding.

**References:** The architecture draws on current best practices and emerging
research, such as Zep’s Graphiti approach for real-time knowledge graph memory,
modern Python concurrency improvements, and established principles of novelty
detection in NLP. By combining these with proven tools (Neo4j, Airflow, etc.),
we aim to deliver a cutting-edge yet practical system for deployment on cloud
Kubernetes environments. The following sources provide additional context and
validation for some of the techniques and choices made:

- Snow, Eric. *PEP 734 – Multiple Interpreters in the Stdlib.* (Python 3.13
  proposal) – explains subinterpreter usage and motivation.
- Zep AI. *Graphiti: Knowledge Graph Memory for an Agentic World.* Neo4j
  Developer Blog, 2025 – describes dynamic KG memory, temporal graph versioning,
  and hybrid search for low-latency retrieval.
- Ghosal et al. *Novelty Detection: A Perspective from NLP.* (2022) – defines
  novelty detection in text as finding new information w.r.t. known information.
- Dask Documentation – highlights Dask’s capability for distributed computing
  with low task overhead and complex scheduling in pure Python.
- JAX Tutorial – demonstrates JAX’s `pmap` for effortless parallelism across
  devices.
