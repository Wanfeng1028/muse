import pytest

from one_memory.input_sanitization import sanitize_model_input, sanitize_model_input_with_spans


@pytest.mark.parametrize(
    "value",
    [
        "plain unchanged text",
        "\u4e2d\u6587\U0001f680e\u0301 token=example-secret tail /project/final.png",
        "Authorization: Bearer abcdefghijklmnop\nreal final decision",
        'start --password "two words" end',
        "https://alice:private-password@example.com/path and useful text",
        "prefix -----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY----- suffix",
        "token=example-secret first token=example-secret second",
        "sk-abcdefghijklmnopqrstuvwxyz and a conclusion",
        '{"password": "quoted space secret"} remaining',
        "already <redacted-secret> text",
    ],
)
def test_mapping_matches_existing_sanitizer_and_exact_original_slices(value):
    result = sanitize_model_input_with_spans(value)
    assert result.text == sanitize_model_input(value)
    previous_output = previous_source = 0
    for span in result.spans:
        assert span.start_cp >= previous_output and span.source_start_cp >= previous_source
        assert span.end_cp > span.start_cp
        assert (
            result.text[span.start_cp : span.end_cp]
            == value[span.source_start_cp : span.source_end_cp]
        )
        previous_output, previous_source = span.end_cp, span.source_end_cp


def test_synthetic_replacements_never_claim_original_locations():
    value = "head token=private-value tail /final/design.png"
    result = sanitize_model_input_with_spans(value)
    retained = "".join(value[s.source_start_cp : s.source_end_cp] for s in result.spans)
    assert retained == "head  tail /final/design.png"
    assert result.text == "head token=<redacted-secret> tail /final/design.png"
    assert len(result.spans) == 2
    assert result.spans[-1].source_end_cp == len(value)


def test_repeated_identical_suffix_is_mapped_by_positions_not_string_search():
    value = "same token=same same token=same same"
    result = sanitize_model_input_with_spans(value)
    assert [(s.source_start_cp, s.source_end_cp) for s in result.spans] == [
        (0, 5),
        (15, 21),
        (31, 36),
    ]


def test_sequential_overlapping_rules_do_not_restore_secret_mapping():
    value = "prefix token=sk-abcdefghijklmnopqrstuvwxyz suffix"
    result = sanitize_model_input_with_spans(value)
    assert result.text == sanitize_model_input(value)
    assert [(s.source_start_cp, s.source_end_cp) for s in result.spans] == [(0, 7), (42, 49)]


def test_empty_input_and_unchanged_identity_map():
    assert sanitize_model_input_with_spans("").spans == ()
    result = sanitize_model_input_with_spans("unchanged")
    assert len(result.spans) == 1
    span = result.spans[0]
    assert (span.start_cp, span.end_cp, span.source_start_cp, span.source_end_cp) == (0, 9, 0, 9)


def test_combinations_preserve_legacy_output_and_partition_every_original_codepoint():
    import random

    from one_memory import input_sanitization as original

    randomizer = random.Random(20260919)
    fragments = [
        "normal text ",
        "\u6c49\u5b57\U0001f680e\u0301 ",
        "token=private-value ",
        "sk-abcdefghijklmnopqrstuvwxyz ",
        "https://user:password@example.com/path ",
        "Authorization: Bearer abcdefghijklmnop ",
        '--password "space secret" ',
        "-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY----- ",
        '{"password": "quoted secret"} ',
        "<redacted-secret> ",
    ]
    for _ in range(200):
        value = "".join(randomizer.choices(fragments, k=12))
        # Frozen pre-refactor substitution order, reusing the existing patterns.
        legacy = original._PRIVATE_KEY.sub(original.REDACTED_SECRET, value)
        legacy = original._AUTHORIZATION.sub(r"\1 <redacted-secret>", legacy)
        legacy = original._CLI_SECRET.sub(r"\1\2<redacted-secret>", legacy)
        legacy = original._ASSIGNED_SECRET.sub(original._redact_assignment, legacy)
        legacy = original._KNOWN_TOKEN.sub(original.REDACTED_SECRET, legacy)
        legacy = original._URL_CREDENTIAL.sub(
            lambda m: f"{m.group('scheme')}{m.group('user')}:<redacted-secret>@", legacy
        )
        result = sanitize_model_input_with_spans(value)
        assert result.text == legacy == sanitize_model_input(value)
        ranges = sorted(
            [(s.source_start_cp, s.source_end_cp) for s in result.spans] + list(result.excluded)
        )
        assert ranges[0][0] == 0 and ranges[-1][1] == len(value)
        assert all(left[1] == right[0] for left, right in zip(ranges, ranges[1:], strict=False))
        for span in result.spans:
            assert (
                result.text[span.start_cp : span.end_cp]
                == value[span.source_start_cp : span.source_end_cp]
            )
