# Using Hugging Face TEI with Neo4j for RAG (Retrieval-Augmented Generation)

Retrieval-augmented generation systems often need to generate vector
**embeddings** for text and store them in a database to enable semantic search.
This guide shows how to use Hugging Face’s containerized **Text Embeddings
Inference (TEI)** service as an embedding model provider, together with
**Neo4j** (with native vector indexing) as the vector database for a knowledge
graph. We’ll cover how to get embeddings from the TEI API, insert (upsert) them
into Neo4j with vector indexing, perform similarity searches in Neo4j, and
design a Python `EmbeddingClient` abstraction (plus a mock version) for clean
integration and testing.

## 1. Generating Text Embeddings with TEI

**Hugging Face TEI** is a Dockerized service for high-performance embedding
generation. First, deploy the TEI container with your chosen model. For example,
to use the `BAAI/bge-large-en-v1.5` model (which produces 1024-dimensional
embeddings):

```bash
docker run -p 8080:80 ghcr.io/huggingface/text-embeddings-inference:1.7 \
    --model-id BAAI/bge-large-en-v1.5
```

This will start the TEI service on port 8080 (no API token needed for local
use). Once running, you can obtain embeddings by sending an HTTP POST to the
container’s `/embed` endpoint. The request should be JSON with an **`inputs`**
field containing the text (or list of texts) to embed. For example, using `curl`
for a batch of texts:

```bash
curl http://127.0.0.1:8080/embed \
     -X POST \
     -d '{"inputs":["Today is a nice day", "I like you"]}' \
     -H 'Content-Type: application/json'
```

The TEI service will return the embeddings as JSON – typically a list of vectors
(one vector per input). In Python, you can call this API using a lightweight
HTTP library like `requests`:

```python
import requests

TEI_URL = "http://localhost:8080/embed"  # Base URL for the TEI embed endpoint
text = "This is a sample document to embed."
response = requests.post(TEI_URL, json={"inputs": text}, timeout=5.0)
response.raise_for_status()  # Ensure the request was successful
embeddings = response.json()
# If a single string was sent, `embeddings` will be a list of one vector
vector = embeddings[0]  # The embedding vector as a list of floats
print(f"Embedding length: {len(vector)}") 
```

For a single input text, `response.json()` will likely return a list containing
one embedding vector. In the example above, `vector` would be a Python list of
floats (e.g. `[0.00479, -0.03164, -0.01805, ...]`). If you send multiple texts
in the `"inputs"` list, the result will be a list of embeddings (one sub-list
per input in the same order).

**Parsing the output:** The TEI JSON response is straightforward – you can use
it directly as a list of floats. Ensure you handle the case where the request or
service might error out (check HTTP status and catch exceptions). Also, note the
**dimension** of the returned vectors, as you will need this when configuring
Neo4j’s vector index. (For example, `BAAI/bge-large-en-v1.5` produces
1024-dimensional embeddings, while other models like OpenAI’s
`text-embedding-ada-002` produce 1536-dimensional vectors.)

## 2. Inserting Embeddings into Neo4j with a Vector Index

Neo4j (v5.13+ general availability) supports **native vector indexing** for
efficient similarity search on vector properties. To store and query embeddings
in Neo4j, you should create a vector index on the node property that will hold
the embedding.

**Create a vector index:** You can do this via Cypher. For example, if we plan
to store embeddings in a property named `embedding` on nodes with label
`Document`, and each embedding is a list of floats of length 1024 using cosine
similarity, we create the index as follows:

```cypher
CREATE VECTOR INDEX DocumentEmbeddings IF NOT EXISTS
FOR (d:Document)
ON (d.embedding)
OPTIONS {
  indexConfig: {
    "vector.dimensions": 1024,         // must match embedding length
    "vector.similarity_function": "cosine"
  }
};
```

This command tells Neo4j to index the `Document.embedding` property as a
1024-dimensional vector, using cosine similarity for comparisons. (**Note:** In
Neo4j 5.15+, you use the `CREATE VECTOR INDEX` syntax as above. Earlier versions
had a procedure `db.index.vector.createNodeIndex`. Also, the `IF NOT EXISTS`
clause makes index creation idempotent.)

Before inserting data, ensure the index is online (use `SHOW VECTOR INDEXES` to
check status). Neo4j builds the index in the background; once its state is
`ONLINE`, you can use it for insertions and queries.

**Upserting nodes with embeddings:** To insert a new knowledge item (or update
an existing one) with its embedding, use Cypher `MERGE` or `CREATE/SET`. For
example, suppose we have a document ID and content text, and we obtained its
embedding vector via TEI as `vector`:

```python
from neo4j import GraphDatabase, basic_auth

# Neo4j connection (update URI, user, password as needed)
driver = GraphDatabase.driver("neo4j://localhost:7687", auth=basic_auth("neo4j", "test"))
doc_id = "doc123"
text = "Some document content"
vector = embedding_client.embed(text)  # assume this returns the embedding list of floats

with driver.session(database="neo4j") as session:
    session.run(
        """
        MERGE (d:Document {id: $doc_id})
        SET d.content = $text, 
            d.embedding = $embedding
        """,
        parameters={"doc_id": doc_id, "text": text, "embedding": vector}
    )
```

In the Cypher above, `MERGE` will find or create a `Document` node with the
given `id`. We then use `SET` to update the node’s `content` and `embedding`
properties. We pass the embedding as a parameter (a list of floats) – the Neo4j
Python driver will transmit this list so that it’s stored as a **`List<Float>`
property** on the node. Neo4j’s vector index will automatically index this new
vector property (once the index is online and assuming the vector has the
correct dimension and type). There’s no need for additional steps to add the
node to the index; it works like a normal index that updates on transaction
commit.

**Important:** The embedding list’s length **must match** the index’s configured
`vector.dimensions`, otherwise the index query will reject it as invalid. Ensure
consistency between the embedding model’s output dimension and the Neo4j index
setting. For example, if using OpenAI’s Ada-002 (1536 dims) or BGE large (1024
dims), configure accordingly. Neo4j’s index can be created without specifying
dimensions (in Neo4j 5.23+), but it’s safer to specify so that only vectors of
the correct size are indexed.

## 3. Performing Vector Similarity Search in Neo4j

Once documents (or knowledge nodes) with embeddings are stored and indexed, you
can perform **vector similarity searches** to find relevant nodes for a given
query. The general approach is:

1. **Embed the query text** using TEI to get a query vector.
2. Use Neo4j’s **KNN query** procedure to find nearest neighbors in the vector
   index.

Neo4j provides the procedure
`db.index.vector.queryNodes(indexName, k, queryVector)` to query a vector index.
This returns up to `k` nearest neighbors (approximate by default) and their
similarity scores. For example, if we want the 5 most similar `Document` nodes
to a given query embedding:

```python
query = "What is the capital of France?"  
q_vector = embedding_client.embed(query)  # get embedding for the query text

with driver.session(database="neo4j") as session:
    result = session.run(
        """
        CALL db.index.vector.queryNodes($indexName, $topK, $queryVector)
        YIELD node, score
        RETURN node.id AS doc_id, node.content AS content, score
        """,
        parameters={"indexName": "DocumentEmbeddings", "topK": 5, "queryVector": q_vector}
    )
    for record in result:
        print(record["doc_id"], record["score"], record["content"][:100])
```

In Cypher, we call the procedure with our index name (e.g.
`"DocumentEmbeddings"`), the number of neighbors (`5`), and the query vector. We
then `YIELD` each matching `node` and its `score`. The score is a similarity
measure between 0 and 1 (for cosine similarity, 1.0 means identical vectors). By
default, results are ordered by similarity (highest first). In the example
above, you’d get up to 5 `Document` nodes most related to the query, along with
their similarity scores.

Under the hood, Neo4j uses an approximate nearest neighbors search (powered by
Lucene) for scalability. You can filter or post-process results as needed. For
instance, you might only consider results above a certain score, or join with
other conditions. If you want to combine vector search with other predicates,
you can incorporate the `CALL ... YIELD ...` inside a broader Cypher query (for
example, filter by some category property after obtaining the neighbors).

**Example:** A direct Cypher example (from Neo4j’s documentation) finding movies
similar to *The Godfather* illustrates the usage of `queryNodes` within a query:

```cypher
MATCH (m:Movie {title: "Godfather, The"})
CALL db.index.vector.queryNodes('moviePlots', 5, m.embedding)
YIELD node AS movie, score
RETURN movie.title AS title, movie.plot AS plot, score;
```

This finds the top-5 movies whose `embedding` is closest to *The Godfather*’s
embedding. In our RAG scenario, you would substitute the known vector
(`m.embedding` in this example) with a parameter for your query vector (as shown
in the Python snippet above using `$queryVector`). The result gives you the
content to feed into your LLM as context.

## 4. Designing an `EmbeddingClient` Abstraction

To cleanly integrate the TEI service into your application, it’s wise to wrap
the embedding logic in a dedicated **EmbeddingClient** class. This abstraction
encapsulates details of the HTTP calls and makes it easy to swap out or mock
later. Key design points for `EmbeddingClient`:

- **Configurable endpoint:** Allow specifying the base URL (and possibly model
  or auth token) for the TEI service.
- **Easy interface:** Provide a method (e.g. `embed(text)` or
  `embed_batch(list_of_texts)`) that returns the embedding vector(s) as Python
  data types (list of floats).
- **Error handling and timeouts:** Set a reasonable timeout on requests and
  handle HTTP errors.
- **Dependency-light:** Use standard libraries (`requests` for HTTP) to avoid
  heavy dependencies.

Below is an example implementation:

```python
import requests
from typing import List, Union, Optional

class EmbeddingClient:
    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 5.0, auth_token: Optional[str] = None):
        """
        Client to fetch text embeddings from a TEI service.
        :param base_url: Base URL of the TEI service (without the trailing slash).
        :param timeout: HTTP request timeout in seconds.
        :param auth_token: Optional bearer token for authentication (if required by TEI).
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Prepare headers if auth token is provided
        self.headers = {"Content-Type": "application/json"}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
    
    def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """
        Get embedding for a single string or a batch of strings.
        Returns a list of floats for single input, or a list of lists for multiple inputs.
        """
        # Prepare payload - TEI expects "inputs" as str or list of str
        payload = {"inputs": text}
        url = f"{self.base_url}/embed"
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to connect to Embedding service: {e}")
        if response.status_code != 200:
            raise RuntimeError(f"Embedding service error {response.status_code}: {response.text}")
        data = response.json()
        # `data` is expected to be a list: [embedding] or [[emb1], [emb2], ...]
        if isinstance(text, str):
            # Single string input – return the single embedding vector (list of floats)
            return data[0] if isinstance(data, list) else data
        else:
            # Batch input – return list of embedding vectors
            return data
```

This `EmbeddingClient.embed()` method sends the request to TEI’s `/embed`
endpoint and parses the JSON response. If a single string is passed, it returns
a single embedding vector (list of floats) for convenience; if a list of strings
is passed, it returns a list of vectors. You can adapt this interface based on
your needs (for example, always return a list of vectors for consistency).

Usage example:

```python
embedding_client = EmbeddingClient(base_url="http://localhost:8080")  # no auth in local setup
vec = embedding_client.embed("Hello world")  
# vec is now a list of floats representing the embedding of "Hello world"
```

You might also integrate logging inside `EmbeddingClient` for debugging (e.g.,
logging the text size or model used) but avoid printing sensitive data in
production. The above implementation is **dependency-light** (only requires
`requests`) and is compatible with Python 3.13+ (utilizing type hints and
f-strings, for example).

If you’re deploying in Kubernetes, the `base_url` would be the internal service
URL (e.g., `http://my-embeddings-service:80`), and you might supply the
`auth_token` if your service is protected. The abstraction ensures the rest of
your code (like the part that upserts nodes or runs vector searches) doesn’t
need to know HTTP details – it just calls `embedding_client.embed()`.

## 5. Mocking the EmbeddingClient for Testing

When writing unit or integration tests for your RAG pipeline, **do not rely on
the live TEI service or an internet connection**. Instead, use a **mock or
stub** for the embedding generation. This makes tests fast, reliable, and
runnable in isolated environments (like CI pipelines) without requiring the
actual model container or network.

There are two common approaches:

- **Stub Class:** Implement a fake version of `EmbeddingClient` that has the
  same interface but returns deterministic values. For example:

  ```python
  class DummyEmbeddingClient(EmbeddingClient):
      def __init__(self):
          # No real base_url needed
          super().__init__(base_url="http://dummy")  
      def embed(self, text: Union[str, List[str]]):
          # Instead of calling an API, return a fixed or pattern-based vector.
          if isinstance(text, str):
              # e.g. return a zero-vector of length 1024 for simplicity
              return [0.0] * 1024
          else:
              # return a list of zero-vectors
              return [[0.0] * 1024 for _ in text]
  ```

  In this `DummyEmbeddingClient`, the `embed` method ignores the actual text and
  returns a vector of the correct dimension (here all zeros of length 1024) or
  multiple vectors if a list is given. You can make the dummy more sophisticated
  if needed (for example, return different vectors for different inputs, perhaps
  by hashing the text to generate pseudo-random but consistent numbers). The key
  is that it’s **fast and does not call external services**.

- **Monkeypatch/Mock the method:** If you prefer not to define a separate class,
  you can monkey-patch the `EmbeddingClient.embed` method in your tests. For
  instance, using `pytest` you could do:

  ```python
  def test_upsert_document(monkeypatch):
      # Arrange: monkeypatch EmbeddingClient.embed to return a known vector
      dummy_vector = [0.1, 0.1, 0.1]  # a short dummy vector for testing
      monkeypatch.setattr(EmbeddingClient, "embed", lambda self, text: dummy_vector)
      
      # Act: call code that uses embedding_client.embed()
      embedding_client = EmbeddingClient()  # base_url won't matter due to monkeypatch
      vec = embedding_client.embed("any text")
      
      # Assert: verify the returned vector is the dummy vector
      assert vec == dummy_vector
  ```

  In this example, we patched `EmbeddingClient.embed` to always return
  `[0.1, 0.1, 0.1]` for any input, allowing us to test the logic that uses the
  embedding (for example, ensuring the subsequent database insertion uses this
  vector). You can similarly use `unittest.mock.patch`:

  ```python
  from unittest.mock import patch

  def test_query_flow():
      fake_vec = [0.2, 0.3, 0.4]
      with patch.object(EmbeddingClient, 'embed', return_value=fake_vec) as mock_method:
          embedding_client = EmbeddingClient()
          result_vec = embedding_client.embed("test query")
          mock_method.assert_called_once_with("test query")
          assert result_vec == fake_vec
  ```

  Here, `patch.object` replaces `EmbeddingClient.embed` with a dummy that
  returns `fake_vec` and we assert it was called properly. This approach is
  useful for unit tests of higher-level functions that call the embedding
  client. It avoids the need to spin up the TEI container or use actual model
  inference during tests.

## 6. Testing Neo4j Integration In-Memory

Testing the Neo4j part (inserting nodes and querying) without a real database is
trickier, but you can still avoid requiring a full Neo4j server for basic tests
by using mocks. The Neo4j Python driver (`neo4j` module) allows you to inject a
fake driver or session. For example, you can **mock the database session** to
verify that the correct Cypher queries and parameters are being sent:

```python
from unittest.mock import MagicMock, patch

def test_store_embedding_to_neo4j():
    # Create a fake session with a MagicMock for the run method
    fake_session = MagicMock()
    fake_session.run = MagicMock(return_value=None)  # we don't care about return for insert
    
    # Patch GraphDatabase.driver to return an object whose session() returns our fake_session
    with patch('neo4j.GraphDatabase.driver') as mock_driver:
        mock_driver.return_value.session.return_value = fake_session

        # Now call the function that uses GraphDatabase.driver and session.run
        embedding_client = DummyEmbeddingClient()
        vec = embedding_client.embed("some text")  # this returns a dummy vector
        # Suppose we have a function store_document(driver, id, text, vector)
        store_document(GraphDatabase.driver(...), "doc42", "dummy content", vec)
        
        # After calling, we can assert the Cypher was correct:
        fake_session.run.assert_called_once()
        cypher_sent = fake_session.run.call_args[0][0]
        params_sent = fake_session.run.call_args[1]["parameters"]
        assert "MERGE (d:Document" in cypher_sent
        assert params_sent["doc_id"] == "doc42"
        assert params_sent["embedding"] == vec
```

In the above pseudo-test, we patch the Neo4j driver so that when our code under
test calls `GraphDatabase.driver(...).session()`, it gets a `fake_session`. We
then trigger our code (e.g., a function that builds and runs the Cypher for
upsert), and afterward we assert that `session.run` was called with the expected
query and parameters. This way, we validate the logic **without needing an
actual Neo4j instance**. The same technique can be applied for testing the query
flow – for example, set `fake_session.run` to return a dummy result list (or a
custom object mimicking Neo4j's `Result`) containing expected nodes and scores,
then verify that your code correctly interprets those results.

For **behavioral tests** (higher-level tests simulating the end-to-end flow),
you might consider using an **embedded Neo4j** or a **Neo4j testcontainer**. If
you do, keep it ephemeral: for example, use a temporary Neo4j Docker container
that starts, loads some test data, runs queries, and is destroyed. This ensures
tests run in isolation. However, many CI environments might not easily support
running Neo4j containers, so using the mocking approach above is often
sufficient for logic verification.

**Summary of testing approach:** In all tests, **avoid external dependencies**:
use the dummy embedding client instead of calling the real TEI service, and
either use a throwaway Neo4j instance or mock the Neo4j driver calls. This
ensures tests are deterministic and fast, and can run in environments without
access to Docker or the internet.

## 7. Conclusion

By leveraging Hugging Face’s TEI for embedding generation and Neo4j’s native
vector index for storage and search, you can build a powerful knowledge
graph-backed RAG system. The workflow is:

1. **Embed text** (documents or queries) via TEI’s `/embed` API, parse the
   returned vector(s).
2. **Upsert nodes** into Neo4j with an `embedding` property (as a list of
   floats), making sure a vector index is configured for that property (e.g.
   using `CREATE VECTOR INDEX ... OPTIONS {vector.dimensions: ...,`
   `vector.similarity_function: ...}`).
3. **Query by similarity** using `db.index.vector.queryNodes(...)` to fetch
   relevant nodes and their similarity scores.
4. Use the results (e.g. node content) as context for your LLM or downstream
   application.

The `EmbeddingClient` abstraction we designed simplifies integration and helps
separate concerns. Moreover, by providing a mockable interface, it enables
robust testing without relying on live services. All the code is written in
Python 3.13+ and keeps dependencies minimal (just `requests` for HTTP and the
official `neo4j` driver for database interaction), making it easy to maintain
and integrate into frameworks like `pytest` or CI pipelines.

With this setup, your RAG chatbot or knowledge application can seamlessly
convert text to embeddings, store them in a Neo4j knowledge graph, and perform
fast semantic lookups – all while being testable entirely with in-memory or
local components. Happy coding!

**Sources:**

- Hugging Face, *Text Embeddings Inference – Quick Tour* (usage of TEI `/embed`
  endpoint with input and output examples)
- Neo4j Documentation, *Vector Indexes* (creating vector index and querying by
  vector similarity in Neo4j)
- BAAI BGE Large model spec – *1024-dimensional embeddings* (embedding dimension
  example for configuring Neo4j index)
