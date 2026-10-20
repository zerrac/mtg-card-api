from . import DISLIKED_SETS


def score_rank(face, preferred_lang, preferred_number, preferred_set):
    """Ranking ignoring sharpness: candidates with equal rank only differ by bluriness."""
    score = face.card.evaluate_score(preferred_lang, preferred_number=preferred_number, preferred_set=preferred_set)
    disliked = 1 if face.card.edition in DISLIKED_SETS else 0
    return (disliked, -score)


def _sort_key(pair, preferred_lang, preferred_number, preferred_set):
    face, image = pair
    return (*score_rank(face, preferred_lang, preferred_number, preferred_set), -image.bluriness)


def sorted_candidates(candidates, preferred_lang="en", preferred_number=None, preferred_set=None):
    return sorted(candidates, key=lambda p: _sort_key(p, preferred_lang, preferred_number, preferred_set))


def select_best_candidate(candidates, preferred_lang="en", preferred_number=None, preferred_set=None):
    """Returns the highest-scored (face, image) pair, or (None, None)."""
    ordered = sorted_candidates(candidates, preferred_lang, preferred_number, preferred_set)
    return ordered[0] if ordered else (None, None)
