"""
Extractive summarization (TextRank, Mihalcea & Tarau 2004) -- picks the most
"central" existing sentences from a piece of text rather than generating new
prose. No ML model, no external service: sentences are scored by how much
word-overlap they share with the rest of the document (a graph where
sentences are nodes and shared-word overlap is the edge weight), ranked via
the same power-iteration approach as PageRank, and the top-scoring ones are
returned in their original order for readability.

This is a deliberate choice over an LLM summarizer for this project: it can
never fabricate a sentence that isn't actually in the source article, at the
cost of not being able to rewrite anything into simpler language -- the
output is always real sentences pulled from the text, not a paraphrase.
"""

import re

import numpy as np

import config

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])')
_WORD_RE = re.compile(r"[A-Za-z']+")

_STOPWORDS = frozenset("""
a an the and or but if then else when while of to in on at by for with about
against between into through during before after above below from up down
out off over under again further once here there all any both each few more
most other some such no nor not only own same so than too very s t can will
just don should now is are was were be been being have has had do does did
doing this that these those i you he she it we they what which who whom
""".split())


def _split_sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    raw = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in raw if len(s.strip()) > 0]


def _sentence_words(sentence):
    words = [w.lower() for w in _WORD_RE.findall(sentence)]
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _similarity(words_a, words_b):
    if not words_a or not words_b:
        return 0.0
    set_a, set_b = set(words_a), set(words_b)
    common = len(set_a & set_b)
    if common == 0:
        return 0.0
    denom = np.log(len(set_a) + 1) + np.log(len(set_b) + 1)
    return common / denom if denom > 0 else 0.0


def _textrank_scores(sentences, damping=0.85, iterations=50, tol=1e-4):
    n = len(sentences)
    if n <= 1:
        return np.ones(n)

    word_lists = [_sentence_words(s) for s in sentences]
    sim = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            s = _similarity(word_lists[i], word_lists[j])
            sim[i, j] = s
            sim[j, i] = s

    row_sums = sim.sum(axis=1)
    row_sums[row_sums == 0] = 1.0  # isolated sentences -- avoid divide-by-zero
    transition = sim / row_sums[:, None]

    scores = np.full(n, 1.0 / n)
    for _ in range(iterations):
        new_scores = (1 - damping) / n + damping * transition.T.dot(scores)
        if np.abs(new_scores - scores).sum() < tol:
            scores = new_scores
            break
        scores = new_scores
    return scores


def summarize_article(text, bullet_sentences=None, indepth_sentences=None):
    """
    Returns {"bullet": [...], "indepth": [...]} -- both lists of sentences
    from `text`, in their original order. "bullet" is the short version
    (for inline display), "indepth" is the longer version (for the popup).
    """
    bullet_sentences = bullet_sentences or config.NEWS_SUMMARY_BULLET_SENTENCES
    indepth_sentences = indepth_sentences or config.NEWS_SUMMARY_INDEPTH_SENTENCES

    sentences = _split_sentences(text)
    if not sentences:
        return {"bullet": [], "indepth": []}
    if len(sentences) <= bullet_sentences:
        return {"bullet": sentences, "indepth": sentences}

    scores = _textrank_scores(sentences)
    ranked_idx = np.argsort(-scores)

    bullet_idx = sorted(ranked_idx[:bullet_sentences].tolist())
    indepth_count = min(indepth_sentences, len(sentences))
    indepth_idx = sorted(ranked_idx[:indepth_count].tolist())

    return {
        "bullet": [sentences[i] for i in bullet_idx],
        "indepth": [sentences[i] for i in indepth_idx],
    }
