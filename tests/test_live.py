"""Explicit opt-in smoke test. Writes isolated test data to local services."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.database import Booking, Document, SessionLocal


@pytest.mark.skipif(os.getenv('RUN_LIVE_TESTS') != '1', reason='Set RUN_LIVE_TESTS=1 with Ollama models, Qdrant and Redis running')
def test_live_ingestion_rag_and_booking():
    session = 'live-' + uuid4().hex
    with TestClient(app) as client:
        for strategy in ('fixed', 'recursive'):
            response = client.post('/api/v1/documents/ingest', files={'file': ('live.txt', b'Palm Mind internship duration is six months. Interns work on AI backend development.')}, data={'strategy': strategy})
            assert response.status_code == 200, response.text
            with SessionLocal() as db:
                assert db.get(Document, response.json()['document_id']) is not None
        first = client.post('/api/v1/chat', json={'session_id': session, 'message': 'What is the Palm Mind internship duration?'})
        assert first.status_code == 200, first.text
        assert first.json()['sources'], first.text
        followup = client.post('/api/v1/chat', json={'session_id': session, 'message': 'What do its interns work on?'})
        assert followup.status_code == 200 and followup.json()['sources'], followup.text
        booking_session = session + '-booking'
        for message in ['I want to book an interview.', 'My name is Riyan Shrestha.', 'riyan@example.com', 'October 20, 2099, at 2 PM.']:
            response = client.post('/api/v1/chat', json={'session_id': booking_session, 'message': message})
            assert response.status_code == 200, response.text
        assert 'confirm' in response.json()['answer'].lower(), response.text
        confirmed = client.post('/api/v1/chat', json={'session_id': booking_session, 'message': 'Yes, confirm.'})
        assert confirmed.status_code == 200 and confirmed.json()['booking_id'], confirmed.text
        repeated = client.post('/api/v1/chat', json={'session_id': booking_session, 'message': 'confirm'})
        assert repeated.json()['booking_id'] == confirmed.json()['booking_id']
        with SessionLocal() as db:
            assert len(db.scalars(select(Booking).where(Booking.session_id == booking_session)).all()) == 1
