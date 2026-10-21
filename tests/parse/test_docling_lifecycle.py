from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import weakref

import pytest

from semantica.parse.docling_parser import DoclingParser


@pytest.fixture(autouse=True)
def clear_shared_parser():
    DoclingParser.clear_shared()
    yield
    DoclingParser.clear_shared()


def test_shared_parser_accepts_path_configuration_and_isolates_model_changes(tmp_path):
    model_path = tmp_path / "models"
    with DoclingParser.lease(artifacts_path=model_path) as first:
        pass
    with DoclingParser.lease(artifacts_path=str(model_path)) as same:
        assert same is first
    with DoclingParser.lease(artifacts_path=Path(model_path, "replacement")) as changed:
        assert changed is not first


def test_shared_parser_does_not_take_ownership_of_injected_converter():
    with pytest.raises(ValueError, match="injected converters"):
        with DoclingParser.lease(converter=object()):
            pytest.fail("shared parser must not retain a caller-owned converter")


def test_shared_parser_reuses_configuration_and_releases_replaced_parser():
    with DoclingParser.lease(enable_ocr=False, export_format="doctags") as first:
        reference = weakref.ref(first)
    with DoclingParser.lease(export_format="doctags", enable_ocr=False) as same:
        assert same is first
    del first, same
    with DoclingParser.lease(enable_ocr=True, export_format="doctags") as changed:
        assert changed.enable_ocr
        assert reference() is None
    DoclingParser.clear_shared()


def test_shared_parser_discards_failed_conversion_and_does_not_retain_documents():
    with pytest.raises(RuntimeError, match="conversion failed"):
        with DoclingParser.lease(enable_ocr=False) as failed:
            failed._converter = object()
            raise RuntimeError("conversion failed")
    with DoclingParser.lease(enable_ocr=False) as recovered:
        assert recovered is not failed
        assert recovered._converter is None
    DoclingParser.clear_shared()


def test_shared_parser_serializes_leases_and_cleanup_waits_for_active_work():
    entered, release, waiting, cleaned = Event(), Event(), Event(), Event()

    def hold():
        with DoclingParser.lease(enable_ocr=False):
            entered.set()
            assert release.wait(5)

    def clear():
        waiting.set()
        DoclingParser.clear_shared()
        cleaned.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        active = executor.submit(hold)
        assert entered.wait(5)
        cleanup = executor.submit(clear)
        assert waiting.wait(5)
        assert not cleaned.is_set()
        release.set()
        active.result(timeout=5)
        cleanup.result(timeout=5)
    assert cleaned.is_set()


def test_concurrent_same_configuration_leases_share_one_parser_without_overlap():
    entered, release, waiting, second_entered = Event(), Event(), Event(), Event()

    def first_lease():
        with DoclingParser.lease(enable_ocr=False) as parser:
            entered.set()
            assert release.wait(5)
            return parser

    def second_lease():
        waiting.set()
        with DoclingParser.lease(enable_ocr=False) as parser:
            second_entered.set()
            return parser

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_lease)
        assert entered.wait(5)
        second = executor.submit(second_lease)
        assert waiting.wait(5)
        assert not second_entered.is_set()
        release.set()
        assert first.result(timeout=5) is second.result(timeout=5)
    assert second_entered.is_set()
