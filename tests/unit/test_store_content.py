"""Canonical content ``content_sha256`` (spec 2026-10-18 §3.1, ADR-003 D17)."""

import hashlib
import json
import struct

import pytest

from imgwtools.exceptions import IMGWDataError, IMGWValidationError
from imgwtools.store.content import CONTENT_FORMS, ContentForm, content_sha256

FORM = "chmi-json/1"
# Envelope of a ČHMÚ metadata file (fictional values, spec §1.1 "Koperta").
ENVELOPE = {
    "zaznamID": "11111111-1111-1111-1111-111111111111",
    "datovyZdrojID": "H",
    "datovyTokID": "Open.Data.Metadata",
    "datumVytvoreni": "2026-10-16T02:03:00Z",
    "verzeDat": "1",
    "data": {
        "type": "DataCollection",
        "data": {
            "header": "objID,STATION_NAME,GEOGR1",
            "values": [
                ["0-203-1-900001", "Špindlerův Mlýn", 50.72],
                ["0-203-1-900002", "Stanice", 12],
            ],
        },
    },
}


def digest(document) -> str:
    return content_sha256(json.dumps(document).encode("utf-8"), form=FORM)


def jcs_sum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_released_form_is_frozen():
    # A released form never changes: other volatile fields need a new identifier.
    released = {
        "chmi-json/1": ContentForm(
            "chmi-json/1", "json-jcs", ("zaznamID", "datumVytvoreni")
        )
    }
    assert released == CONTENT_FORMS


def test_serialization_details_and_new_envelope_keep_the_sum():
    base = digest(ENVELOPE)
    reordered = {key: ENVELOPE[key] for key in reversed(list(ENVELOPE))}
    regenerated = {
        **ENVELOPE,
        "zaznamID": "22222222-2222-2222-2222-222222222222",
        "datumVytvoreni": "2026-10-17T02:03:00Z",
    }
    without_envelope = {
        key: value
        for key, value in ENVELOPE.items()
        if key not in ("zaznamID", "datumVytvoreni")
    }
    spaced = json.dumps(ENVELOPE, indent=4, ensure_ascii=True).encode("utf-8")
    variants = [
        json.dumps(reordered).encode("utf-8"),
        spaced,
        b"\xef\xbb\xbf" + json.dumps(ENVELOPE).encode("utf-8"),
        json.dumps(regenerated).encode("utf-8"),
        json.dumps(without_envelope).encode("utf-8"),
        json.dumps(ENVELOPE, ensure_ascii=False).encode("utf-8"),
    ]
    assert {content_sha256(data, form=FORM) for data in variants} == {base}
    # The same number written as 12, 12.0 and 1.2E1; \u0161 escaped or literal.
    numbers = {
        content_sha256(f'{{"n":{text},"s":"\\u0161"}}'.encode(), form=FORM)
        for text in ("12", "12.0", "1.2E1")
    }
    assert numbers == {content_sha256('{"s":"š","n":12}'.encode(), form=FORM)}


def test_every_other_change_changes_the_sum():
    base = digest(ENVELOPE)
    values = ENVELOPE["data"]["data"]["values"]
    changed = [
        {
            **ENVELOPE,
            "data": {
                **ENVELOPE["data"],
                "data": {
                    **ENVELOPE["data"]["data"],
                    "values": [values[0], [*values[1][:2], 13]],
                },
            },
        },
        {
            **ENVELOPE,
            "data": {
                **ENVELOPE["data"],
                "data": {**ENVELOPE["data"]["data"], "values": list(reversed(values))},
            },
        },
        {**ENVELOPE, "verzeDat": "2"},
        {**ENVELOPE, "datovyTokID": "Open.Data.Other"},
        # A nested field of a volatile name is content, never removed.
        {**ENVELOPE, "data": {**ENVELOPE["data"], "zaznamID": "x"}},
    ]
    sums = [digest(document) for document in changed]
    assert base not in sums
    assert len(set(sums)) == len(sums)


def test_canonical_text_follows_rfc8785_examples():
    # RFC 8785 §3.2.2: values and string escaping.
    source = (
        '{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, '
        "0.000000000000000000000000001], "
        r'"string": "\u20ac$\u000F\u000aA'
        "'"
        r'\u0042\u0022\u005c\\\"\/", '
        '"literals": [null, true, false]}'
    )
    expected = (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,'
        '1e-27],"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert content_sha256(source.encode(), form=FORM) == jcs_sum(expected)
    # RFC 8785 §3.2.3: object keys sorted by UTF-16 code units.
    keys = (
        '{"\\u20ac": "Euro Sign", "\\r": "Carriage Return", "\\ufb33": "Hebrew", '
        '"1": "One", "\\ud83d\\ude00": "Emoji", "\\u0080": "Control", '
        '"\\u00f6": "Latin"}'
    )
    ordered = (
        '{"\\r":"Carriage Return","1":"One","\u0080":"Control","\u00f6":"Latin",'
        '"\u20ac":"Euro Sign","\U0001f600":"Emoji","\ufb33":"Hebrew"}'
    )
    assert content_sha256(keys.encode(), form=FORM) == jcs_sum(ordered)


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        # RFC 8785 Appendix B (IEEE 754 bits → ECMAScript notation).
        ("0000000000000000", "0"),
        ("8000000000000000", "0"),
        ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"),
        ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"),
        ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"),
        ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"),
        ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"),
        ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"),
        ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"),
        ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"),
        ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"),
        ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ],
)
def test_numbers_follow_rfc8785_appendix_b(bits, expected):
    number = struct.unpack(">d", bytes.fromhex(bits))[0]
    data = f'{{"n":{number!r}}}'.encode()
    assert content_sha256(data, form=FORM) == jcs_sum(f'{{"n":{expected}}}')


@pytest.mark.parametrize(
    "data",
    [
        b'{"a":1,"a":1}',
        b'{"a":{"b":1,"b":2}}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":1e400}',
        b'{"a":' + b"1" * 400 + b"}",
        b'{"a":"\xff"}',
        b"\xef\xbb\xbf\xef\xbb\xbf{}",
        b"[1,2]",
        b'"text"',
        b'{"a":1} {}',
        b'{"a":1,}',
        b'{"a":"\\ud800"}',
        b"",
    ],
)
def test_bytes_violating_the_form_are_a_data_error(data):
    with pytest.raises(IMGWDataError) as error:
        content_sha256(data, form=FORM)
    assert error.value.code == "data_error"


def test_unknown_form_is_a_validation_error():
    with pytest.raises(IMGWValidationError) as error:
        content_sha256(b"{}", form="chmi-json/9")
    assert error.value.details["allowed"] == ["chmi-json/1"]
