"""
Collector registry — Module 5B. Maps an AcquisitionJob's
`collector_type` string to the SourceAdapter class that handles it.
This is the extension point future collectors (website, api,
structured_file, user_submission) plug into — adding one is a single
dict entry here, not a change anywhere in acquisition_service, which
only ever depends on the SourceAdapter interface.

Module 6D adds the first real USA sources (sec_edgar, census_cbp,
usitc_dataweb) plus manual_entry — exactly this extension point, zero
change to acquisition_service itself, confirming Module 5B's own
extensibility goal.
"""

from app.collectors.base import SourceAdapter
from app.collectors.census_cbp_adapter import CensusCBPAdapter
from app.collectors.document_extraction_adapter import DocumentExtractionAdapter
from app.collectors.manual_entry_adapter import ManualEntryAdapter
from app.collectors.mca_data_gov_in_adapter import MCADataGovInAdapter
from app.collectors.mock_adapter import MockSourceAdapter
from app.collectors.sec_edgar_adapter import SECEdgarAdapter
from app.collectors.usitc_dataweb_adapter import USITCDataWebAdapter

_ADAPTERS: dict[str, type[SourceAdapter]] = {
    MockSourceAdapter.adapter_type: MockSourceAdapter,
    MCADataGovInAdapter.adapter_type: MCADataGovInAdapter,
    SECEdgarAdapter.adapter_type: SECEdgarAdapter,
    CensusCBPAdapter.adapter_type: CensusCBPAdapter,
    USITCDataWebAdapter.adapter_type: USITCDataWebAdapter,
    ManualEntryAdapter.adapter_type: ManualEntryAdapter,
    DocumentExtractionAdapter.adapter_type: DocumentExtractionAdapter,
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
