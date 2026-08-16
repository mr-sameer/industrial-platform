"""
Collector registry — Module 5B. Maps an AcquisitionJob's
`collector_type` string to the SourceAdapter class that handles it.
This is the extension point future collectors (website, api,
structured_file, user_submission) plug into — adding one is a single
dict entry here, not a change anywhere in acquisition_service, which
only ever depends on the SourceAdapter interface.

Only "mock" is registered in this phase, matching this module's
explicit scope: no real external collector exists yet.
"""

from app.collectors.base import SourceAdapter
from app.collectors.mca_data_gov_in_adapter import MCADataGovInAdapter
from app.collectors.mock_adapter import MockSourceAdapter

_ADAPTERS: dict[str, type[SourceAdapter]] = {
    MockSourceAdapter.adapter_type: MockSourceAdapter,
    MCADataGovInAdapter.adapter_type: MCADataGovInAdapter,
}


class UnknownCollectorTypeError(Exception):
    pass


def get_adapter(collector_type: str) -> SourceAdapter:
    adapter_cls = _ADAPTERS.get(collector_type)
    if adapter_cls is None:
        raise UnknownCollectorTypeError(
            f"No collector registered for type {collector_type!r}. Known types: {sorted(_ADAPTERS)}"
        )
    return adapter_cls()


def known_collector_types() -> list[str]:
    return sorted(_ADAPTERS)
