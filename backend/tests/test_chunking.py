from app.rag.chunking import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS, chunk_text


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_text("a short page", page=3, source="book")
    assert len(chunks) == 1
    assert chunks[0].text == "a short page"
    assert chunks[0].page == 3
    assert chunks[0].chunk_id == "book-p3-0"


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_text("", page=1, source="book") == []


def test_long_text_is_split_with_overlap() -> None:
    text = "".join(str(i % 10) for i in range(CHUNK_SIZE_CHARS * 2))
    chunks = chunk_text(text, page=1, source="book")
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= CHUNK_SIZE_CHARS
    # consecutive chunks overlap by roughly CHUNK_OVERLAP_CHARS
    overlap = len(set(chunks[0].text[-CHUNK_OVERLAP_CHARS:]) & set(chunks[1].text[:CHUNK_OVERLAP_CHARS]))
    assert overlap > 0


def test_chunk_ids_are_unique_and_ordered() -> None:
    text = "x" * (CHUNK_SIZE_CHARS * 3)
    chunks = chunk_text(text, page=7, source="krcmar")
    ids = [c.chunk_id for c in chunks]
    assert ids == [f"krcmar-p7-{i}" for i in range(len(chunks))]
    assert len(set(ids)) == len(ids)
