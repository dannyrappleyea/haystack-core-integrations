# SPDX-FileCopyrightText: 2023-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0
import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from haystack.dataclasses.document import ByteStream, Document
from haystack.document_stores.errors import DuplicateDocumentError
from haystack.document_stores.types import DuplicatePolicy
from haystack.testing.document_store import DocumentStoreBaseTests
from haystack.utils import Secret
from pymongo import MongoClient
from pymongo.driver_info import DriverInfo

from haystack_integrations.document_stores.mongodb_atlas import MongoDBAtlasDocumentStore


@patch("haystack_integrations.document_stores.mongodb_atlas.document_store.MongoClient")
def test_init_is_lazy(_mock_client):
    MongoDBAtlasDocumentStore(
        mongo_connection_string=Secret.from_token("test"),
        database_name="database_name",
        collection_name="collection_name",
        vector_search_index="cosine_index",
        full_text_search_index="full_text_index",
        embedding_field="embedding",
    )
    _mock_client.assert_not_called()


@pytest.mark.skipif(
    not os.environ.get("MONGO_CONNECTION_STRING"),
    reason="No MongoDB Atlas connection string provided",
)
@pytest.mark.integration
class TestDocumentStore(DocumentStoreBaseTests):
    @pytest.fixture
    def document_store(self):
        database_name = "haystack_integration_test"
        collection_name = "test_collection_" + str(uuid4())

        connection: MongoClient = MongoClient(
            os.environ["MONGO_CONNECTION_STRING"], driver=DriverInfo(name="MongoDBAtlasHaystackIntegration")
        )
        database = connection[database_name]
        if collection_name in database.list_collection_names():
            database[collection_name].drop()
        database.create_collection(collection_name)
        database[collection_name].create_index("id", unique=True)

        store = MongoDBAtlasDocumentStore(
            database_name=database_name,
            collection_name=collection_name,
            vector_search_index="cosine_index",
            full_text_search_index="full_text_index",
            embedding_field="embedding",
        )
        yield store
        database[collection_name].drop()

    def test_write_documents(self, document_store: MongoDBAtlasDocumentStore):
        docs = [Document(content="some text")]
        assert document_store.write_documents(docs) == 1
        with pytest.raises(DuplicateDocumentError):
            document_store.write_documents(docs, DuplicatePolicy.FAIL)

    def test_write_blob(self, document_store: MongoDBAtlasDocumentStore):
        bytestream = ByteStream(b"test", meta={"meta_key": "meta_value"}, mime_type="mime_type")
        docs = [Document(blob=bytestream)]
        document_store.write_documents(docs)
        retrieved_docs = document_store.filter_documents()
        assert retrieved_docs == docs

    def test_to_dict(self, document_store):
        serialized_store = document_store.to_dict()
        assert serialized_store["init_parameters"].pop("collection_name").startswith("test_collection_")
        assert serialized_store == {
            "type": "haystack_integrations.document_stores.mongodb_atlas.document_store.MongoDBAtlasDocumentStore",
            "init_parameters": {
                "mongo_connection_string": {
                    "env_vars": [
                        "MONGO_CONNECTION_STRING",
                    ],
                    "strict": True,
                    "type": "env_var",
                },
                "database_name": "haystack_integration_test",
                "vector_search_index": "cosine_index",
                "full_text_search_index": "full_text_index",
            },
        }

    def test_from_dict(self):
        docstore = MongoDBAtlasDocumentStore.from_dict(
            {
                "type": "haystack_integrations.document_stores.mongodb_atlas.document_store.MongoDBAtlasDocumentStore",
                "init_parameters": {
                    "mongo_connection_string": {
                        "env_vars": [
                            "MONGO_CONNECTION_STRING",
                        ],
                        "strict": True,
                        "type": "env_var",
                    },
                    "database_name": "haystack_integration_test",
                    "collection_name": "test_embeddings_collection",
                    "vector_search_index": "cosine_index",
                    "full_text_search_index": "full_text_index",
                    "embedding_field": "custom_embedding",
                },
            }
        )
        assert docstore.mongo_connection_string == Secret.from_env_var("MONGO_CONNECTION_STRING")
        assert docstore.database_name == "haystack_integration_test"
        assert docstore.collection_name == "test_embeddings_collection"
        assert docstore.vector_search_index == "cosine_index"
        assert docstore.full_text_search_index == "full_text_index"
        assert docstore.embedding_field == "custom_embedding"

    def test_complex_filter(self, document_store, filterable_docs):
        document_store.write_documents(filterable_docs)
        filters = {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "meta.number", "operator": "==", "value": 100},
                        {"field": "meta.chapter", "operator": "==", "value": "intro"},
                    ],
                },
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "meta.page", "operator": "==", "value": "90"},
                        {"field": "meta.chapter", "operator": "==", "value": "conclusion"},
                    ],
                },
            ],
        }

        result = document_store.filter_documents(filters=filters)

        self.assert_documents_are_equal(
            result,
            [
                d
                for d in filterable_docs
                if (d.meta.get("number") == 100 and d.meta.get("chapter") == "intro")
                or (d.meta.get("page") == "90" and d.meta.get("chapter") == "conclusion")
            ],
        )

    @pytest.mark.integration
    def test_custom_embedding_field(self):
        """Test that the custom embedding field is correctly used in the document store."""
        # Create a document store with a custom embedding field
        database_name = "haystack_integration_test"
        collection_name = "test_custom_embeddings_" + str(uuid4())

        connection: MongoClient = MongoClient(
            os.environ["MONGO_CONNECTION_STRING"], driver=DriverInfo(name="MongoDBAtlasHaystackIntegration")
        )
        database = connection[database_name]
        if collection_name in database.list_collection_names():
            database[collection_name].drop()
        database.create_collection(collection_name)
        database[collection_name].create_index("id", unique=True)

        try:
            custom_field_store = MongoDBAtlasDocumentStore(
                database_name=database_name,
                collection_name=collection_name,
                vector_search_index="cosine_index",
                full_text_search_index="full_text_index",
                embedding_field="custom_vector",
            )

            # Check that the embedding field is correctly set
            assert custom_field_store.embedding_field == "custom_vector"

            # This is a mock test since we can't execute vector search without a real vector index
            with patch.object(custom_field_store, "_collection") as mock_collection:
                # Setup the mock
                mock_collection.aggregate.return_value = []

                # Execute the method
                custom_field_store._embedding_retrieval(query_embedding=[0.1, 0.2, 0.3])

                # Verify that the correct embedding field was used in the pipeline
                args = mock_collection.aggregate.call_args[0][0]
                assert args[0]["$vectorSearch"]["path"] == "custom_vector"
                assert args[1]["$project"]["custom_vector"] == 1

        finally:
            database[collection_name].drop()
