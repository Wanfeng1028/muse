"""Text helpers for the voice scripts: tags, spoken-text normalization with homophones, word and syllable counts."""
import re
import unicodedata

TAG_PATTERN = re.compile(r"\[([^\]]*)\]")
QUOTES = "«»\"“”„'‘’¡!¿?.,;:…()-–—"

NUMERALS: dict[str, dict[str, str]] = {
    "es": {"0": "cero", "1": "uno", "2": "dos", "3": "tres", "4": "cuatro", "5": "cinco", "6": "seis", "7": "siete",
           "8": "ocho", "9": "nueve", "10": "diez", "100": "cien", "1000": "mil"},
    "pt": {"0": "zero", "1": "um", "2": "dois", "3": "tres", "4": "quatro", "5": "cinco", "6": "seis", "7": "sete",
           "8": "oito", "9": "nove", "10": "dez", "100": "cem", "1000": "mil"},
    "en": {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
           "8": "eight", "9": "nine", "10": "ten", "100": "hundred", "1000": "thousand"},
}


def strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", TAG_PATTERN.sub(" ", text)).strip()


def tags(text: str) -> list[str]:
    return [tag.strip() for tag in TAG_PATTERN.findall(text)]


def tag_words(text: str) -> set[str]:
    return {word for tag in tags(text) for word in re.findall(r"[a-z]+", tag.lower()) if len(word) > 2}


def words(text: str) -> list[str]:
    return [token for token in strip_tags(text).split() if any(character.isalnum() for character in token)]


def internal_pauses(text: str) -> int:
    """Commas, stops, ellipses, colons and dashes inside the line (not at its end): each one adds a breath."""
    spoken = strip_tags(text).rstrip(" .!?…»\"'")
    return len(re.findall(r"\.{3}|…|[,;:.!?]|\s[-–—]\s", spoken))


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).lower()


def spanish_homophones(word: str) -> str:
    word = word.replace("ch", "\0").replace("h", "").replace("\0", "ch")
    word = word.replace("v", "b").replace("z", "s").replace("ll", "y")
    word = re.sub(r"c(?=[ei])", "s", word)
    return re.sub(r"y$", "i", word)


def portuguese_homophones(word: str) -> str:
    return re.sub(r"^h", "", word).replace("ss", "s")


HOMOPHONES = {"es": spanish_homophones, "pt": portuguese_homophones}


def normalize_word(token: str, language: str) -> str:
    numerals = NUMERALS.get(language, {})
    bare = token.strip(QUOTES)
    folded = re.sub(r"[^a-z]", "", fold(numerals.get(bare, bare)))
    rule = HOMOPHONES.get(language)
    return rule(folded) if rule and folded else folded


SPOKEN_SYMBOLS = {"es": ("punto", "arroba"), "pt": ("ponto", "arroba"), "en": ("dot", "at")}


def normalize_spoken(text: str, language: str) -> list[str]:
    dot, at = SPOKEN_SYMBOLS.get(language, (".", "@"))
    spoken = re.sub(r"(?<=\w)\.(?=\w)", f" {dot} ", strip_tags(text)).replace("@", f" {at} ")
    tokens = re.split(r"[\s\-–—/]+", spoken)
    return [word for word in (normalize_word(token, language) for token in tokens) if word]


SPANISH_STRONG = set("aeoáéóíú")
PORTUGUESE_STRONG = set("aeoáéóíúâêôãõà")
WEAK = set("iuüy")


def _romance_syllables(word: str, strong: set[str]) -> int:
    word = re.sub(r"(?<=q)u|(?<=g)u(?=[eéií])", "", word.lower()).replace("h", "")
    if word == "y":
        return 1
    vowels = strong | WEAK
    count, group = 0, ""
    for index, character in enumerate(word + " "):
        is_vowel = character in vowels and not (character == "y" and index + 1 < len(word) and word[index + 1] in vowels)
        if is_vowel:
            group += character
            continue
        if group:
            count += max(1, sum(1 for vowel in group if vowel in strong))
        group = ""
    return max(1, count) if re.search(r"[a-záéíóúâêôãõàü]", word) else 0


def _english_syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and groups > 1:
        groups -= 1
    if re.search(r"[^aeiou]ed$", word) and not re.search(r"[td]ed$", word) and groups > 1:
        groups -= 1
    return max(1, groups)


def syllables(text: str, language: str) -> int:
    total = 0
    for token in words(text):
        bare = re.sub(r"[^\w]", "", token.lower())
        if language == "en":
            total += _english_syllables(bare)
        elif language == "pt":
            total += _romance_syllables(re.sub(r"(?<=[ãõ])[eo]", "", bare), PORTUGUESE_STRONG)
        else:
            total += _romance_syllables(bare, SPANISH_STRONG)
    return total


STOPWORDS: dict[str, set[str]] = {
    "es": {"el", "los", "las", "y", "en", "una", "es", "por", "con", "para", "pero", "como", "muy", "sin", "también",
           "hay", "donde", "cuando", "todo", "nada", "algo", "ella", "esto", "eso", "tu", "tus", "yo", "ya", "está",
           "están", "puede", "porque", "qué", "cómo", "así", "hasta", "del", "al", "su", "sus", "le", "les", "mi", "aquí"},
    "pt": {"o", "os", "um", "uma", "em", "na", "no", "com", "não", "para", "mas", "como", "muito", "sem", "também",
           "há", "onde", "quando", "tudo", "nada", "você", "isso", "isto", "ele", "ela", "eu", "já", "está", "estão",
           "pode", "porque", "do", "da", "dos", "das", "ao", "seu", "sua", "meu", "minha", "aqui", "são", "é", "e"},
    "en": {"the", "and", "of", "to", "in", "is", "it", "you", "that", "with", "for", "on", "are", "this", "be", "your",
           "at", "from", "have", "not", "but", "what", "all", "can", "will", "just", "they", "we", "my", "our", "a", "an"},
}


def guess_language(text: str) -> tuple[str | None, dict[str, int]]:
    tokens = [token.strip(QUOTES).lower() for token in words(text)]
    scores = {language: sum(token in vocabulary for token in tokens) for language, vocabulary in STOPWORDS.items()}
    lowered = text.lower()
    scores["es"] += 3 * (("ñ" in lowered) + ("¿" in lowered) + ("¡" in lowered))
    scores["pt"] += 3 * (bool(re.search(r"[ãõç]", lowered)) + bool(re.search(r"\b\w*(lh|nh)\w*\b", lowered)))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, runner_up = ranked[0], ranked[1]
    if best[1] >= 2 and best[1] - runner_up[1] >= 2:
        return best[0], scores
    return None, scores
