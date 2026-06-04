from . import DISLIKED_SETS


def select_best_candidate(candidates, preferred_lang="en", preferred_number=None, preferred_set=None):
    """
    candidates: list of (face, image) pairs, pre-fetched in memory
    Returns (face, image) or (None, None)
    """
    if not candidates:
        return None, None

    def sort_key(pair):
        face, image = pair
        score = face.card.evaluate_score(preferred_lang, preferred_number=preferred_number, preferred_set=preferred_set)
        disliked = 1 if face.card.edition in DISLIKED_SETS else 0
        return (disliked, -score, -image.bluriness)

    return min(candidates, key=sort_key)
