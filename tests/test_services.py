import asyncio
import json
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, Booking, Document
from app.main import app
from app.services import COLLECTION, Services, extract_text


def run(coro):
    return asyncio.run(coro)


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.lists = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def lrange(self, key, start, end):
        return self.lists.get(key, [])[start:] if end == -1 else self.lists.get(key, [])[start:end + 1]

    async def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists[key][start:]

    async def expire(self, key, ttl):
        pass

    def lock(self, *args, **kwargs):
        class Lock:
            async def __aenter__(self):
                pass
            async def __aexit__(self, *args):
                pass
        return Lock()


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def service():
    llm = NS(embeddings=NS(create=AsyncMock()), chat=NS(completions=NS(create=AsyncMock())))
    qdrant = AsyncMock()
    return Services(llm, qdrant, MemoryRedis())


def completion(content):
    return NS(choices=[NS(message=NS(content=content))])


@pytest.mark.parametrize('strategy', ['fixed', 'recursive'])
@pytest.mark.parametrize('filename', ['test.txt', 'test.pdf'])
def test_ingestion(service, db, strategy, filename):
    if filename.endswith('.pdf'):
        # Minimal real PDF containing a text stream, parsed by pypdf.
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 200 Td (Palm Mind internships are six months.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        buffer = BytesIO()
        writer.write(buffer)
        content = buffer.getvalue()
    else:
        content = b'Palm Mind internships are six months.'
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1] * 768)])
    doc_id, count = run(service.ingest(filename, content, strategy, db))
    assert count == 1
    assert db.get(Document, doc_id).chunking_strategy == strategy
    point = service.qdrant.upsert.call_args.kwargs['points'][0]
    assert point.payload['embedding_model'] == 'nomic-embed-text'
    assert len(point.vector) == 768


def test_embedding_dimension_rejected(service):
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1])])
    with pytest.raises(HTTPException) as exc:
        run(service.embed(['hello']))
    assert exc.value.status_code == 502


def test_collection_mismatch_preserves_data(service):
    service.qdrant.collection_exists.return_value = True
    service.qdrant.get_collection.return_value = NS(config=NS(params=NS(vectors=NS(size=1536))))
    with pytest.raises(RuntimeError, match='preserved'):
        run(service.prepare_collection())
    service.qdrant.delete_collection.assert_not_called()


def test_booking_turns_confirmation_and_retry(service, db):
    turns = [
        {'intent': True},
        {'intent': True, 'name': 'Riyan Shrestha'},
        {'intent': True, 'email': 'riyan@example.com'},
        {'intent': True, 'date': '2099-10-20', 'time': '14:00', 'confirmed': True},
        {'intent': True, 'confirmed': True},
    ]
    service.booking_intent = AsyncMock(side_effect=turns)
    for message in ['I want to book an interview', 'My name is Riyan Shrestha', 'riyan@example.com']:
        run(service.conversation('booking-test', message, db))
    summary, _, booking_id = run(service.conversation('booking-test', 'October 20 2099 at 2 PM', db))
    assert 'Please confirm' in summary and booking_id is None
    assert db.query(Booking).count() == 0
    _, _, booking_id = run(service.conversation('booking-test', 'Yes, confirm.', db))
    assert db.get(Booking, booking_id).email == 'riyan@example.com'
    _, _, duplicate_id = run(service.conversation('booking-test', 'confirm', db))
    assert duplicate_id == booking_id
    assert db.query(Booking).count() == 1
    assert len(run(service.history('booking-test'))) == 10


@pytest.mark.parametrize('fields', [
    {'name': 'Riyan', 'email': 'bad', 'date': '2099-01-01', 'time': '14:00'},
    {'name': 'Riyan', 'email': 'r@example.com', 'date': '2000-01-01', 'time': '14:00'},
    {'name': 'Riyan', 'email': 'r@example.com', 'date': '2099-01-01', 'time': '25:00'},
])
def test_invalid_booking(service, db, fields):
    service.booking_intent = AsyncMock(return_value={'intent': True, **fields})
    answer, _, _ = run(service.conversation('invalid', 'Book an interview', db))
    assert 'valid' in answer
    assert db.query(Booking).count() == 0


def test_rag_followup_rewrites_query(service, db):
    service.booking_intent = AsyncMock(return_value={'intent': False})
    run(service.remember('rag', 'Tell me about the internship', 'It lasts six months.'))
    service.openai.chat.completions.create.side_effect = [completion('What is the internship duration?'), completion('The internship lasts six months.')]
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1] * 768)])
    service.qdrant.query_points.return_value = NS(points=[NS(score=0.9, payload={'document_id': 'doc', 'filename': 'test.txt', 'text': 'Internships last six months.'})])
    answer, sources, _ = run(service.conversation('rag', 'How long does it last?', db))
    assert 'six months' in answer and sources[0].document_id == 'doc'
    assert service.openai.embeddings.create.call_args.kwargs['input'] == ['What is the internship duration?']
    assert len(run(service.history('rag'))) == 4


def test_no_relevant_documents(service, db):
    service.booking_intent = AsyncMock(return_value={'intent': False})
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1] * 768)])
    service.qdrant.query_points.return_value = NS(points=[])
    answer, sources, _ = run(service.conversation('empty', 'Unknown?', db))
    assert "don't know" in answer and sources == []


def test_invalid_model_json(service):
    service.openai.chat.completions.create.return_value = completion('not json')
    with pytest.raises(HTTPException) as exc:
        run(service.booking_intent([], 'hello'))
    assert exc.value.status_code == 502


@pytest.mark.parametrize('filename,content,status', [('bad.exe', b'x', 415), ('empty.txt', b'', 422)])
def test_upload_validation(filename, content, status):
    client = TestClient(app)
    assert client.post('/api/v1/documents/ingest', files={'file': (filename, content)}).status_code == status


def test_bad_text_and_pdf():
    for filename, content in [('bad.txt', b'\xff'), ('bad.pdf', b'not a PDF')]:
        with pytest.raises(HTTPException) as exc:
            extract_text(content, filename)
        assert exc.value.status_code == 422


def test_request_validation():
    client = TestClient(app)
    assert client.post('/api/v1/chat', json={'session_id': 'bad space', 'message': 'Hi'}).status_code == 422
    assert client.post('/api/v1/chat', json={'session_id': 'ok', 'message': '   '}).status_code == 422


def test_qdrant_insertion_and_retrieval_with_sqlite(service, db):
    from qdrant_client import AsyncQdrantClient
    service.qdrant = AsyncQdrantClient(':memory:')
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1] * 768)])
    async def exercise():
        await service.prepare_collection()
        doc_id, _ = await service.ingest('real-store.txt', b'Internship lasts six months.', 'fixed', db)
        result = await service.qdrant.query_points(collection_name=COLLECTION, query=[0.1] * 768, limit=1, with_payload=True)
        assert result.points[0].payload['document_id'] == doc_id
        assert db.get(Document, doc_id).chunk_count == 1
        await service.qdrant.close()
    run(exercise())


def test_http_routes_and_dependency_failure(service, db, monkeypatch):
    from contextlib import contextmanager
    from redis.exceptions import ConnectionError
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr('app.main.SessionLocal', session)
    monkeypatch.setattr(app.state, 'services', service, raising=False)
    service.ingest = AsyncMock(return_value=('doc-id', 1))
    service.conversation = AsyncMock(return_value=('Answer', [], None))
    client = TestClient(app)
    response = client.post('/api/v1/documents/ingest', files={'file': ('sample.txt', b'Hello')}, data={'strategy': 'fixed'})
    assert response.status_code == 200 and response.json()['chunks_stored'] == 1
    assert client.post('/api/v1/chat', json={'session_id': 's', 'message': 'Hi'}).json()['answer'] == 'Answer'
    service.conversation.side_effect = ConnectionError('offline')
    assert client.post('/api/v1/chat', json={'session_id': 's', 'message': 'Hi'}).status_code == 503


def test_failed_sql_write_compensates_vector_storage(service, db, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[0.1] * 768)])
    def fail():
        raise SQLAlchemyError('write failed')
    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(SQLAlchemyError):
        run(service.ingest('rollback.txt', b'Hello', 'fixed', db))
    service.qdrant.delete.assert_awaited_once()
    assert db.query(Document).count() == 0


def test_real_openai_client_ollama_wire_contract():
    import httpx
    from openai import AsyncOpenAI
    async def exercise():
        requests = []
        def respond(request):
            body = json.loads(request.content)
            requests.append((request.url.path, body))
            if request.url.path.endswith('/embeddings'):
                assert body['encoding_format'] == 'float'
                return httpx.Response(200, json={'object': 'list', 'model': 'nomic-embed-text', 'data': [{'object': 'embedding', 'index': 0, 'embedding': [0.1] * 768}], 'usage': {'prompt_tokens': 1, 'total_tokens': 1}})
            assert body['response_format'] == {'type': 'json_object'}
            return httpx.Response(200, json={'id': 'local', 'object': 'chat.completion', 'created': 0, 'model': 'qwen2.5:1.5b', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{"intent": false}'}, 'finish_reason': 'stop'}]})
        client = AsyncOpenAI(api_key='ollama', base_url='http://localhost:11434/v1', http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        service = Services(client, AsyncMock(), MemoryRedis())
        try:
            assert len((await service.embed(['hello']))[0]) == 768
            assert await service.booking_intent([], 'hello') == {'intent': False}
            assert [p for p, _ in requests] == ['/v1/embeddings', '/v1/chat/completions']
        finally:
            await client.close()
    run(exercise())


def test_changed_booking_details_require_new_confirmation(service, db):
    details = {'name': 'Riyan', 'email': 'r@example.com', 'date': '2099-01-01', 'time': '14:00'}
    run(service.redis.set('booking:changed', json.dumps({'details': details, 'pending': True})))
    service.booking_intent = AsyncMock(return_value={'intent': True, 'time': '15:00', 'confirmed': True})
    answer, _, booking_id = run(service.conversation('changed', 'Confirm, but change time to 15:00', db))
    assert 'Please confirm' in answer and '15:00' in answer and booking_id is None
    assert db.query(Booking).count() == 0


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_embeddings_rejected(service, value):
    service.openai.embeddings.create.return_value = NS(data=[NS(index=0, embedding=[value] * 768)])
    with pytest.raises(HTTPException) as exc:
        run(service.embed(['hello']))
    assert exc.value.status_code == 502


def test_collection_wrong_distance_rejected(service):
    from qdrant_client import models
    service.qdrant.collection_exists.return_value = True
    service.qdrant.get_collection.return_value = NS(config=NS(params=NS(vectors=models.VectorParams(size=768, distance=models.Distance.DOT))))
    with pytest.raises(RuntimeError, match='preserved'):
        run(service.prepare_collection())
    service.qdrant.delete_collection.assert_not_called()


def test_memory_retention_and_session_isolation(service):
    async def exercise():
        for i in range(12):
            await service.remember('one', str(i), 'reply')
        await service.remember('two', 'private question', 'private answer')
        history = await service.history('one')
        assert len(history) == 20
        assert history[0]['content'] == '2'
        assert all('private' not in item['content'] for item in history)
    run(exercise())


def test_confirmation_retry_after_redis_write_failure(service, db):
    from redis.exceptions import ConnectionError
    details = {'name': 'Riyan', 'email': 'r@example.com', 'date': '2099-01-01', 'time': '14:00'}
    run(service.redis.set('booking:retry', json.dumps({'details': details, 'pending': True})))
    original_set = service.redis.set
    service.redis.set = AsyncMock(side_effect=ConnectionError('offline'))
    with pytest.raises(ConnectionError):
        run(service.conversation('retry', 'confirm', db))
    assert db.query(Booking).count() == 1
    service.redis.set = original_set
    _, _, booking_id = run(service.conversation('retry', 'confirm', db))
    assert booking_id == db.query(Booking).one().id
    assert db.query(Booking).count() == 1


def test_upload_size_and_strategy_validation(monkeypatch):
    monkeypatch.setattr(settings, 'max_upload_bytes', 3)
    client = TestClient(app)
    assert client.post('/api/v1/documents/ingest', files={'file': ('large.txt', b'abcd')}).status_code == 413
    assert client.post('/api/v1/documents/ingest', files={'file': ('a.txt', b'a')}, data={'strategy': 'invalid'}).status_code == 422
