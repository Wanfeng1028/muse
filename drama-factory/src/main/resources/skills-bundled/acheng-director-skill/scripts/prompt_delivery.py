"""Expand explicit production bindings and reject model-facing shorthand.

This checks known reference syntax, not arbitrary natural-language semantics.
Dialogue and quoted on-screen text are literal content, never macro input.
"""
import re


class PromptDeliveryError(ValueError):
    pass


LITERAL = re.compile(r'<d>.*?</d>|"[^"\n]*"', re.S)
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")
CODE = re.compile(
    r"\b(?:CHAR|SCENE|PROP|ASSET|EX|EV|FILM)[_-][A-Za-z0-9_-]+\b|"
    r"\b(?:M0[1-3]|F0[1-3]|A0[1-3]|[EO]\d{3})\b|"
    r"\b(?:KF\d+|D[0-3])\b|\b(?i:trauma|damage)\s*(?i:phase|level)\s*[0-3]\b|"
    r"(?<![A-Za-z])[A-I]\s*(?:型|类|款)?\s*(?:身材|体型|性格|人格|原型)|"
    r"(?:身材|体型|性格|人格|原型)\s*(?:编号|代号|为|是|[:：])?\s*[A-I](?![A-Za-z])|"
    r"\b(?i:body|personality|emotion|archetype|camera|previs)\s*(?i:type|code|preset|id)?\s*[:#=-]?\s*(?:[A-I]|\d{3})\b|"
    r"\b[A-I](?:-|(?i:-type-| type ))(?i:body|personality|archetype)\b|"
    r"(?:运镜|情绪|表情)\s*(?:编号|代号|[:：])?\s*[0-9]{3}\b|\[img\d+\]")
EXTERNAL = re.compile(
    r"同上|如上|见上文|沿用上段|同上一段|上一段设定|沿用前文|其余不变|"
    r"\b(?:as above|same as above|as previously described|as defined earlier|"
    r"previous (?:prompt|segment)|preceding (?:prompt|segment)|"
    r"registered (?:character|scene|repair hangar|maintenance room)|"
    r"according to (?:the )?(?:character|scene|visual) bible)\b", re.I)
PLACEHOLDER = re.compile(r"\{\{|\}\}|\b(?:TBD|TODO)\b|待填|待补|<insert\b|\[INSERT\b", re.I)


def prose_only(text):
    return LITERAL.sub("", text)


def expand_prompt(text, bindings=None):
    if not isinstance(text, str) or not text.strip():
        raise PromptDeliveryError("model prompt must contain text")
    bindings = bindings or {}
    def expand(part, stack=()):
        def replace(match):
            key = match.group(1)
            if key in stack:
                raise PromptDeliveryError(f"cyclic prompt binding: {key}")
            value = bindings.get(key)
            if not isinstance(value, str) or not value.strip():
                raise PromptDeliveryError(f"unresolved prompt binding: {key}")
            return expand(value, (*stack, key))
        return TOKEN.sub(replace, part)
    # Preserve user-authored literal content byte-for-byte.
    parts, cursor = [], 0
    for match in LITERAL.finditer(text):
        parts.extend((expand(text[cursor:match.start()]), match.group()))
        cursor = match.end()
    parts.append(expand(text[cursor:]))
    return "".join(parts)


def require_standalone(text, internal_ids=(), english=False):
    prose = prose_only(text)
    for pattern, label in ((CODE, "unexpanded production code"),
                           (EXTERNAL, "external-context dependency"),
                           (PLACEHOLDER, "unresolved placeholder")):
        match = pattern.search(prose)
        if match:
            raise PromptDeliveryError(f"{label}: {match.group()}")
    for value in internal_ids:
        if value and re.search(r"(?<![\w])" + re.escape(value) + r"(?![\w])", prose):
            raise PromptDeliveryError(f"internal ID in model prompt: {value}")
    if english and re.search(r"[\u3400-\u9fff]", prose):
        raise PromptDeliveryError("H3 prose must be English; preserve dialogue/on-screen text only")


def render_asset_prompt(card, bindings=None, style_lock=None):
    policy = card.get("reference_policy")
    refs = card.get("references", [])
    if policy not in ("none", "required"):
        raise PromptDeliveryError("reference_policy must explicitly be none or required")
    if (policy == "none" and refs) or (policy == "required" and not refs):
        raise PromptDeliveryError("reference_policy and actual reference list disagree")
    if card.get("mode") in ("EDIT", "REBUILD", "MIXED") and not refs:
        raise PromptDeliveryError("image editing/rebuild requires the actual source image")
    chunks = []
    for i, ref in enumerate(refs, 1):
        if ref.get("image") != i:
            raise PromptDeliveryError("image reference numbers must follow upload order starting at 1")
        for field in ("subject", "preserve", "exclude"):
            if not isinstance(ref.get(field), str) or len(ref[field].strip()) < 3:
                raise PromptDeliveryError(f"reference image {i}: {field} description required")
        chunks.append(f"Reference image {i} supplies {ref['role']} guidance for {ref['subject']}. "
                      f"Preserve {ref['preserve']}. Do not inherit {ref['exclude']}.")
    if style_lock and card.get("asset_kind") in style_lock.get("apply_to_kinds", []):
        preserve = "; ".join(style_lock["preserve_scope"])
        exclude = "; ".join(style_lock["exclude_scope"])
        style_refs = [ref for ref in refs if ref.get("role") == "style" and ref.get("asset_id") == style_lock["anchor_asset_id"]]
        if len(style_refs) != 1 or style_refs[0].get("asset_version") != style_lock["anchor_version"]:
            raise PromptDeliveryError("approved STYLE_MOTHER reference/version is required for this asset")
        style_ref = style_refs[0]
        if refs[-1] is not style_ref:
            raise PromptDeliveryError("STYLE_MOTHER must be the final uploaded reference slot")
        style_slot = refs.index(style_ref) + 1
        chunks.insert(0, f"Use Reference image {style_slot} (@图片{style_slot}) only as a visual style and rendering language anchor. "
                      f"Preserve {preserve}. Do not let it replace identity, body or face facts, scene geometry, camera layout, pose, action, state, exact light direction, text or logos; exclude {exclude} from style transfer.")
    chunks.append(card.get("prompt", ""))
    text = expand_prompt("\n\n".join(chunks), {**(bindings or {}), **card.get("prompt_bindings", {})})
    require_standalone(text, (card.get("id"),))
    used = {int(number) for pair in re.findall(r"\b(?:reference image|@image)\s*(\d+)\b|(?:参考图|@图|@图片)\s*(\d+)", text, re.I) for number in pair if number}
    if used != set(range(1, len(refs) + 1)):
        raise PromptDeliveryError("unresolved image reference number in final prompt")
    if not refs and re.search(r"参考图|上传的图|\b(?:reference image|uploaded image|source image)\b", prose_only(text), re.I):
        raise PromptDeliveryError("prompt requests a reference image but none is supplied")
    if len(text) > 32000:
        raise PromptDeliveryError("GPT Image prompt exceeds 32000 characters")
    return text.rstrip() + "\n"
