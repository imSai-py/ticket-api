"""Tests for knowledge base article retrieval."""

from app.retrieval import KBRetriever


def test_load_all_kb_articles():
    retriever = KBRetriever()
    articles = retriever.articles
    assert len(articles) == 6
    article_ids = {a.article_id for a in articles}
    assert article_ids == {
        "KB-001",
        "KB-002",
        "KB-003",
        "KB-004",
        "KB-005",
        "KB-006",
    }


def test_retrieve_password_reset_article():
    retriever = KBRetriever()
    results = retriever.retrieve("Cannot log in", "reset email never arrives")
    assert len(results) > 0
    assert results[0].article_id == "KB-001"


def test_retrieve_refund_article():
    retriever = KBRetriever()
    results = retriever.retrieve(
        "Refund please", "bought 20 days ago and want my money back"
    )
    assert len(results) > 0
    assert results[0].article_id == "KB-002"


def test_retrieve_shipping_article():
    retriever = KBRetriever()
    results = retriever.retrieve(
        "Where is my order?", "shipped 11 days ago and tracking not updated"
    )
    assert len(results) > 0
    assert results[0].article_id == "KB-004"


def test_retrieve_app_troubleshooting_article():
    retriever = KBRetriever()
    results = retriever.retrieve(
        "App keeps freezing", "app keeps freezing on the report screen"
    )
    assert len(results) > 0
    assert results[0].article_id == "KB-005"


def test_retrieve_unrelated_query_returns_empty():
    retriever = KBRetriever()
    results = retriever.retrieve(
        "Weather today", "what is the atmospheric pressure in Antarctica"
    )
    assert len(results) == 0


def test_retrieve_multilingual_spanish_query_matches_password_reset():
    retriever = KBRetriever()
    results = retriever.retrieve(
        "Acceso",
        "No puedo acceder a mi cuenta desde ayer, el correo de recuperacion no llega.",
    )
    assert len(results) > 0
    assert results[0].article_id == "KB-001"


def test_retrieve_unicode_characters_matches_article():
    # Verifies retrieval processes accented characters like 'contraseña' through public retrieve method
    retriever = KBRetriever()
    results = retriever.retrieve("Olvidé contraseña", "No puedo ingresar mi contraseña")
    assert len(results) > 0
    assert results[0].article_id == "KB-001"
