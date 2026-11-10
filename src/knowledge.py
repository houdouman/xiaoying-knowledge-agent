"""Small-corpus lexical retrieval with exact source offsets; no external index."""
import re


def split_documents(documents, size=240):
    chunks = []
    for doc in documents:
        text = doc['text']
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = max(text.rfind('。', start, end), text.rfind('\n', start, end))
                if boundary >= start + size // 2:
                    end = boundary + 1
            chunks.append(dict(doc, doc_id=doc['id'], chunk_id=f"{doc['id']}:{start}-{end}",
                               start=start, end=end, text=text[start:end]))
            start = end
    return chunks


def terms(text):
    text = re.sub(r'\s+', '', text.lower())
    return set(re.findall(r'[a-z0-9]+', text)) | {
        text[i:i+2] for i in range(len(text)-1)
        if all('\u4e00' <= c <= '\u9fff' for c in text[i:i+2])}


def search(chunks, query):
    # Exact theme keywords dominate; body bigrams allow unseen formulations.
    q = terms(query)
    scored = []
    for chunk in chunks:
        body = terms(chunk['text'] + chunk['title'])
        lexical = len(q & body)
        theme = sum(k in query for k in chunk.get('keywords', []))
        score = theme * 4 + lexical
        if theme or lexical >= 2:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]['chunk_id']))
    # Return all matching short-corpus passages: don't hide contradictory evidence.
    return [dict(id=c['id'], chunk_id=c['chunk_id'], version_date=c['version_date'],
                 title=c['title'], start=c['start'], end=c['end'], score=score,
                 snippet=c['text'][:80]) for score, c in scored]
