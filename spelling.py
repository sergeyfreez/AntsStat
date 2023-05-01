import os

import textdistance

cur_dir = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(cur_dir, 'resource/dictionary.txt'), 'r') as d:
    correct_words = tuple(i.strip() for i in d.read().splitlines())


def spell_check(word):
    if word is None or len(word) <= 3:
        return word
    for correct_word in correct_words:
        if textdistance.levenshtein(word, correct_word) <= 3:
            return correct_word
    return word
