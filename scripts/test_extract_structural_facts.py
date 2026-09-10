"""Regression test for the ref()/source() quote-style bug found running
this script, unmodified, against a real second (private) dbt project,
2026-08-25 -- its manifest renders ref("some_model") with double quotes;
jaffle_shop's only ever used single quotes, so this was never caught
until the pipeline was actually tested on a second real project, which is
exactly what that step is for.
"""
import pytest

from extract_structural_facts import _model_name_from_jinja


@pytest.mark.parametrize("quote", ["'", '"'])
def test_model_name_from_jinja_handles_both_quote_styles(quote):
    jinja = f"{{{{ get_where_subquery(ref({quote}some_model{quote})) }}}}"
    assert _model_name_from_jinja(jinja) == "some_model"


@pytest.mark.parametrize("quote", ["'", '"'])
def test_source_reference_is_skipped_regardless_of_quote_style(quote):
    jinja = f"{{{{ get_where_subquery(source({quote}raw{quote}, {quote}raw_customers{quote})) }}}}"
    assert _model_name_from_jinja(jinja) is None


def test_unrecognized_reference_shape_still_raises():
    with pytest.raises(ValueError):
        _model_name_from_jinja("{{ get_where_subquery(something_else()) }}")
