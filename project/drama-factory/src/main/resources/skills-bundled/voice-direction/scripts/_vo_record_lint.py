"""Script lint for vo_record.py: tag syntax, spoken-layer hazards (digits, URLs, acronyms) and language mismatches."""
import re

import _voice_text as text_tools

TAG_MODELS = ("eleven_v3", "eleven_v4")
MAX_TAGS = 3


def _bracket_problems(text: str) -> list[str]:
    depth, problems = 0, []
    for character in text:
        depth += {"[": 1, "]": -1}.get(character, 0)
        if depth < 0 or depth > 1:
            problems.append("unbalanced or nested [ ]")
            break
    if depth > 0:
        problems.append("unbalanced [ ] (a tag is never closed)")
    if re.search(r"\[\s*\]", text):
        problems.append("empty [ ] tag")
    return problems


def _tag_problems(text: str, model: str, vocabulary: list[str]) -> list[str]:
    problems = []
    found = text_tools.tags(text)
    if re.search(r"\((?:[A-Za-z]+[ ,]*){1,4}\)|\{[^}]*\}", text):
        problems.append("parentheses or braces used as a tag: they are spoken; use [tag]")
    if len(found) > MAX_TAGS:
        problems.append(f"{len(found)} tags in one line (more than {MAX_TAGS} blurs the read; tag only the shifts)")
    if re.search(r"\[[^\]]*\]\s*[.!?…]*\s*$", text):
        problems.append("tag with no text after it")
    if found and not model.startswith(TAG_MODELS):
        problems.append(f"[tags] on {model} are spoken aloud (only eleven_v3/v4 read them as directions)")
    if model.startswith(TAG_MODELS) and re.search(r"<\s*(break|phoneme)", text):
        problems.append(f"SSML <break>/<phoneme> is not supported on {model}; split the line or use IPA in /slashes/")
    vocabulary_lower = {tag.lower() for tag in vocabulary}
    unknown = [tag for tag in found if vocabulary and tag.lower() not in vocabulary_lower]
    if unknown:
        problems.append(f"tags outside the voice file vocabulary: {', '.join(unknown)}")
    return problems


def _spoken_layer_problems(text: str) -> list[str]:
    spoken = text_tools.strip_tags(text)
    problems = []
    if re.search(r"\d", spoken):
        problems.append("digits: write numbers as words in the spoken layer")
    symbols = sorted({symbol for symbol in "%$@/€£#&" if symbol in spoken})
    if symbols:
        problems.append(f"symbols {' '.join(symbols)}: write them as words")
    if re.search(r"\w\.(com|org|net|io|co|app|ai|dev|es|mx|br|pt)\b", spoken, re.IGNORECASE):
        problems.append("URL: spell it as it is said (e.g. 'acme punto com')")
    acronyms = sorted(set(re.findall(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b", spoken)))
    if acronyms:
        problems.append(f"all-caps {', '.join(acronyms)}: spell as said (letters or a word); caps can also sound shouted")
    return problems


def _language_problem(text: str, language: str | None) -> list[str]:
    if not language or len(text_tools.words(text)) < 4:
        return []
    guessed, _ = text_tools.guess_language(text_tools.strip_tags(text))
    if guessed and guessed != language:
        return [f"text reads as '{guessed}' but language_code is '{language}'"]
    return []


def lint_text(text: str, model: str, language: str | None, vocabulary: list[str]) -> list[str]:
    return (_bracket_problems(text) + _tag_problems(text, model, vocabulary) + _spoken_layer_problems(text)
            + _language_problem(text, language))
